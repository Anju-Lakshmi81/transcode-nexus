from celery import Celery
import os
import boto3
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from botocore.client import Config

# Redis broker
celery = Celery('tasks', broker='redis://redis:6379/0')

# AWS + Email setup
S3_BUCKET = "transcode-nexus-storage"
s3_client = boto3.client(
    's3',
    region_name='ap-south-1',
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
    config=Config(signature_version='s3v4')
)

def send_email(to_email, url):
    from_email = os.environ['EMAIL_ADDRESS']
    password = os.environ['EMAIL_PASSWORD']
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = '✅ Your video is ready!'
    msg.attach(MIMEText(f"Download here:\n{url}", 'plain'))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())

@celery.task
def convert_video_task(filename, format, email, compression):
    input_path = f"/tmp/{filename}"
    output_filename = f"{os.path.splitext(filename)[0]}_converted.{format}"
    output_path = f"/tmp/{output_filename}"

    if format == 'webm':
        ffmpeg_cmd = ['ffmpeg', '-i', input_path, '-c:v', 'libvpx', '-b:v', '1M', '-c:a', 'libopus', output_path]
    else:
        crf = int((1 - float(compression)) * 40)
        crf = max(0, min(crf, 40))
        ffmpeg_cmd = ['ffmpeg', '-i', input_path, '-vcodec', 'libx264', '-crf', str(crf), '-acodec', 'libmp3lame', output_path]

    subprocess.run(ffmpeg_cmd)
    s3_client.upload_file(output_path, S3_BUCKET, f"converted/{output_filename}")

    url = s3_client.generate_presigned_url(
        ClientMethod='get_object',
        Params={'Bucket': S3_BUCKET, 'Key': f"converted/{output_filename}"},
        ExpiresIn=3600
    )
    send_email(email, url)
