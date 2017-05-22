import os
import json
import boto3
import requests
from urllib.parse import urlparse, urljoin
from requests.auth import HTTPBasicAuth
from flask import request
from flask_wtf import Form
from wtforms import TextField, PasswordField, SubmitField, validators

ZAPPA_HOST = os.getenv('ZAPPA_HOST')
WATSON_URL = 'https://stream.watsonplatform.net/speech-to-text/api/v1/'
WATSON_USER = os.getenv('IBM_WATSON_USERNAME')
WATSON_PASS = os.getenv('IBM_WATSON_PASSWORD')
WATSON_PARAMS = [
    'model=en-US_NarrowbandModel',
    'timestamps=true',
    'speaker_labels=true',
    'smart_formatting=true',
    'events=recognitions.completed_with_results'
]
S3_BUCKET = os.getenv('S3_BUCKET')

s3 = boto3.resource('s3')
s3_client = boto3.client(
    's3',
    region_name=os.getenv('AWS_REGION'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)


# Source: http://flask.pocoo.org/snippets/62/
def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


class LoginForm(Form):
    username = TextField('Username', [validators.Required()])
    password = PasswordField('Password', [validators.Required()])
    submit = SubmitField("Login")

    def __init__(self, *args, **kwargs):
        Form.__init__(self, *args, **kwargs)

    def validate(self):
        rv = Form.validate(self)
        if not rv:
            return False
        return self.username.data == os.getenv('HTTP_USER') and self.password.data == os.getenv('HTTP_PASS')


def handle_audio(event, context):
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    key = record['s3']['object']['key']
    if not key.endswith('.wav'):
        return

    audio_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    # NOTE: Slicing key because assuming will be in "uploads/" and slashes can't be in Flask path
    callback_url = ZAPPA_HOST + '/callback/{}/results'.format(key.split('/')[-1])

    post_watson = WATSON_URL + 'register_callback?callback_url=' + callback_url
    resp = requests.post(post_watson, auth=HTTPBasicAuth(WATSON_USER, WATSON_PASS))
    if resp.status_code not in [200, 201]:
        print('Failure registering callback')

    res = requests.post(
        # NOTE: events parameter is important, makes sure results are sent in callback
        url=WATSON_URL + 'recognitions?callback_url={}&{}'.format(callback_url, '&'.join(WATSON_PARAMS)),
        data=audio_obj['Body'].read(),
        headers={'Content-Type': 'audio/wav'},
        auth=HTTPBasicAuth(WATSON_USER, WATSON_PASS)
    )
    if res.status_code == 201:
        print('Job created')
        print(res.content)
    else:
        print('Job creation failed with status code {}'.format(res.status_code))\


def process_transcription(event, context):
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    key = record['s3']['object']['key']

    # TODO: Don't see option for filter params in Zappa config, manually doing for now
    if not key.endswith('.json'):
        return

    transcript_obj = s3.Object(S3_BUCKET, key)
    transcription_dict = json.loads(transcript_obj.get()['Body'].read())
