# Use official Python image
FROM python:3.10-slim

# Install FFmpeg and other deps
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean

# Set work directory
WORKDIR /app

# Copy code
COPY . /app

# Install Python packages
RUN pip install --upgrade flask boto3

# Expose Flask port
EXPOSE 5000

# Start the app
CMD ["python", "app.py"]
