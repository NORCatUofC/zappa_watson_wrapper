import os
import io
from functools import wraps
from datetime import date
import boto3
from botocore.client import Config
import flask
import json
from flask import (Blueprint, Response, redirect, render_template, request,
    current_app, jsonify, session, url_for)
from flask_wtf.csrf import CSRFProtect
from utils import LoginForm, is_safe_url

csrf = CSRFProtect()
views = Blueprint('views', __name__)


ZAPPA_HOST = os.getenv('ZAPPA_HOST')
S3_BUCKET = os.getenv('S3_BUCKET')
s3 = boto3.resource('s3')
s3_client = boto3.client(
    's3',
    region_name=os.getenv('AWS_REGION'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    config=Config(signature_version='s3v4')
)
WATSON_URL = 'https://stream.watsonplatform.net/speech-to-text/api/v1/'


def auth_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('logged_in', False):
            return func(*args, **kwargs)
        else:
            return redirect('{}?next={}'.format(url_for('views.login'), url_for('views.index')))
    return wrapper


@views.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        session['logged_in'] = True
        next = flask.request.args.get('next', '')
        if not is_safe_url(next):
            return flask.abort(400)
        return redirect(next or flask.url_for('index'))
    return render_template('login.html', form=form)


@views.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('views.login'))


@views.route('/')
@auth_required
def index():
    bucket = s3.Bucket(S3_BUCKET)
    prefix = request.args.get('prefix', '')
    prefixes, keys = [], []

    # At top level, only list dates
    if not len(prefix):
        objects = s3_client.list_objects(Bucket=S3_BUCKET, Prefix=prefix, Delimiter='/')
        prefixes = [obj['Prefix'] for obj in objects['CommonPrefixes']]
    else:
        objects = s3_client.list_objects(Bucket=S3_BUCKET, Prefix=prefix)
        keys = [obj['Key'] for obj in objects['Contents'] if not obj['Key'].endswith('/')]

    return render_template('index.html', prefixes=prefixes, keys=keys)


@views.route('/callback/<string:audio_key>/results', methods=['GET', 'POST'])
@csrf.exempt
def callback_route(audio_key):
    # Responds to Watson callback setting
    # TODO: Implement solving challenge_string
    if request.method == 'GET':
        challenge_string = request.args.get('challenge_string')
        if challenge_string:
            return Response(request.args.get('challenge_string'), mimetype='text/plain')
        else:
            return Response('', mimetype='text/plain')
    elif request.method == 'POST':
        # Gets 'results' val if finished, uploads as JSON to S3 in separate dir
        post_vals = request.get_json()
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key='{}/results/{}.json'.format(date.today().strftime('%Y%m%d'), audio_key),
            Body=json.dumps(post_vals)
        )
        return jsonify({'message': 'Success'})


@views.route('/download')
@auth_required
def download():
    key_val = request.args.get('key')
    if not key_val:
        resp = jsonify({'status': 404, 'message': 'Not found'})
        resp.status_code = 404
        return resp

    download_url = s3_client.generate_presigned_url(
        ClientMethod='get_object',
        Params={'Bucket': S3_BUCKET, 'Key': key_val}
    )
    return redirect(download_url)


@views.route('/s3-post', methods=['GET', 'POST'])
def direct_upload():
    # Load required data from the request
    if request.method == 'GET':
        return render_template('upload.html')
    elif request.method == 'POST':
        form = dict(request.form)
        # Form keys are in list form, unpacking
        file_name = form['file-name'][0]
        file_type = form['file-type'][0]
        # Generate and return the presigned URL
        presigned_post = s3_client.generate_presigned_post(
            Bucket=S3_BUCKET,
            Key=file_name,
            Fields={"acl": "public-read", "Content-Type": file_type},
            Conditions=[{"Content-Type": file_type}],
            ExpiresIn=3600
        )

        return jsonify(presigned_post)
