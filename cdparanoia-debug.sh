#!/bin/bash
# cdparanoia-debug.sh - Debug script to see actual cdparanoia output

echo "🔍 Debugging cdparanoia output format..."
echo "========================================"

# Check if cdparanoia is available
if ! command -v cdparanoia &> /dev/null; then
    echo "❌ cdparanoia not found - this script must run in Docker container"
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

echo "📀 Testing cdparanoia with device: $DEVICE"
echo

# Test cdparanoia -Q command and capture ALL output
echo "=== CDPARANOIA -Q OUTPUT ==="
echo "Command: cdparanoia -Q -d $DEVICE"
echo
echo "STDOUT:"
cdparanoia -Q -d "$DEVICE" 2>cdparanoia_stderr.log || echo "Command failed with exit code $?"
echo
echo "STDERR:"
cat cdparanoia_stderr.log
echo
echo "=== END OUTPUT ==="

# Also test without -d flag
echo
echo "=== CDPARANOIA -Q (no device flag) OUTPUT ==="
echo "Command: cdparanoia -Q"
echo
echo "STDOUT:"
cdparanoia -Q 2>cdparanoia_stderr_nodev.log || echo "Command failed with exit code $?"
echo
echo "STDERR:"
cat cdparanoia_stderr_nodev.log
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
rm -f cdparanoia_stderr.log cdparanoia_stderr_nodev.log

echo "✅ Debug complete - check output above for actual cdparanoia format"
