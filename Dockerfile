# Lightweight Python 3.9 image suitable for Cloud Run
FROM python:3.9-slim

# Create app directory
WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py ./app.py
COPY templates ./templates

# Start the server
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
