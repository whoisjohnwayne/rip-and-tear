#!/bin/bash
# test-cd-detection.sh - Test CD detection inside container

echo "🔍 Testing CD Detection in Container"
echo "===================================="
echo

echo "1. 📀 Checking CD device access..."
if [ -e "/dev/cdrom" ]; then
    echo "✅ /dev/cdrom exists"
    ls -la /dev/cdrom
else
    echo "❌ /dev/cdrom not found"
    echo "Available devices:"
    ls -la /dev/sr* /dev/cd* 2>/dev/null || echo "No CD devices found"
fi
echo

echo "2. 🎵 Testing cd-paranoia..."
if command -v cd-paranoia >/dev/null 2>&1; then
    echo "✅ cd-paranoia is available"
    echo "Testing CD query (insert a CD first):"
    timeout 10s cd-paranoia -Q -d /dev/cdrom 2>&1 | head -10
else
    echo "❌ cd-paranoia not found"
fi
echo

echo "3. 🆔 Testing cd-discid..."
if command -v cd-discid >/dev/null 2>&1; then
    echo "✅ cd-discid is available"
    echo "Testing disc ID (insert a CD first):"
    timeout 10s cd-discid /dev/cdrom 2>&1 || echo "No disc or disc not readable"
else
    echo "❌ cd-discid not found"
fi
echo

echo "4. 📋 Container environment..."
echo "CD_DEVICE environment: ${CD_DEVICE:-/dev/cdrom}"
echo "Container privileges:"
cat /proc/self/status | grep -E "(CapInh|CapPrm|CapEff)" 2>/dev/null || echo "Cannot read capabilities"
echo

echo "5. 🔄 Testing Python CD monitor..."
echo "Running a quick CD detection test:"
python3 -c "
import subprocess
import sys

device = '/dev/cdrom'
print(f'Testing device: {device}')

try:
    # Test cd-paranoia
    result = subprocess.run(['cd-paranoia', '-Q', '-d', device], 
                          capture_output=True, text=True, timeout=5)
    
    if result.returncode == 0 and 'track' in result.stderr.lower():
        print('✅ CD detected by cd-paranoia')
        
        # Test cd-discid
        try:
            result2 = subprocess.run(['cd-discid', device], 
                                   capture_output=True, text=True, timeout=5)
            if result2.returncode == 0:
                disc_id = result2.stdout.strip().split()[0]
                print(f'✅ Disc ID: {disc_id}')
            else:
                print('⚠️ cd-discid failed but CD detected')
        except Exception as e:
            print(f'⚠️ cd-discid error: {e}')
    else:
        print('❌ No CD detected by cd-paranoia')
        print(f'Return code: {result.returncode}')
        print(f'Stderr: {result.stderr[:200]}')
        
except Exception as e:
    print(f'❌ Error testing CD: {e}')
"
echo

echo "✅ CD detection test complete!"
echo "If errors appear above, check:"
echo "  - Container is running with --privileged"
echo "  - /dev/cdrom is properly mounted"
echo "  - A readable CD is inserted"
