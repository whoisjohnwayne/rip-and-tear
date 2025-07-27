#!/usr/bin/env python3
"""
Test script to verify MusicBrainz disc ID lookup
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from metadata_fetcher import MetadataFetcher

def test_disc_id_lookup():
    # Create a test instance
    config = {"disable_metadata": False}
    fetcher = MetadataFetcher(config)
    
    # Test with a known disc ID (this is just a test format)
    test_disc_id = "49HHV7Eb8UKF3aQiNmu1GR8vKTY-"
    print(f"Testing disc ID lookup for: {test_disc_id}")
    
    try:
        result = fetcher._search_by_disc_id(test_disc_id)
        if result:
            print("✓ Disc ID lookup successful!")
            print(f"Found: {result.get('album', 'Unknown')} by {result.get('artist', 'Unknown')}")
        else:
            print("✗ No results found for disc ID")
    except Exception as e:
        print(f"✗ Error during lookup: {e}")

if __name__ == "__main__":
    test_disc_id_lookup()
