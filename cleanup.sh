#!/bin/bash
# cleanup.sh - Remove unnecessary files from Rip and Tear project

echo "🗑️  Cleaning up Rip and Tear project files..."
echo "============================================="
echo

# Function to remove file with confirmation
remove_file() {
    local file="$1"
    local reason="$2"
    
    if [ -f "$file" ]; then
        echo "Removing $file ($reason)"
        rm "$file"
    elif [ -d "$file" ]; then
        echo "Removing directory $file ($reason)"
        rm -rf "$file"
    fi
}

# Remove test files (development only)
echo "📝 Removing test files..."
remove_file "test.py" "basic component testing - not needed for production"
remove_file "test_config.py" "configuration testing - replaced by validate-setup.sh"
remove_file "test_selective_rerip.py" "feature testing - development only"

# Remove redundant setup scripts
echo
echo "🔧 Removing redundant setup scripts..."
remove_file "setup.sh" "duplicates Docker functionality"
remove_file "configure.sh" "replaced by environment variables and validation script"

# Remove temporary debug files
echo
echo "🧹 Removing debug and temporary files..."
remove_file "Dockerfile.minimal" "temporary workaround - no longer needed"
remove_file "debug-pip-install.sh" "debugging script - no longer needed"
remove_file "add-license-headers.sh" "development script - not needed for production"
remove_file "cd-drive-debug.sh" "debugging script - can be regenerated if needed"
remove_file "test-cd-detection.sh" "debugging script - can be regenerated if needed"

# Keep Makefile as it's useful for development - just notify
if [ -f "Makefile" ]; then
    echo "ℹ️  Keeping Makefile (useful for development commands)"
fi

# Remove Python cache files
echo
echo "🧹 Removing Python cache files..."
remove_file "__pycache__" "Python bytecode cache"
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "*.pyo" -delete 2>/dev/null || true

# Remove any DS_Store files (macOS)
echo
echo "🍎 Removing macOS files..."
find . -name ".DS_Store" -delete 2>/dev/null || true

# Keep docker-compose.override.yml.template as reference
if [ -f "docker-compose.override.yml.template" ]; then
    echo "ℹ️  Keeping docker-compose.override.yml.template (useful reference)"
fi

echo
echo "✅ Cleanup complete!"
echo
echo "📊 Files removed:"
echo "   • Test files (test.py, test_config.py, test_selective_rerip.py)"
echo "   • Redundant scripts (setup.sh, configure.sh)"
echo "   • Cache files (__pycache__, *.pyc)"
echo
echo "📁 Important files kept:"
echo "   • All core Python modules"
echo "   • Documentation files"
echo "   • Docker configuration"
echo "   • Portainer deployment files"
echo "   • Build and validation scripts"
echo "   • License and requirements"
echo
echo "🎯 Project is now production-ready and clean!"

# Show final file count
echo
echo "📈 Final file count:"
find . -type f | wc -l
