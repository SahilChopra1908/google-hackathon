# Use an official small Python image
FROM python:3.11-slim

# Install apt packages needed for Chrome and for selenium to run
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    unzip \
    fonts-liberation \
    libnss3 \
    libglib2.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxss1 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxrandr2 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxfixes3 \
    libxrender1 \
    libgbm1 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Install Chromium and Chromedriver (Debian packages)
# Chromium package name may differ by distro; Debian slim provides chromium.
RUN apt-get update && apt-get install -y chromium chromium-driver && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and source
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Set environment variables used by selenium in app
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PORT=8080

# Use functions-framework to expose your function "linkedin_lookup"
# Cloud Run expects HTTP on port from $PORT
ENTRYPOINT ["functions-framework", "--target=linkedin_lookup", "--port=8080"]

