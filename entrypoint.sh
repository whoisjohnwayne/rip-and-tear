#!/bin/bash
set -e

# Initialize configuration if it doesn't exist
if [ ! -f /config/config.yaml ]; then
    cp /app/config/default_config.yaml /config/config.yaml
    echo "Created default configuration in /config/config.yaml"
fi

# Create output and log directories if they don't exist
mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

# Start udev for device detection
if [ ! -d /run/udev ]; then
    mkdir -p /run/udev
fi

# Start the CD ripper daemon
echo "Starting Rip and Tear..."
python3 /app/main.py
