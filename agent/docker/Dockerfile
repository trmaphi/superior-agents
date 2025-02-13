# Dockerfile
FROM python:3.11-slim

# Install system dependencies and utilities
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    iputils-ping \
    net-tools \
    procps \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt /requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /requirements.txt
RUN pip install ddgr

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command that keeps container running
CMD ["sleep", "infinity"]