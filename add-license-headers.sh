#!/bin/bash
# add-license-headers.sh - Add MIT license headers to Python files

LICENSE_HEADER="# Copyright (c) 2025 Rip and Tear Contributors
# Licensed under the MIT License - see LICENSE file for details"

echo "Adding license headers to Python files..."

# List of Python files to update (excluding test files and generated files)
PYTHON_FILES=(
    "cd_ripper.py"
    "accuraterip_checker.py" 
    "config_manager.py"
    "web_gui.py"
    "cd_monitor.py"
    "metadata_fetcher.py"
    "toc_analyzer.py"
)

for file in "${PYTHON_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "Processing $file..."
        
        # Check if license header already exists
        if grep -q "Licensed under the MIT License" "$file"; then
            echo "  License header already exists, skipping"
        else
            # Find the first """ line and add license after it
            if grep -q '"""' "$file"; then
                # Create temporary file with license header added
                awk '
                    /^"""/ && !found {
                        print $0
                        print ""
                        print "'"$LICENSE_HEADER"'"
                        found=1
                        next
                    }
                    { print $0 }
                ' "$file" > "${file}.tmp"
                
                mv "${file}.tmp" "$file"
                echo "  ✅ License header added"
            else
                echo "  ⚠️  No docstring found, skipping"
            fi
        fi
    else
        echo "  ❌ File not found: $file"
    fi
done

echo "Done! License headers have been added to Python files."
