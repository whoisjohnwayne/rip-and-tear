#!/usr/bin/env python3
"""
Test script to verify Rip and Tear components
"""

import sys
import subprocess
import importlib
from pathlib import Path

def test_imports():
    """Test that all required Python modules can be imported"""
    required_modules = [
        'flask',
        'requests', 
        'musicbrainzngs',
        'yaml',
        'logging',
        'threading',
        'pathlib'
    ]
    
    print("Testing Python imports...")
    failed_imports = []
    
    for module in required_modules:
        try:
            importlib.import_module(module)
            print(f"✅ {module}")
        except ImportError as e:
            print(f"❌ {module}: {e}")
            failed_imports.append(module)
    
    return len(failed_imports) == 0

def test_system_tools():
    """Test that required system tools are available"""
    required_tools = [
        'cd-paranoia',
        'flac',
        'python3'
    ]
    
    print("\nTesting system tools...")
    failed_tools = []
    
    for tool in required_tools:
        try:
            result = subprocess.run(['which', tool], 
                                  capture_output=True, 
                                  text=True)
            if result.returncode == 0:
                print(f"✅ {tool}: {result.stdout.strip()}")
            else:
                print(f"❌ {tool}: not found")
                failed_tools.append(tool)
        except Exception as e:
            print(f"❌ {tool}: {e}")
            failed_tools.append(tool)
    
    return len(failed_tools) == 0

def test_file_structure():
    """Test that all required files exist"""
    required_files = [
        'main.py',
        'cd_ripper.py',
        'config_manager.py',
        'metadata_fetcher.py',
        'web_gui.py',
        'cd_monitor.py',
        'accuraterip_checker.py',
        'cue_generator.py',
        'Dockerfile',
        'requirements.txt',
        'entrypoint.sh',
        'templates/index.html',
        'config/default_config.yaml'
    ]
    
    print("\nTesting file structure...")
    missing_files = []
    
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path}: missing")
            missing_files.append(file_path)
    
    return len(missing_files) == 0

def main():
    """Run all tests"""
    print("Rip and Tear Component Test")
    print("=" * 40)
    
    all_passed = True
    
    # Test imports
    if not test_imports():
        all_passed = False
        print("\n⚠️  Some Python modules are missing. Run: pip install -r requirements.txt")
    
    # Test system tools  
    if not test_system_tools():
        all_passed = False
        print("\n⚠️  Some system tools are missing. Install them using your package manager.")
    
    # Test file structure
    if not test_file_structure():
        all_passed = False
        print("\n⚠️  Some required files are missing.")
    
    print("\n" + "=" * 40)
    
    if all_passed:
        print("🎉 All tests passed! Rip and Tear is ready to use.")
        print("\nNext steps:")
        print("1. Run: ./setup.sh")
        print("2. Run: docker-compose up -d")
        print("3. Open: http://localhost:8080")
    else:
        print("❌ Some tests failed. Please fix the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
