FROM alpine:latest

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    cdparanoia \
    flac \
    curl \
    udev \
    dbus \
    util-linux \
    cdrtools \
    libcdio \
    libcdio-paranoia \
    libcdio-utils \
    cd-discid \
    bash \
    && ln -sf python3 /usr/bin/python

# Install cdrdao for .cue support and advanced gap detection
RUN apk add --no-cache cdrdao

# Create app directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

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
