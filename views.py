import os
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
    aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
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
        return redirect(next or flask.url_for('views.index'))
    return render_template('login.html', form=form)


@views.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('views.login'))


@views.route('/')
@auth_required
def index():
    prefix = request.args.get('prefix', '')
    render_dict = {}

    # At top level, only list dates
    if not len(prefix):
        objects = s3_client.list_objects(Bucket=S3_BUCKET, Prefix=prefix, Delimiter='/')
        render_dict['prefixes'] = [obj['Prefix'] for obj in objects['CommonPrefixes']]
    else:
        objects = s3_client.list_objects(Bucket=S3_BUCKET, Prefix=prefix)
        keys = [obj['Key'] for obj in objects['Contents'] if not obj['Key'].endswith('/')]
        key_dicts = [{'recording': k} for k in filter(lambda x: '/recordings/' in x, keys)]
        for kd in key_dicts:
            kd['audio_url'] = s3_client.generate_presigned_url(
                ClientMethod='get_object',
                Params={'Bucket': S3_BUCKET, 'Key': kd['recording']}
            )
            csv_key = kd['recording'].replace('/recordings/', '/clean/') + '.csv'
            if csv_key in keys:
                kd['transcript'] = csv_key.split('/')[-1]
                kd['transcript_url'] = s3_client.generate_presigned_url(
                    ClientMethod='get_object',
                    Params={'Bucket': S3_BUCKET, 'Key': csv_key}
                )

            kd['recording'] = kd['recording'].split('/')[-1]
            file_ext = kd['recording'].split('.')[-1]
            if file_ext == 'wav':
                kd['filetype'] = 'audio/x-wav'
            else:
                kd['filetype'] = 'audio/' + file_ext
        render_dict['prefix_date'] = keys[0].split('/')[0]
        render_dict['keys'] = key_dicts

    return render_template('index.html', **render_dict)


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


@views.route('/upload', methods=['GET', 'POST'])
@auth_required
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


@views.route('/edit', methods=['GET', 'POST'])
@auth_required
def edit_transcription():
    if request.method == 'GET':
        prefix = request.args.get('prefix')
        recording = request.args.get('recording')
        if not prefix and recording:
            return redirect(flask.url_for('views.index'))

        transcript_file = recording + '.json'
        transcript_key = '{}/results/{}'.format(prefix, transcript_file)
        transcript_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=transcript_key)
        transcript = json.loads(transcript_obj['Body'].read())

        results = transcript['results'][0]['results']
        result_list = []
        for result in results:
            r = result['alternatives'][0]
            result_list.append({
                'transcript': r['transcript'].replace('%HESITATION', ''),
                'start': r['timestamps'][0][1],
                'end': r['timestamps'][-1][2]
            })

        # Generating presigned url for audio playback
        audio_url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': S3_BUCKET, 'Key': '{}/recordings/{}'.format(prefix, recording)}
        )
        return render_template('editor.html',
                               # prefix=prefix,
                               transcript_key=transcript_key,
                               audio_url=audio_url,
                               filetype='audio/' + recording.split('.')[-1],
                               results=result_list)

    elif request.method == 'POST':
        result_json = request.get_json()
        if not len(result_json['results']):
            return redirect(flask.url_for('views.index'))

        transcript_obj = s3_client.get_object(Bucket=S3_BUCKET, Key=result_json['transcript_key'])
        transcript = json.loads(transcript_obj['Body'].read())

        results = transcript['results'][0]['results']
        if len(results) != len(result_json['results']):
            return redirect(flask.url_for('views.index'))

        for idx, r in enumerate(results):
            r['alternatives'][0]['transcript'] = result_json['results'][idx]

        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=result_json['transcript_key'],
            Body=json.dumps(transcript)
        )

        return jsonify({'message': 'success'})
