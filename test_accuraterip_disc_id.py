#!/usr/bin/env python3
"""
Test AccurateRip disc ID calculation for Porcupine Tree - Fear of a Blank Planet
"""

def test_accuraterip_disc_id():
    """Test with the actual track data from the logs"""
    
    # Track data from logs
    tracks = [
        {'start_sector': 0, 'length_sectors': 33607},
        {'start_sector': 33607, 'length_sectors': 23066},
        {'start_sector': 56673, 'length_sectors': 79695},
        {'start_sector': 136368, 'length_sectors': 24489},
        {'start_sector': 160857, 'length_sectors': 34326},
        {'start_sector': 195183, 'length_sectors': 33847},
    ]
    
    # Calculate track offsets (with 150 sector offset)
    track_offsets = []
    for track in tracks:
        offset = track['start_sector'] + 150
        track_offsets.append(offset)
    
    # Add leadout
    last_track = tracks[-1]
    leadout = last_track['start_sector'] + last_track['length_sectors'] + 150
    track_offsets.append(leadout)
    
    print(f"Track offsets: {track_offsets}")
    print(f"Number of tracks: {len(tracks)}")
    print(f"Leadout: {leadout}")
    
    # Test FreeDB calculation (like our current implementation)
    def calculate_freedb_disc_id(track_offsets):
        tracks = track_offsets[:-1]  # Exclude leadout
        leadout = track_offsets[-1]
        num_tracks = len(tracks)
        
        # Calculate checksum - sum of track start times in seconds, mod 255
        checksum = 0
        for offset in tracks:
            start_seconds = offset // 75
            while start_seconds > 0:
                checksum += start_seconds % 10
                start_seconds //= 10
        checksum = checksum % 255
        
        # Calculate total time - from first track to leadout in seconds
        total_seconds = (leadout - tracks[0]) // 75
        
        # Build FreeDB disc ID: XXYYYYZZ
        disc_id = (checksum << 24) | ((total_seconds & 0xFFFF) << 8) | num_tracks
        return disc_id
    
    freedb_id = calculate_freedb_disc_id(track_offsets)
    print(f"FreeDB disc ID: {freedb_id:08X}")
    
    # Test if we need RAW track offsets (without 150 offset)
    raw_offsets = []
    for track in tracks:
        raw_offsets.append(track['start_sector'])
    raw_offsets.append(last_track['start_sector'] + last_track['length_sectors'])
    
    raw_freedb_id = calculate_freedb_disc_id(raw_offsets)
    print(f"Raw FreeDB disc ID: {raw_freedb_id:08X}")
    
    # Test MSF conversion
    def sectors_to_msf(sectors):
        minutes = sectors // (75 * 60)
        seconds = (sectors % (75 * 60)) // 75
        frames = sectors % 75
        return f"{minutes:02d}:{seconds:02d}:{frames:02d}"
    
    print("\nMSF format:")
    for i, offset in enumerate(track_offsets[:-1]):
        print(f"Track {i+1}: {sectors_to_msf(offset)} (sector {offset})")
    print(f"Leadout: {sectors_to_msf(leadout)} (sector {leadout})")
    
    # Check what we got in the logs vs expected
    print(f"\nFrom logs: Calculated disc IDs: 420BED06, 00698BAC, 42B0089A")
    print(f"Our calculation: {freedb_id:08X}")
    print(f"Raw calculation: {raw_freedb_id:08X}")

if __name__ == "__main__":
    test_accuraterip_disc_id()
