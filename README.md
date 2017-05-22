# Watson Speech-to-Text Wrapper

Light GUI for uploading audio recordings to an S3 bucket, getting them transcribed
through IBM Watson's speech-to-text service, and downloading results.

## Audio Conversion

The Lambda function currently uses `ffmpeg` to convert audio to FLAC format. You'll need to download a binary from
https://www.johnvansickle.com/ffmpeg/ and add it to the `lib/` directory for it to work.