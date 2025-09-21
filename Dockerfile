# Use official Python image
FROM python:3.11-slim

# Set environment vars
ENV PYTHONUNBUFFERED=True \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

# Set workdir
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Expose Cloud Run port
EXPOSE 8080

# Start Flask app

