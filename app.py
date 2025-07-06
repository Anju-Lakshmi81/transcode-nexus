from flask import Flask, request, send_file, render_template, abort
import subprocess
import os
import time

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB

UPLOAD_FOLDER = 'uploads'
CONVERTED_FOLDER = 'converted'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CONVERTED_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'webm'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_old_files(folder, age_limit_minutes=30):
    now = time.time()
    for filename in os.listdir(folder):
        filepath = os.path.join(folder, filename)
        if os.path.isfile(filepath):
            age_seconds = now - os.path.getmtime(filepath)
            if age_seconds > age_limit_minutes * 60:
                os.remove(filepath)

@app.route('/', methods=['GET', 'POST'])
def upload_and_convert():
    clean_old_files(UPLOAD_FOLDER)
    clean_old_files(CONVERTED_FOLDER)

    if request.method == 'POST':
        video = request.files['video']
        if video.filename == '' or not allowed_file(video.filename):
            error_msg = "Invalid file type. Please upload only mp4, avi, mov, or webm files."
            return render_template('index.html', error=error_msg)

        format = request.form.get('format', 'avi')
        try:
            compression = float(request.form.get('compression', '1'))
        except ValueError:
            compression = 1

        input_path = os.path.join(UPLOAD_FOLDER, video.filename)
        video.save(input_path)

        output_filename = f"{os.path.splitext(video.filename)[0]}_converted.{format}"
        output_path = os.path.join(CONVERTED_FOLDER, output_filename)

        crf = int((1 - compression) * 40)
        crf = max(0, min(crf, 40))  # ensure between 0–40

        subprocess.run([
            'ffmpeg', '-i', input_path,
            '-vcodec', 'libx264', '-crf', str(crf),
            output_path
        ])

        size = os.path.getsize(output_path) / (1024 * 1024)
        success_msg = f"✅ Conversion successful! File size: {size:.2f} MB"
        download_link = f"/download/{output_filename}"
        return render_template('index.html', success=success_msg, download_link=download_link)

    return render_template('index.html')

@app.route('/download/<filename>')
def download_file(filename):
    path = os.path.join(CONVERTED_FOLDER, filename)
    return send_file(path, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
