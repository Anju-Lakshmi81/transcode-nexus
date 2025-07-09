import os
import subprocess
import boto3
from botocore.client import Config
import time

S3_BUCKET = "transcode-nexus-storage"
region = "ap-south-1"

s3_client = boto3.client(
    's3',
    region_name=region,
    aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
    aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
    config=Config(signature_version='s3v4')
)

def calculate_crf(compression):
    crf = int((1 - compression) * 40)
    return max(0, min(crf, 40))

from celery import Celery
app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')

@app.task(name='tasks.convert_video_task')
def convert_video_task(filename, format, email, compression):
    input_path = f"/tmp/{filename}"
    output_filename = f"{os.path.splitext(filename)[0]}_converted.{format}"
    output_path = f"/tmp/{output_filename}"

    crf = calculate_crf(compression)

    subprocess.run([
        'ffmpeg', '-i', input_path,
        '-vcodec', 'libx264', '-crf', str(crf),
        output_path
    ])

    s3_client.upload_file(output_path, S3_BUCKET, f"converted/{output_filename}")

    # Generate presigned URL for downloading
    url = s3_client.generate_presigned_url(
        ClientMethod='get_object',
        Params={'Bucket': S3_BUCKET, 'Key': f"converted/{output_filename}"},
        ExpiresIn=3600
    )

    # (Optional) Send email (if email != "")
    if email:
        import smtplib
        from email.mime.text import MIMEText

        from_email = os.environ['EMAIL_ADDRESS']
        password = os.environ['EMAIL_PASSWORD']

        msg = MIMEText(f"✅ Your video has been converted.\n\nClick to download: {url}")
        msg['Subject'] = "✅ Transcode Nexus: Video Ready"
        msg['From'] = from_email
        msg['To'] = email

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(from_email, password)
        server.send_message(msg)
        server.quit()

    return url

