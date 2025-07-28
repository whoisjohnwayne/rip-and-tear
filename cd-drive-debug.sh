#!/bin/bash
# cd-drive-debug.sh - Debug CD drive detection issues

echo "🔍 CD Drive Debugging Script"
echo "============================"
echo

echo "1. 📀 Checking for CD devices..."
echo "Available CD/DVD devices:"
ls -la /dev/cdrom* /dev/sr* /dev/dvd* 2>/dev/null || echo "No standard CD devices found"
echo

echo "2. 🔧 Checking if running in container..."
if [ -f /.dockerenv ]; then
    echo "✅ Running inside Docker container"
    echo "Container privileges:"
    cat /proc/self/status | grep -E "(CapInh|CapPrm|CapEff)" || echo "Cannot read capabilities"
else
    echo "❌ Running on host system"
fi
echo

echo "3. 🎵 Testing cd-paranoia..."
if command -v cd-paranoia >/dev/null 2>&1; then
    echo "✅ cd-paranoia is available"
    echo "Testing CD detection with cd-paranoia..."
    
    # Try different device paths
    for device in /dev/cdrom /dev/sr0 /dev/sr1 /dev/dvd; do
        if [ -e "$device" ]; then
            echo "Testing device: $device"
            timeout 10s cd-paranoia -Q -d "$device" 2>&1 | head -10
            echo "---"
        fi
    done
else
    echo "❌ cd-paranoia not found"
fi
echo

echo "4. 🔍 Checking mount points..."
echo "Currently mounted CD/DVD devices:"
mount | grep -E "(cd|dvd|sr[0-9])" || echo "No CD/DVD devices mounted"
echo

echo "5. 📋 Checking udev and device permissions..."
echo "Device permissions:"
ls -la /dev/cdrom* /dev/sr* 2>/dev/null || echo "No devices to check"
echo

echo "6. 🐳 Docker-specific checks..."
if [ -f /.dockerenv ]; then
    echo "Checking if devices are mounted in container:"
    ls -la /dev/ | grep -E "(cdrom|sr[0-9]|dvd)" || echo "No CD devices found in container"
    
    echo "Checking container volumes:"
    mount | grep -E "/dev|/config|/output|/logs"
fi
echo

echo "7. 💡 Suggestions:"
echo "If you're running in Docker:"
echo "  - Make sure to use --privileged flag"
echo "  - Mount /dev:/dev or specific devices like /dev/sr0:/dev/sr0"
echo "  - Check that CD device exists on host: ls -la /dev/sr*"
echo "  - Verify container has access: docker exec <container> ls -la /dev/sr*"
echo

echo "If running on macOS:"
echo "  - CD drives typically appear as /dev/disk* rather than /dev/sr*"
echo "  - Use 'diskutil list' to find CD drive"
echo "  - May need different detection method for macOS"
echo

echo "✅ Debug complete!"
