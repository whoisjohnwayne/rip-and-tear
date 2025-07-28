#!/bin/bash
# cd-paranoia-debug.sh - Debug script to see actual cd-paranoia output

echo "🔍 Debugging cd-paranoia output format..."
echo "========================================"

# Check if cd-paranoia is available
if ! command -v cd-paranoia &> /dev/null; then
    echo "❌ cd-paranoia not found - this script must run in Docker container"
    exit 1
fi

# Check if device exists
DEVICE=${CD_DEVICE:-/dev/sr0}
if [ ! -e "$DEVICE" ]; then
    echo "❌ CD device $DEVICE not found"
    echo "Available devices:"
    ls -la /dev/sr* /dev/cdrom* 2>/dev/null || echo "No CD devices found"
    exit 1
fi

echo "📀 Testing cd-paranoia with device: $DEVICE"
echo

# Test cd-paranoia -Q command and capture ALL output
echo "=== cd-paranoia -Q OUTPUT ==="
echo "Command: cd-paranoia -Q -d $DEVICE"
echo
echo "STDOUT:"
cd-paranoia -Q -d "$DEVICE" 2>cd-paranoia_stderr.log || echo "Command failed with exit code $?"
echo
echo "STDERR:"
cat cd-paranoia_stderr.log
echo
echo "=== END OUTPUT ==="

# Also test without -d flag
echo
echo "=== cd-paranoia -Q (no device flag) OUTPUT ==="
echo "Command: cd-paranoia -Q"
echo
echo "STDOUT:"
cd-paranoia -Q 2>cd-paranoia_stderr_nodev.log || echo "Command failed with exit code $?"
echo
echo "STDERR:"
cat cd-paranoia_stderr_nodev.log
echo
echo "=== END OUTPUT ==="

# Test cd-info as alternative
echo
echo "=== CD-INFO OUTPUT ==="
if command -v cd-info &> /dev/null; then
    echo "Command: cd-info $DEVICE"
    cd-info "$DEVICE" 2>&1 || echo "cd-info failed"
else
    echo "cd-info not available"
fi
echo

# Clean up
rm -f cd-paranoia_stderr.log cd-paranoia_stderr_nodev.log

echo "✅ Debug complete - check output above for actual cd-paranoia format"
