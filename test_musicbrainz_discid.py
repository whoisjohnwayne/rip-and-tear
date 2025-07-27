#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test MusicBrainz disc ID calculation against known examples
"""

import hashlib
import base64

def calculate_musicbrainz_disc_id_manual(track_offsets, leadout_offset):
    """
    Calculate MusicBrainz disc ID manually using official algorithm
    
    Args:
        track_offsets: List of track start offsets (including +150 for lead-in)
        leadout_offset: Lead-out track offset (including +150)
    
    Returns:
        MusicBrainz disc ID string
    """
    
    first_track = 1
    last_track = len(track_offsets)
    
    # Build the hex string for SHA-1 hashing
    hex_string = ""
    
    # First track number (2-digit hex)
    hex_string += "{:02X}".format(first_track)
    
    # Last track number (2-digit hex)
    hex_string += "{:02X}".format(last_track)
    
    # Lead-out track offset (8-digit hex) - this is position 0 in the frame offset array
    hex_string += "{:08X}".format(leadout_offset)
    
    # 99 track offsets (8-digit hex each) - positions 1-99 in the frame offset array
    for i in range(99):
        if i < len(track_offsets):
            hex_string += "{:08X}".format(track_offsets[i])
        else:
            hex_string += "00000000"  # Pad with zeros
    
    print("Hex string: {}".format(hex_string[:50] + "..."))
    print("Hex string length: {}".format(len(hex_string)))
    
    # Step 2: SHA-1 hash the hex string
    sha1 = hashlib.sha1()
    sha1.update(hex_string.encode('ascii'))
    digest = sha1.digest()
    
    # Step 3: Base64 encode with MusicBrainz character substitutions
    # Standard base64
    b64 = base64.b64encode(digest).decode('ascii')
    
    # MusicBrainz substitutions: + -> ., / -> _, = -> -
    mb_b64 = b64.replace('+', '.').replace('/', '_').replace('=', '-')
    
    return mb_b64

def test_known_musicbrainz_example():
    """Test against the known example from MusicBrainz documentation"""
    print("=" * 60)
    print("Testing MusicBrainz Disc ID Calculation")
    print("=" * 60)
    
    # Known example from MusicBrainz docs:
    # Expected disc ID: 49HHV7Eb8UKF3aQiNmu1GR8vKTY-
    
    # Track offsets from the documentation (already include +150):
    track_offsets = [
        150,    # Track 1: 150 + 0
        15363,  # Track 2: 150 + 15213
        32314,  # Track 3: 150 + 32164
        46592,  # Track 4: 150 + 46442
        63414,  # Track 5: 150 + 63264
        80489,  # Track 6: 150 + 80339
    ]
    
    leadout_offset = 95462  # 150 + 95312
    
    print("Track offsets: {}".format(track_offsets))
    print("Lead-out offset: {}".format(leadout_offset))
    
    calculated_id = calculate_musicbrainz_disc_id_manual(track_offsets, leadout_offset)
    expected_id = "49HHV7Eb8UKF3aQiNmu1GR8vKTY-"
    
    print("\nResults:")
    print("Calculated: {}".format(calculated_id))
    print("Expected:   {}".format(expected_id))
    
    if calculated_id == expected_id:
        print("✓ MusicBrainz disc ID calculation CORRECT!")
        return True
    else:
        print("X MusicBrainz disc ID calculation INCORRECT!")
        
        # Debug: let's check each step
        print("\nDebugging...")
        
        # Build debug hex string
        hex_debug = ""
        hex_debug += "{:02X}".format(1)  # First track
        hex_debug += "{:02X}".format(6)  # Last track  
        hex_debug += "{:08X}".format(leadout_offset)  # Lead-out
        
        print("First track: {:02X}".format(1))
        print("Last track: {:02X}".format(6))
        print("Lead-out: {:08X}".format(leadout_offset))
        
        for i, offset in enumerate(track_offsets):
            print("Track {}: {:08X}".format(i+1, offset))
            hex_debug += "{:08X}".format(offset)
        
        # Pad remaining positions
        for i in range(len(track_offsets), 99):
            hex_debug += "00000000"
        
        print("First 50 chars of hex: {}".format(hex_debug[:50]))
        
        # Manual SHA-1
        sha1 = hashlib.sha1()
        sha1.update(hex_debug.encode('ascii'))
        digest = sha1.digest()
        print("SHA-1 digest (hex): {}".format(digest.hex()))
        
        # Manual base64
        b64 = base64.b64encode(digest).decode('ascii')
        print("Standard base64: {}".format(b64))
        
        mb_b64 = b64.replace('+', '.').replace('/', '_').replace('=', '-')
        print("MusicBrainz base64: {}".format(mb_b64))
        
        return False

def test_simple_case():
    """Test a simple 3-track case"""
    print("\n" + "=" * 60)
    print("Testing Simple 3-Track Case")
    print("=" * 60)
    
    # Simple 3-track example
    track_offsets = [150, 1000, 2000]  # Already include +150
    leadout_offset = 3000
    
    print("Track offsets: {}".format(track_offsets))
    print("Lead-out offset: {}".format(leadout_offset))
    
    calculated_id = calculate_musicbrainz_disc_id_manual(track_offsets, leadout_offset)
    
    print("Calculated disc ID: {}".format(calculated_id))
    print("Length: {} characters".format(len(calculated_id)))
    
    # All MusicBrainz disc IDs should be 28 characters
    if len(calculated_id) == 28:
        print("✓ Correct length (28 characters)")
        return True
    else:
        print("X Incorrect length (should be 28 characters)")
        return False

def main():
    """Run MusicBrainz disc ID tests"""
    print("MusicBrainz Disc ID Validation Test")
    print("=" * 60)
    
    tests = [
        test_known_musicbrainz_example,
        test_simple_case
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print("Test failed with exception: {}".format(e))
            results.append(False)
    
    print("\n" + "=" * 60)
    print("Test Results")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print("Tests passed: {}/{}".format(passed, total))
    
    if passed == total:
        print("✓ All MusicBrainz disc ID tests passed!")
        print("Algorithm implementation is correct.")
    else:
        print("X Some tests failed - algorithm needs review")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
