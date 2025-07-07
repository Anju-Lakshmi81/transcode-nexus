from flask import Flask, request, render_template
import subprocess
import os
import time
import smtplib
import boto3
from botocore.client import Config
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB

# AWS S3 setup
S3_BUCKET = "transcode-nexus-storage"

s3_client = boto3.client(
    's3',
    region_name='ap-south-1',
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
    config=Config(signature_version='s3v4')
)

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'webm'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_old_s3_files(prefix, age_limit_minutes=30):
    objects = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    if 'Contents' in objects:
        for obj in objects['Contents']:
            age = time.time() - obj['LastModified'].timestamp()
            if age > age_limit_minutes * 60:
                s3_client.delete_object(Bucket=S3_BUCKET, Key=obj['Key'])

def send_email(to_email, download_url):
    from_email = os.environ['EMAIL_ADDRESS']
    password = os.environ['EMAIL_PASSWORD']

    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = '✅ Your Video is Ready to Download!'

    body = f"Hi,\n\nYour converted video is ready:\n{download_url}\n\nLink valid for 1 hour."
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())

@app.route('/', methods=['GET', 'POST'])
def upload_and_convert():
    clean_old_s3_files('uploads/')
    clean_old_s3_files('converted/')

    if request.method == 'POST':
        video = request.files.get('video')
        if not video or not allowed_file(video.filename):
            return render_template('index.html', error="❌ Invalid file type. Please upload .mp4, .avi, .mov, or .webm.")

        format = request.form.get('format', 'avi')
        email = request.form.get('email')

        try:
            compression = float(request.form.get('compression', '1'))
        except ValueError:
            compression = 1

        filename = secure_filename(video.filename)
        input_path = f"/tmp/{filename}"
        video.save(input_path)

        # Upload original to S3
        s3_client.upload_file(input_path, S3_BUCKET, f"uploads/{filename}")

        output_filename = f"{os.path.splitext(filename)[0]}_converted.{format}"
        output_path = f"/tmp/{output_filename}"

        crf = int((1 - compression) * 40)
        crf = max(0, min(crf, 40))

        if format == 'webm':
            ffmpeg_cmd = [
                'ffmpeg', '-i', input_path,
                '-c:v', 'libvpx', '-b:v', '1M',
                '-c:a', 'libopus',
                output_path
            ]
        else:
            ffmpeg_cmd = [
                'ffmpeg', '-i', input_path,
                '-vcodec', 'libx264', '-crf', str(crf),
                output_path
            ]

        subprocess.run(ffmpeg_cmd)

        # Upload converted file to S3
        s3_client.upload_file(output_path, S3_BUCKET, f"converted/{output_filename}")

        # Generate signed URL
        url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': S3_BUCKET, 'Key': f"converted/{output_filename}"},
            ExpiresIn=3600
        )

        print("Presigned URL:", url)

        # Send email with download link
        if email:
            send_email(email, url)

        size = os.path.getsize(output_path) / (1024 * 1024)
        success_msg = f"✅ Conversion successful! File size: {size:.2f} MB. A download link has been emailed."

        return render_template('index.html', success=success_msg, download_link=url)

    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
