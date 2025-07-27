#!/usr/bin/env python3
"""
Simple test script for MusicBrainz disc ID lookup
"""

import musicbrainzngs as mb
import logging

# Enable logging to see what's happening
logging.basicConfig(level=logging.DEBUG)

# Set user agent
mb.set_useragent("Rip-and-Tear-Test", "1.0", "test@example.com")

def test_basic_lookup():
    print("Testing basic MusicBrainz connection...")
    
    try:
        # Test with a well-known disc ID
        test_disc_id = "49HHV7Eb8UKF3aQiNmu1GR8vKTY-"
        print(f"Looking up disc ID: {test_disc_id}")
        
        result = mb.get_releases_by_discid(
            id=test_disc_id,
            includes=['artists'],
            cdstubs=True
        )
        
        print(f"Result keys: {list(result.keys())}")
        
        if 'disc' in result:
            print("✓ Found disc data")
            disc_data = result['disc']
            releases = disc_data.get('release-list', [])
            print(f"Found {len(releases)} releases")
            
        elif 'release-list' in result:
            print("✓ Found fuzzy match releases")
            releases = result['release-list']
            print(f"Found {len(releases)} fuzzy releases")
            
        elif 'cdstub' in result:
            print("✓ Found CD stub")
            cdstub = result['cdstub']
            print(f"CD Stub: {cdstub}")
            
        else:
            print("✗ No data found")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_basic_lookup()
