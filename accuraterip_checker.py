#!/usr/bin/env python3
"""
AccurateRip Checker - Verifies rips against the AccurateRip database
"""

import hashlib
import logging
import requests
import struct
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

class AccurateRipChecker:
    """Checks ripped tracks against AccurateRip database"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.accuraterip_url = "http://www.accuraterip.com/accuraterip"
    
    def accuraterip_checksum(self, wav_path: str, track_number: int, total_tracks: int) -> Tuple[Optional[int], Optional[int]]:
        """
        Calculate AccurateRip v1 and v2 checksums for a WAV file.
        
        Returns tuple of (v1_checksum, v2_checksum) or (None, None) on error.
        """
        try:
            import wave
            import struct
            
            with wave.open(wav_path, 'rb') as w:
                if w.getnchannels() != 2 or w.getsampwidth() != 2 or w.getframerate() != 44100:
                    self.logger.error(f"WAV file {wav_path} is not CD-quality (44.1kHz, 16-bit, stereo)")
                    return None, None
                
                frames = w.readframes(w.getnframes())
                if len(frames) == 0:
                    self.logger.error(f"No audio data in {wav_path}")
                    return None, None
                
                # Convert to 32-bit integers (little-endian 16-bit samples)
                audio_data = []
                for i in range(0, len(frames), 4):  # 4 bytes = 2 samples * 2 bytes each
                    if i + 3 < len(frames):
                        # Combine left and right samples into one 32-bit value
                        left = struct.unpack('<h', frames[i:i+2])[0]
                        right = struct.unpack('<h', frames[i+2:i+4])[0]
                        combined = (right << 16) | (left & 0xFFFF)
                        audio_data.append(combined & 0xFFFFFFFF)
                
                if not audio_data:
                    self.logger.error(f"Could not extract audio data from {wav_path}")
                    return None, None
                
                return self._compute_checksums(audio_data, track_number, total_tracks)
                
        except Exception as e:
            self.logger.error(f"Error calculating AccurateRip checksum for {wav_path}: {e}")
            return None, None
    
    def _compute_checksums(self, audio_data: List[int], track_number: int, total_tracks: int) -> Tuple[int, int]:
        """
        Compute AccurateRip v1 and v2 checksums from audio data.
        
        Implementation based on whipper's C extension.
        """
        csum_hi = 0
        csum_lo = 0
        
        # AccurateRip skips first and last 5 sectors for first/last tracks
        sector_bytes = 2352  # bytes per CD sector
        samples_per_sector = sector_bytes // 4  # 4 bytes per sample (2 channels * 2 bytes)
        
        start_offset = 0
        end_offset = len(audio_data)
        
        if track_number == 1:
            start_offset = samples_per_sector * 5
        if track_number == total_tracks:
            end_offset -= samples_per_sector * 5
        
        # Ensure we don't go out of bounds
        start_offset = max(0, start_offset)
        end_offset = min(len(audio_data), end_offset)
        
        if start_offset >= end_offset:
            self.logger.warning(f"Track {track_number}: start_offset {start_offset} >= end_offset {end_offset}")
            return 0, 0
        
        for i in range(start_offset, end_offset):
            multiplier = i + 1  # 1-based multiplier
            sample = audio_data[i]
            
            # Calculate product
            product = sample * multiplier
            
            # Split into high and low 32-bit parts
            csum_hi += (product >> 32) & 0xFFFFFFFF
            csum_lo += product & 0xFFFFFFFF
        
        # Ensure results are 32-bit
        csum_hi &= 0xFFFFFFFF
        csum_lo &= 0xFFFFFFFF
        
        v1 = csum_lo
        v2 = (csum_lo + csum_hi) & 0xFFFFFFFF
        
        return v1, v2
    
    def calculate_accuraterip_disc_ids(self, track_offsets: List[int]) -> Tuple[str, str, str]:
        """
        Calculate AccurateRip disc IDs based on track offsets.
        
        Implementation based on whipper's table.py accuraterip_ids() method.
        
        Returns tuple of (disc_id1, disc_id2, cddb_disc_id).
        """
        if not track_offsets or len(track_offsets) < 2:
            self.logger.error("Need at least 2 track offsets for AccurateRip disc ID calculation")
            return "00000000", "00000000", "00000000"
        
        # AccurateRip disc ID calculation (based on whipper implementation)
        disc_id1 = 0
        disc_id2 = 0
        
        # track_offsets includes leadout, so tracks are all but the last offset
        track_count = len(track_offsets) - 1
        
        # Process all tracks (exclude leadout)
        for i in range(track_count):
            offset = track_offsets[i]
            track_number = i + 1
            
            disc_id1 += offset
            disc_id2 += offset * track_number
        
        # Add leadout offset (one past the end of last track)
        leadout_offset = track_offsets[-1] if len(track_offsets) > track_count else track_offsets[-1] + 150 * 75
        disc_id1 += leadout_offset
        disc_id2 += leadout_offset * (track_count + 1)
        
        # Ensure 32-bit values
        disc_id1 &= 0xFFFFFFFF
        disc_id2 &= 0xFFFFFFFF
        
        # Calculate CDDB disc ID (different algorithm)
        cddb_id = self._calculate_cddb_disc_id(track_offsets)
        
        return f"{disc_id1:08x}", f"{disc_id2:08x}", f"{cddb_id:08x}"
    
    def _calculate_cddb_disc_id(self, track_offsets: List[int]) -> int:
        """Calculate CDDB disc ID"""
        # Simple implementation - in practice this would need proper CDDB algorithm
        checksum = 0
        for offset in track_offsets:
            # Sum of digits of seconds
            seconds = offset // 75
            while seconds > 0:
                checksum += seconds % 10
                seconds //= 10
        
        # Add number of tracks and total time
        total_time = (track_offsets[-1] + 150 * 75) // 75  # Approximate
        return (checksum % 0xFF) << 24 | (total_time << 8) | len(track_offsets)
    
    def get_accuraterip_path(self, disc_id1: str, disc_id2: str, cddb_id: str, track_count: int = None) -> str:
        """
        Generate AccurateRip database path from disc IDs.
        
        Format: 1/2/3/dBAR-nnn-discid1-discid2-cddbid.bin
        Based on whipper's table.py accuraterip_path() method.
        """
        # Use last digit of each ID for path structure (reverse order)
        path1 = disc_id1[-1]
        path2 = disc_id1[-2] 
        path3 = disc_id1[-3]
        
        # Track count for filename (default to extracting from context)
        if track_count is None:
            track_count = 12  # Default assumption
        
        # Format filename
        filename = f"dBAR-{track_count:03d}-{disc_id1}-{disc_id2}-{cddb_id}.bin"
        
        return f"{path1}/{path2}/{path3}/{filename}"
    
    def lookup_accuraterip_database(self, disc_id1: str, disc_id2: str, cddb_id: str, track_count: int = 12) -> Optional[List[Dict]]:
        """
        Look up disc in AccurateRip database and return responses.
        """
        path = self.get_accuraterip_path(disc_id1, disc_id2, cddb_id, track_count)
        url = f"{self.accuraterip_url}/{path}"
        
        self.logger.info(f"Looking up AccurateRip database: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 404:
                self.logger.warning("Disc not found in AccurateRip database")
                return None
            
            response.raise_for_status()
            
            # Parse binary response
            return self._parse_accuraterip_response(response.content)
            
        except requests.RequestException as e:
            self.logger.error(f"Error accessing AccurateRip database: {e}")
            return None
    
    def _parse_accuraterip_response(self, data: bytes) -> List[Dict]:
        """
        Parse AccurateRip binary response data.
        
        Format: [track_count][disc_id1][disc_id2][cddb_id][track_data...]
        Track data: [confidence][checksum] for each track
        """
        responses = []
        pos = 0
        
        while pos < len(data):
            if pos + 13 > len(data):
                break
                
            # Read header
            track_count = data[pos]
            disc_id1 = struct.unpack('<I', data[pos+1:pos+5])[0]
            disc_id2 = struct.unpack('<I', data[pos+5:pos+9])[0] 
            cddb_id = struct.unpack('<I', data[pos+9:pos+13])[0]
            pos += 13
            
            # Read track data
            checksums = []
            confidences = []
            
            for track in range(track_count):
                if pos + 9 > len(data):
                    break
                    
                confidence = data[pos]
                checksum = struct.unpack('<I', data[pos+1:pos+5])[0]
                
                confidences.append(confidence)
                checksums.append(f"{checksum:08x}")
                pos += 9
            
            responses.append({
                'track_count': track_count,
                'disc_id1': f"{disc_id1:08x}",
                'disc_id2': f"{disc_id2:08x}",
                'cddb_id': f"{cddb_id:08x}",
                'checksums': checksums,
                'confidences': confidences
            })
        
        return responses
    
    def verify_rip(self, output_dir: Path, track_offsets: List[int]) -> bool:
        """
        Verify all tracks in the output directory against AccurateRip database.
        
        Args:
            output_dir: Directory containing ripped WAV files
            track_offsets: List of track start offsets in CD frames
            
        Returns:
            True if verification passes, False otherwise
        """
        try:
            wav_files = sorted(list(output_dir.glob("*.wav")))
            if not wav_files:
                self.logger.warning("No WAV files found for AccurateRip verification")
                return False
            
            self.logger.info(f"Starting AccurateRip verification for {len(wav_files)} tracks")
            
            # Calculate disc IDs
            disc_id1, disc_id2, cddb_id = self.calculate_accuraterip_disc_ids(track_offsets)
            self.logger.info(f"Disc IDs: ID1={disc_id1}, ID2={disc_id2}, CDDB={cddb_id}")
            
            # Look up in AccurateRip database
            responses = self.lookup_accuraterip_database(disc_id1, disc_id2, cddb_id)
            if not responses:
                self.logger.warning("Disc not found in AccurateRip database")
                return False
            
            self.logger.info(f"Found {len(responses)} AccurateRip response(s)")
            
            # Calculate checksums for all tracks
            track_checksums = []
            for i, wav_file in enumerate(wav_files):
                track_number = i + 1
                total_tracks = len(wav_files)
                
                v1, v2 = self.accuraterip_checksum(str(wav_file), track_number, total_tracks)
                if v1 is None or v2 is None:
                    self.logger.error(f"Failed to calculate checksum for track {track_number}")
                    return False
                
                track_checksums.append({
                    'track': track_number,
                    'v1': f"{v1:08x}",
                    'v2': f"{v2:08x}",
                    'file': wav_file.name
                })
                
                self.logger.debug(f"Track {track_number}: v1={v1:08x}, v2={v2:08x}")
            
            # Verify against database responses
            return self._verify_checksums_against_responses(track_checksums, responses)
            
        except Exception as e:
            self.logger.error(f"AccurateRip verification failed: {e}")
            return False
    
    def _verify_checksums_against_responses(self, track_checksums: List[Dict], responses: List[Dict]) -> bool:
        """
        Verify calculated checksums against AccurateRip database responses.
        """
        all_tracks_verified = True
        
        for track_checksum in track_checksums:
            track_number = track_checksum['track']
            track_index = track_number - 1
            
            v1_match = False
            v2_match = False
            best_confidence = 0
            
            # Check against all responses
            for response in responses:
                if track_index < len(response['checksums']):
                    db_checksum = response['checksums'][track_index]
                    confidence = response['confidences'][track_index]
                    
                    # Check v1 match
                    if track_checksum['v1'] == db_checksum:
                        v1_match = True
                        best_confidence = max(best_confidence, confidence)
                        self.logger.info(f"Track {track_number}: AccurateRip v1 match (confidence {confidence})")
                    
                    # Check v2 match (note: v2 checksums might be in separate responses)
                    if track_checksum['v2'] == db_checksum:
                        v2_match = True
                        best_confidence = max(best_confidence, confidence)
                        self.logger.info(f"Track {track_number}: AccurateRip v2 match (confidence {confidence})")
            
            if v1_match or v2_match:
                self.logger.info(f"✓ Track {track_number} ({track_checksum['file']}): AccurateRip verification PASSED (confidence {best_confidence})")
            else:
                self.logger.warning(f"✗ Track {track_number} ({track_checksum['file']}): AccurateRip verification FAILED")
                self.logger.warning(f"  Calculated: v1={track_checksum['v1']}, v2={track_checksum['v2']}")
                all_tracks_verified = False
        
        if all_tracks_verified:
            self.logger.info("🎉 All tracks verified successfully against AccurateRip database!")
        else:
            self.logger.warning("⚠️  Some tracks failed AccurateRip verification")
        
        return all_tracks_verified
    
    def verify_track_with_versions(self, wav_file: Path, track_number: int, total_tracks: int) -> Dict[str, Any]:
        """
        Verify a single track and return detailed results.
        
        Returns dict with verification status and checksum information.
        """
        result = {
            'track': track_number,
            'file': wav_file.name,
            'verified': False,
            'v1_checksum': None,
            'v2_checksum': None,
            'confidence': 0,
            'error': None
        }
        
        try:
            v1, v2 = self.accuraterip_checksum(str(wav_file), track_number, total_tracks)
            if v1 is not None and v2 is not None:
                result['v1_checksum'] = f"{v1:08x}"
                result['v2_checksum'] = f"{v2:08x}"
                # Note: Database lookup would require disc IDs which need TOC data
                # This method is for calculating checksums only
            else:
                result['error'] = "Failed to calculate AccurateRip checksums"
                
        except Exception as e:
            result['error'] = str(e)
            
        return result
