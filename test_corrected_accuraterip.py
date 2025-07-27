#!/usr/bin/env python3

import sys
sys.path.append('.')

from accuraterip_checker import AccurateRipChecker
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Test data from the Porcupine Tree disc
# Track sectors from the logs:
# Track 01: 33607 sectors
# Track 02: 23066 sectors  
# Track 03: 79695 sectors
# Track 04: 24489 sectors
# Track 05: 34326 sectors
# Track 06: 33847 sectors

# Calculate track offsets (start sectors + 150)
# Assuming tracks start at: 0, 33607, 56673, 136368, 160857, 195183
track_offsets = [
    150,      # Track 1 start (0 + 150)
    33757,    # Track 2 start (33607 + 150) 
    56823,    # Track 3 start (33607 + 23066 + 150)
    136518,   # Track 4 start (33607 + 23066 + 79695 + 150)
    161007,   # Track 5 start (33607 + 23066 + 79695 + 24489 + 150)
    195333,   # Track 6 start (33607 + 23066 + 79695 + 24489 + 34326 + 150)
    229180    # Leadout (195333 + 33847)
]

print("Testing corrected AccurateRip disc ID calculation")
print("=" * 50)

print(f"Track offsets: {track_offsets}")

checker = AccurateRipChecker({})

# Calculate disc IDs using corrected algorithms
disc_id1 = checker._calculate_accuraterip_disc_id1(track_offsets)
disc_id2 = checker._calculate_accuraterip_disc_id2(track_offsets) 
disc_id3 = checker._calculate_accuraterip_disc_id3(track_offsets)

print(f"\nCorrected AccurateRip disc IDs:")
print(f"ID1: {disc_id1:08X}")
print(f"ID2: {disc_id2:08X}")
print(f"ID3: {disc_id3:08X}")

# Test URLs
id1_hex = f"{disc_id1:08X}"
id2_hex = f"{disc_id2:08X}" 
id3_hex = f"{disc_id3:08X}"

url = f"http://www.accuraterip.com/accuraterip/{id1_hex[0]}/{id1_hex[1]}/{id1_hex[2]}/dBAR-006-{id1_hex}-{id2_hex}-{id3_hex}.bin"
print(f"\nAccurateRip URL: {url}")

# Test with a simple HTTP request
import requests
try:
    response = requests.get(url, timeout=10)
    print(f"HTTP Status: {response.status_code}")
    if response.status_code == 200:
        print(f"SUCCESS! Found AccurateRip data ({len(response.content)} bytes)")
    elif response.status_code == 404:
        print("404 - Still not found in database")
    else:
        print(f"Other status: {response.status_code}")
except Exception as e:
    print(f"Request error: {e}")
