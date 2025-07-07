from flask import Flask, request, render_template
from werkzeug.utils import secure_filename
import os
import time
import boto3
from botocore.client import Config
from tasks import convert_video_task  # Celery task

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max upload

# AWS S3 config
S3_BUCKET = "transcode-nexus-storage"
s3_client = boto3.client(
    's3',
    region_name='ap-south-1',
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
    config=Config(signature_version='s3v4')
)

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'webm', 'mkv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Auto-delete old files from S3
def clean_old_s3_files(prefix, age_limit_minutes=30):
    objects = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    if 'Contents' in objects:
        for obj in objects['Contents']:
            age = time.time() - obj['LastModified'].timestamp()
            if age > age_limit_minutes * 60:
                s3_client.delete_object(Bucket=S3_BUCKET, Key=obj['Key'])

@app.route('/', methods=['GET', 'POST'])
def upload_and_convert():
    clean_old_s3_files('uploads/')
    clean_old_s3_files('converted/')

    if request.method == 'POST':
        video = request.files.get('video')
        if not video or not allowed_file(video.filename):
            return render_template('index.html', error="❌ Invalid file. Please upload .mp4, .avi, .mov, .webm, or .mkv files only.")

        format = request.form.get('format', 'avi').lower()
        email = request.form.get('email')

        try:
            compression = float(request.form.get('compression', '1'))
        except ValueError:
            compression = 1

        filename = secure_filename(video.filename)
        input_path = f"/tmp/{filename}"
        video.save(input_path)

        # Upload the original to S3
        s3_client.upload_file(input_path, S3_BUCKET, f"uploads/{filename}")

        # Trigger background Celery task
        convert_video_task.delay(filename, format, email, compression)

        return render_template('index.html', success="✅ Upload successful! You’ll receive an email with the download link once the conversion is complete.")

    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

