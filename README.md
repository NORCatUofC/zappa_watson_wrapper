# Watson Speech-to-Text Wrapper

Light GUI for uploading audio recordings in a Flask app running on an AWS Lambda with Zappa to an S3 bucket, transcribing
them through IBM Watson's speech-to-text service, and then cleaning up the results.

## Setup

### Accounts

In order to run this app you'll need an accounts with both [IBM Bluemix](https://www.ibm.com/cloud-computing/bluemix/) and
AWS. This uses the IBM Watson [Speech-to-Text](https://www.ibm.com/watson/developercloud/speech-to-text.html) to transcribe
uploaded audio, so you'll need to create credentials in Bluemix that will work with that service. You'll also need a
valid set of AWS credentials ([`aws-cli`](https://aws.amazon.com/cli/) is usually the easiest way of settings this up).

### Python 3.6 Environment

Once you have the accounts set up, you can create the virtual environment using `venv` in Python 3.6. **Note:** The
application is only tested in a Python 3.6 Lambda environment.

After the virtual environment is created, activate it, and install dependencies with `pip install -r requirements.txt`.
You'll then need to set environment variables (see `env.json.sample` for a list of what needs to be set, `ZAPPA_HOST` will
come from the deployment and can be ignored for now).

### Audio Conversion with `ffmpeg`

The Lambda function currently uses `ffmpeg` to convert audio to OGG format. You'll need to download a binary from
https://www.johnvansickle.com/ffmpeg/ and add it to the `lib/` directory for it to work.

### Configuration and Deployment

After you have `ffmpeg` in the `lib/` directory, create a JSON file with your environment variables similar to `env.json.sample`,
and upload it to an S3 bucket. Change the path in `zappa_settings.json` to match the path to that file. Also update the paths
in `zappa_settings.json` for `s3_bucket` and the `arn` of `event_source` to buckets your account has access to.

Once you've made the configuration changes, run `zappa deploy dev`. You should be able to access the Lambda in the AWS console.
Make sure to give the newly created role access to all of the mentioned S3 buckets, and then add the full API Gateway path
(i.e. RANDOMCHARS.execute-api.us-east-1.amazonaws.com/dev/) from the Zappa deployment output to your environment variables
JSON file as `ZAPPA_HOST`, and update the file in the S3 bucket.

After that, you should be able to access the app at the API Gateway path by entering the credentials set in the environment
variables file as `HTTP_HOST` and `HTTP_PASS`.