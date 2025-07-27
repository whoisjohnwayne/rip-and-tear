FROM alpine:3.18

# Install all system dependencies including build tools
RUN apk update && \
    apk add --no-cache \
        python3 \
        py3-pip \
        bash \
        curl \
        tini \
        shadow \
        su-exec \
        udev \
        util-linux \
        # Audio tools
        libcdio-paranoia \
        flac \
        cdrkit \
        libcdio \
        libcdio-dev \
        libdiscid \
        libdiscid-dev \
        cdrdao \
        cd-discid \
        # Build dependencies (permanent for Python packages that need compilation)
        gcc \
        g++ \
        musl-dev \
        python3-dev \
        linux-headers \
        libffi-dev \
        openssl-dev \
        rust \
        cargo \
        pkgconfig \
        make

# Create python symlink and upgrade pip
RUN ln -sf python3 /usr/bin/python && \
    python3 -m pip install --upgrade pip setuptools wheel

# Create app directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python packages with comprehensive error handling
RUN set -e && \
    echo "Installing Python packages from requirements.txt..." && \
    export PIP_DEFAULT_TIMEOUT=300 && \
    export PIP_RETRIES=3 && \
    pip3 install --no-cache-dir --verbose --timeout 300 --retries 3 -r requirements.txt || { \
        echo "Failed to install all packages, trying individually:"; \
        echo "Installing flask..."; \
        pip3 install --no-cache-dir --verbose flask || echo "flask failed"; \
        echo "Installing requests..."; \
        pip3 install --no-cache-dir --verbose requests || echo "requests failed"; \
        echo "Installing pyyaml..."; \
        pip3 install --no-cache-dir --verbose pyyaml || echo "pyyaml failed"; \
        echo "Installing musicbrainzngs..."; \
        pip3 install --no-cache-dir --verbose musicbrainzngs || echo "musicbrainzngs failed"; \
        echo "Installing mutagen..."; \
        pip3 install --no-cache-dir --verbose mutagen || echo "mutagen failed"; \
        echo "Installing psutil..."; \
        pip3 install --no-cache-dir --verbose psutil || echo "psutil failed"; \
        echo "Installing watchdog..."; \
        pip3 install --no-cache-dir --verbose watchdog || echo "watchdog failed"; \
    }

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
