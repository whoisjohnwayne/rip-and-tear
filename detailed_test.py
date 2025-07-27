#!/usr/bin/env python3
"""
Detailed test script for MusicBrainz disc ID lookup
"""

import musicbrainzngs as mb
import json

# Set user agent
mb.set_useragent("Rip-and-Tear-Test", "1.0", "test@example.com")

def test_detailed_lookup():
    test_disc_id = "49HHV7Eb8UKF3aQiNmu1GR8vKTY-"
    print(f"Looking up disc ID: {test_disc_id}")
    
    try:
        result = mb.get_releases_by_discid(
            id=test_disc_id,
            includes=['artists', 'recordings', 'release-groups'],
            cdstubs=True
        )
        
        print("=== FULL RESULT ===")
        print(json.dumps(result, indent=2, default=str))
        
        if 'disc' in result:
            disc_data = result['disc']
            release_list = disc_data.get('release-list', [])
            if release_list:
                release = release_list[0]
                print("\n=== FIRST RELEASE ===")
                print(f"Title: {release.get('title', 'Unknown')}")
                print(f"ID: {release.get('id', 'Unknown')}")
                
                artist_credit = release.get('artist-credit', [])
                if artist_credit:
                    artist_name = artist_credit[0].get('name', 'Unknown Artist')
                    print(f"Artist: {artist_name}")
                    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_detailed_lookup()
