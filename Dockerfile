FROM alpine:3.18

# Update package index
RUN apk update

# Install essential packages
RUN apk add --no-cache \
    python3 \
    py3-pip \
    bash \
    curl \
    gcc \
    musl-dev \
    python3-dev

# Install audio packages (these should exist in Alpine)
RUN apk add --no-cache \
    cdparanoia \
    flac

# Try to install additional tools (fallback if not available)
RUN apk add --no-cache cdrtools || echo "cdrtools not available, continuing..."
RUN apk add --no-cache libcdio || echo "libcdio not available, continuing..."  
RUN apk add --no-cache cdrdao || echo "cdrdao not available, continuing..."

# Create python symlink
RUN ln -sf python3 /usr/bin/python

# Upgrade pip
RUN pip3 install --upgrade pip

# Create app directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python packages with better error handling
RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel
RUN pip3 install --no-cache-dir -r requirements.txt

# Clean up build dependencies to reduce image size
RUN apk del gcc musl-dev python3-dev

# Copy application files
COPY . .

# Create directories for configuration and output
RUN mkdir -p /config /output /logs

# Set permissions
RUN chmod +x /app/entrypoint.sh

# Expose web GUI port
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV OUTPUT_DIR=/output
ENV CONFIG_DIR=/config
ENV LOG_DIR=/logs

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Entry point
ENTRYPOINT ["/app/entrypoint.sh"]
