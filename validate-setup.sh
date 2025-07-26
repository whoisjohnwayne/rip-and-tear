#!/bin/bash
# validate-setup.sh - Validate host environment for Rip and Tear deployment

echo "🔍 Validating Rip and Tear deployment environment..."
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ISSUES=0

# Check if running on Linux
echo "📋 Checking operating system..."
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo -e "✅ ${GREEN}Linux detected${NC}"
else
    echo -e "⚠️  ${YELLOW}Warning: Non-Linux OS detected ($OSTYPE)${NC}"
    echo "   CD drive access may be limited on non-Linux systems"
    ((ISSUES++))
fi

# Check for CD drive devices
echo
echo "💿 Checking for CD drive devices..."
if ls /dev/cdrom /dev/sr* /dev/dvd* 2>/dev/null | head -1 >/dev/null; then
    echo -e "✅ ${GREEN}CD drive devices found:${NC}"
    ls -la /dev/cdrom /dev/sr* /dev/dvd* 2>/dev/null | head -5
else
    echo -e "❌ ${RED}No CD drive devices found${NC}"
    echo "   Expected devices: /dev/cdrom, /dev/sr0, /dev/sr1, etc."
    ((ISSUES++))
fi

# Check Docker
echo
echo "🐳 Checking Docker..."
if command -v docker >/dev/null 2>&1; then
    echo -e "✅ ${GREEN}Docker found: $(docker --version)${NC}"
    
    # Check if Docker daemon is running
    if docker ps >/dev/null 2>&1; then
        echo -e "✅ ${GREEN}Docker daemon is running${NC}"
    else
        echo -e "❌ ${RED}Docker daemon is not running${NC}"
        ((ISSUES++))
    fi
else
    echo -e "❌ ${RED}Docker not found${NC}"
    ((ISSUES++))
fi

# Check for cdparanoia (optional, for testing)
echo
echo "🎵 Checking audio tools..."
if command -v cdparanoia >/dev/null 2>&1; then
    echo -e "✅ ${GREEN}cdparanoia found (can test CD access)${NC}"
    
    # Test CD access if a disc is inserted
    if cdparanoia -Q 2>/dev/null | grep -q "tracks"; then
        echo -e "✅ ${GREEN}CD detected and accessible${NC}"
        cdparanoia -Q 2>/dev/null | head -3
    else
        echo -e "ℹ️  ${YELLOW}No CD detected (insert a CD to test)${NC}"
    fi
else
    echo -e "ℹ️  ${YELLOW}cdparanoia not found (install to test CD access)${NC}"
fi

# Check network connectivity
echo
echo "🌐 Checking network connectivity..."
if curl -s --max-time 5 https://musicbrainz.org >/dev/null; then
    echo -e "✅ ${GREEN}MusicBrainz accessible${NC}"
else
    echo -e "⚠️  ${YELLOW}Warning: Cannot reach MusicBrainz${NC}"
    echo "   Metadata fetching may not work"
fi

if curl -s --max-time 5 http://www.accuraterip.com >/dev/null; then
    echo -e "✅ ${GREEN}AccurateRip accessible${NC}"
else
    echo -e "⚠️  ${YELLOW}Warning: Cannot reach AccurateRip${NC}"
    echo "   Verification may not work"
fi

# Check available space
echo
echo "💾 Checking available disk space..."
AVAILABLE=$(df / | awk 'NR==2 {print $4}')
if [ "$AVAILABLE" -gt 1048576 ]; then  # 1GB in KB
    echo -e "✅ ${GREEN}Sufficient disk space available${NC}"
else
    echo -e "⚠️  ${YELLOW}Warning: Low disk space ($(($AVAILABLE/1024))MB available)${NC}"
    echo "   Consider freeing space or using bind mounts to other drives"
fi

# Summary
echo
echo "📊 Validation Summary:"
if [ $ISSUES -eq 0 ]; then
    echo -e "🎉 ${GREEN}All checks passed! Ready for deployment.${NC}"
    echo
    echo "Next steps:"
    echo "1. Build and push your Docker image"
    echo "2. Update docker-compose.portainer.yml with your image name"
    echo "3. Set CONTACT_EMAIL environment variable"
    echo "4. Deploy in Portainer"
else
    echo -e "⚠️  ${YELLOW}Found $ISSUES potential issues${NC}"
    echo "Please review the warnings above before deployment."
fi

echo
echo "📖 See PRE_DEPLOYMENT_CHECKLIST.md for detailed requirements"
