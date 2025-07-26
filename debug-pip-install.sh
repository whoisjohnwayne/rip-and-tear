#!/bin/bash
# debug-pip-install.sh - Debug pip installation issues

echo "🔍 DEBUGGING PIP INSTALLATION"
echo "=============================="

# Test pip installation locally with Docker
echo "Testing pip packages individually in Alpine container..."

docker run --rm -it alpine:3.18 sh -c '
echo "Setting up environment..."
apk update
apk add --no-cache python3 py3-pip gcc musl-dev python3-dev linux-headers libffi-dev openssl-dev rust cargo
python3 -m pip install --upgrade pip setuptools wheel

echo
echo "Testing individual packages:"

packages=(
    "flask"
    "requests" 
    "pyyaml"
    "musicbrainzngs"
    "mutagen"
    "psutil"
    "watchdog"
)

for pkg in "${packages[@]}"; do
    echo "--- Testing $pkg ---"
    if pip3 install --no-cache-dir --verbose "$pkg"; then
        echo "✅ $pkg installed successfully"
    else
        echo "❌ $pkg failed to install"
    fi
    echo
done
'
