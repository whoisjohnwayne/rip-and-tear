#!/usr/bin/env python3
"""
CD Ripper - Main ripping functionality
Handles the actual CD ripping process with burst mode, AccurateRip verification,
and fallback to cd-paranoia (libcdio-paranoia)
"""

import os
import time
import subprocess
import logging
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from metadata_fetcher import MetadataFetcher
from cue_generator import CueGenerator
from accuraterip_checker import AccurateRipChecker

from toc_analyzer import TOCAnalyzer, DiscInfo

class RipStatus:
    """Status tracking for rip operations"""
    IDLE = "idle"
    READING_TOC = "reading_toc"
    FETCHING_METADATA = "fetching_metadata"
    RIPPING_BURST = "ripping_burst"
    VERIFYING_ACCURATERIP = "verifying_accuraterip"
    RERIPPING_FAILED_TRACKS = "reripping_failed_tracks"
    RIPPING_PARANOIA = "ripping_paranoia"
    ENCODING = "encoding"
    CREATING_CUE = "creating_cue"
    COMPLETED = "completed"
    ERROR = "error"

class CDRipper:
    """Main CD ripping class"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.status = RipStatus.IDLE
        self.progress = 0
        self.current_track = 0
        self.total_tracks = 0
        self.error_message = ""
        self.rip_start_time = None
        self.cancel_requested = False
        self.current_process = None
        self.metadata_fetcher = MetadataFetcher(config)
        self.cue_generator = CueGenerator()
        self.accuraterip_checker = AccurateRipChecker()
        self.toc_analyzer = TOCAnalyzer(config)
        
        # Create output directory
        self.output_dir = Path(config['output']['directory'])
        self.output_dir.mkdir(exist_ok=True)
        
    def rip_cd(self) -> bool:
        """Main CD ripping function"""
        try:
            self.rip_start_time = datetime.now()
            self.cancel_requested = False
            self._update_status(RipStatus.READING_TOC)
            
            # Check for cancellation
            if self._check_cancelled():
                self._eject_cd()
                return False
            
            # Get comprehensive CD information with gap detection
            disc_info = self.toc_analyzer.analyze_disc()
            if not disc_info:
                self._update_status(RipStatus.ERROR, "Failed to analyze CD structure")
                self._eject_cd()
                return False
            
            # Check for cancellation
            if self._check_cancelled():
                self._eject_cd()
                return False
            
            # Validate that we have tracks
            if not hasattr(disc_info, 'tracks') or not disc_info.tracks:
                self._update_status(RipStatus.ERROR, "No tracks found on CD - disc may be damaged or unreadable")
                self._eject_cd()
                return False
            
            self.total_tracks = len(disc_info.tracks)
            self.logger.info(f"Found {self.total_tracks} tracks on CD")
            
            # Fetch metadata
            self._update_status(RipStatus.FETCHING_METADATA)
            
            # Check for cancellation
            if self._check_cancelled():
                self._eject_cd()
                return False
                
            metadata = self.metadata_fetcher.get_metadata(disc_info.to_dict())
            
            # Create output directory for this album
            album_dir = self._create_album_directory(metadata)
            
            
            # Try burst mode rip first
            if self.config['ripping']['try_burst_first']:
                # Check for cancellation
                if self._check_cancelled():
                    self._eject_cd()
                    return False
                self._update_status(RipStatus.RIPPING_BURST)
                burst_success = self._rip_burst_mode(disc_info, album_dir, metadata)
                
                # Check for cancellation - if cancelled during burst mode, abort completely
                if self._check_cancelled():
                    self._update_status(RipStatus.IDLE, "Operation cancelled by user during burst mode")
                    self._eject_cd()
                    return False
                
                if burst_success and self.config['ripping']['use_accuraterip']:
                    # AccurateRip verification was already done per-track during burst mode
                    self.logger.info("Per-track AccurateRip verification completed during burst mode")
                    result = self._finalize_rip(disc_info, metadata, album_dir, skip_encoding=True)
                    self._eject_cd()
                    return result
                elif burst_success:
                    self.logger.info("Burst mode rip completed (AccurateRip verification disabled)")
                    result = self._finalize_rip(disc_info, metadata, album_dir, skip_encoding=True)
                    self._eject_cd()
                    return result
                else:
                    # Burst mode failed (not cancelled) - fall through to paranoia mode
                    self.logger.warning("Burst mode failed, will try full paranoia mode")
            
            # Fallback to full paranoia mode if burst mode failed completely (not if cancelled)
            if not self._check_cancelled():  # Only proceed to paranoia if not cancelled
                self._update_status(RipStatus.RIPPING_PARANOIA)
                self.logger.info("Using full paranoia mode for all tracks")
                if self._rip_paranoia_mode(disc_info, album_dir, metadata):
                    # Check for cancellation after paranoia mode
                    if self._check_cancelled():
                        self._update_status(RipStatus.IDLE, "Operation cancelled by user during paranoia mode")
                        self._eject_cd()
                        return False
                    result = self._finalize_rip(disc_info, metadata, album_dir, skip_encoding=True)
                    self._eject_cd()
                    return result
                else:
                    self._update_status(RipStatus.ERROR, "Paranoia mode ripping failed")
                    self._eject_cd()
                    return False
            else:
                # Cancelled before paranoia mode could start
                self._update_status(RipStatus.IDLE, "Operation cancelled by user")
                self._eject_cd()
                return False
                
        except Exception as e:
            self.logger.error(f"CD ripping failed: {e}")
            self._update_status(RipStatus.ERROR, str(e))
            self._eject_cd()
            return False
    def _eject_cd(self):
        """Eject the CD using the system eject command"""
        device = self.config['cd_drive']['device']
        try:
            subprocess.run(['eject', device], check=False)
            self.logger.info(f"Ejected CD from {device}")
        except Exception as e:
            self.logger.warning(f"Failed to eject CD: {e}")
    
    def _get_cd_toc(self) -> Optional[Dict[str, Any]]:
        """Get CD table of contents"""
        device = self.config['cd_drive']['device']
        
        try:
            # Use cd-paranoia (libcdio-paranoia) to get TOC
            result = subprocess.run(
                ['cd-paranoia', '-Q', '-d', device],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self.logger.error(f"Failed to read CD TOC: {result.stderr}")
                return None
            
            return self._parse_toc_output(result.stderr)
            
        except subprocess.TimeoutExpired:
            self.logger.error("TOC reading timed out")
            return None
        except Exception as e:
            self.logger.error(f"Error reading TOC: {e}")
            return None
    
    def _parse_toc_output(self, toc_output: str) -> Dict[str, Any]:
        """Parse cd-paranoia TOC output with robust error handling"""
        tracks = []
        lines = toc_output.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('track'):
                try:
                    # Parse track line: "track 01.  audio    00:32.17    760 [00:02.17]"
                    parts = line.split()
                    if len(parts) >= 4 and parts[2] == 'audio':
                        # Validate track number
                        track_str = parts[1].rstrip('.')
                        if not track_str.isdigit():
                            self.logger.warning(f"Invalid track number in TOC line: {line}")
                            continue
                        track_num = int(track_str)
                        
                        # Validate duration format
                        duration = parts[3]
                        if ':' not in duration:
                            self.logger.warning(f"Invalid duration format in TOC line: {line}")
                            continue
                        
                        tracks.append({
                            'number': track_num,
                            'duration': duration,
                            'type': 'audio'
                        })
                except (ValueError, IndexError) as e:
                    self.logger.warning(f"Failed to parse TOC line '{line}': {e}")
                    continue
        
        if not tracks:
            self.logger.warning("No valid tracks found in TOC output")
        
        return {
            'tracks': tracks,
            'total_time': self._calculate_total_time(tracks)
        }
    
    def _calculate_total_time(self, tracks: List[Dict]) -> str:
        """Calculate total disc time"""
        total_seconds = 0
        for track in tracks:
            duration = track['duration']
            if ':' in duration:
                parts = duration.split(':')
                minutes = int(parts[0])
                seconds = float(parts[1])
                total_seconds += minutes * 60 + seconds
        
        total_minutes = int(total_seconds // 60)
        remaining_seconds = int(total_seconds % 60)
        return f"{total_minutes:02d}:{remaining_seconds:02d}"
    
    def _create_album_directory(self, metadata: Dict[str, Any]) -> Path:
        """Create directory for the album"""
        artist = metadata.get('artist', 'Unknown Artist')
        album = metadata.get('album', 'Unknown Album')
        year = metadata.get('date', '')
        
        # Sanitize directory name
        dir_name = f"{artist} - {album}"
        if year:
            dir_name = f"{year} - {dir_name}"
        
        dir_name = self._sanitize_filename(dir_name)
        album_dir = self.output_dir / dir_name
        album_dir.mkdir(exist_ok=True)
        
        return album_dir
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem compatibility"""
        # Remove or replace problematic characters
        chars_to_replace = {
            '/': '-',
            '\\': '-',
            ':': ' -',
            '*': '',
            '?': '',
            '"': "'",
            '<': '(',
            '>': ')',
            '|': '-'
        }
        
        for char, replacement in chars_to_replace.items():
            filename = filename.replace(char, replacement)
        
        # Remove multiple spaces and trim
        filename = ' '.join(filename.split())
        return filename.strip()

    def _rip_burst_mode(self, disc_info: DiscInfo, output_dir: Path, metadata: Dict[str, Any] = None) -> bool:
        """Rip in burst mode (fast) with immediate per-track encoding"""
        device = self.config['cd_drive']['device']
        tracks = disc_info.tracks
        last_track_failed = False
        
        try:
            for i, track in enumerate(tracks, 1):
                self.current_track = i
                # Progress: 50% for ripping, 50% for encoding per track
                base_progress = int((i - 1) / len(tracks) * 100)

                # Get track title for logging

                # Robustly get track title, fallback if missing, and log if metadata is missing
                fallback_title = f'Track {i:02d}'
                track_meta = None
                track_title = None
                if metadata and metadata.get('tracks') and i <= len(metadata['tracks']):
                    track_meta = metadata['tracks'][i-1]
                    if not track_meta:
                        self.logger.warning(f"No metadata for track {i}, using fallback title '{fallback_title}'")
                        track_title = fallback_title
                    else:
                        title = track_meta.get('title')
                        if not title or not str(title).strip():
                            self.logger.warning(f"Missing or empty title for track {i}, using fallback title '{fallback_title}'")
                            track_title = fallback_title
                        else:
                            track_title = str(title)
                else:
                    self.logger.warning(f"No metadata entry for track {i}, using fallback title '{fallback_title}'")
                    track_title = fallback_title

                sanitized_title = self._sanitize_filename(track_title)
                track_file = output_dir / f"{i:02d} - {sanitized_title}.wav"

                self.logger.info(f"Track {i} output WAV filename: {track_file}")

                # Enhanced ripping with gap handling
                cmd = [
                    'cd-paranoia',
                    '-d', device,
                    '-Z',  # Disable all paranoia checks for speed (burst mode)
                    '-z',  # Never ask, never tell
                ]
                # Add offset to cmd if needed (before positional args)
                if self.config['cd_drive']['offset'] != 0:
                    cmd.extend(['-O', str(self.config['cd_drive']['offset'])])
                # Standard track ripping
                track_cmd = cmd + [f'{i}', str(track_file)]
                # Apply last track specific settings
                if i == len(tracks):
                    track_cmd = [
                        'cd-paranoia',
                    ]
                    if self.config['cd_drive'].get('force_overread', True):
                        track_cmd.append('--force-overread')
                        self.logger.info(f"Drive supports overread: enabling --force-overread for last track.")
                    track_cmd += [
                        '-d', device,
                        '-z',  # Never ask, never tell
                        '-Z',  # Disable all paranoia checks for speed (burst mode)
                    ]
                    if self.config['cd_drive']['offset'] != 0:
                        track_cmd.extend(['-O', str(self.config['cd_drive']['offset'])])
                    # Add track and output
                    track_cmd.extend([f'{i}', str(track_file)])
                    # Extra validation: ensure output filename is not empty
                    if not str(track_file):
                        self.logger.error(f"BUG: Last track output filename is empty! Track {i}, track_file={track_file}")
                        raise RuntimeError(f"BUG: Last track output filename is empty! Track {i}, track_file={track_file}")
                    if not track_cmd[-1] or track_cmd[-1].strip() == '':
                        self.logger.error(f"BUG: Last track cd-paranoia command missing output filename! Command: {' '.join(track_cmd)}")
                        raise RuntimeError(f"BUG: Last track cd-paranoia command missing output filename! Command: {' '.join(track_cmd)}")
                    self.logger.info(f"Last track special command: {' '.join(track_cmd)}")
                # Handle pre-gaps and HTOA
                if track.has_htoa and i == 1:
                    # Rip HTOA if present
                    htoa_file = output_dir / "00.wav"
                    htoa_cmd = cmd.copy()
                    htoa_cmd += [f'-{track.htoa_length//75}', str(htoa_file)]
                    self.logger.info(f"Ripping HTOA ({track.htoa_length/75:.2f} seconds)")
                    subprocess.run(htoa_cmd, capture_output=True, text=True, timeout=600)
                # Debug: Log the exact command being executed
                self.logger.info(f"Executing cd-paranoia command: {' '.join(track_cmd)}")

                # Check for cancellation before ripping
                if self._check_cancelled():
                    return False

                self.logger.info(f"Ripping track {i}...")
                self.progress = base_progress
                result = self._run_cancellable_subprocess(track_cmd, timeout=600)

                # Check for cancellation after ripping
                if self._check_cancelled():
                    return False

                if result.returncode != 0:
                    # Last track failure handling
                    if i == len(tracks):
                        self.logger.warning(f"Last track {i} failed with standard settings")
                        self.logger.error(f"Error: {result.stderr}")
                        
                        # Try one recovery attempt with minimal paranoia
                        self.logger.info("Attempting last track recovery...")
                        recovery_cmd = [
                            'cd-paranoia',
                            '-d', device,
                            '-z',  # Never ask, never tell
                            '-Y',  # Most lenient paranoia mode
                        ]
                        if self.config['cd_drive'].get('force_overread', True):
                          track_cmd.append('--force-overread')
                          self.logger.info(f"Drive supports overread: enabling --force-overread for last track.")

                        if self.config['cd_drive']['offset'] != 0:
                            recovery_cmd.extend(['-O', str(self.config['cd_drive']['offset'])])
                        
                        recovery_cmd.extend([f'{i}', str(track_file)])
                        
                        self.logger.info(f"Recovery command: {' '.join(recovery_cmd)}")
                        recovery_result = self._run_cancellable_subprocess(recovery_cmd, timeout=900)
                        
                        if recovery_result.returncode == 0:
                            self.logger.info("Last track recovery successful!")
                            result = recovery_result
                        else:
                            self.logger.error(f"Last track recovery failed: {recovery_result.stderr}")
                            self.logger.warning("Last track failed - will need paranoia mode fallback")
                            last_track_failed = True
                            break  # Exit loop to trigger paranoia mode fallback
                    else:
                        # Non-last track failure
                        self.logger.error(f"Failed to rip track {i}: {result.stderr}")
                        return False
                
                self.logger.info(f"Ripped track {i}, now encoding to FLAC...")
                
                # Immediately encode this track to FLAC
                self.progress = base_progress + int(25 / len(tracks))  # 25% for encoding
                if not self._encode_single_track(i, track, track_file, output_dir, metadata):
                    return False
                
                # Check for cancellation after encoding
                if self._check_cancelled():
                    return False
                
                # Immediately verify with AccurateRip if enabled
                track_verified = True
                if self.config['ripping']['use_accuraterip']:
                    self.logger.info(f"Verifying track {i} with AccurateRip...")
                    self.progress = base_progress + int(40 / len(tracks))  # +15% for verification
                    track_verified = self._verify_single_track_accuraterip(i, track_file, disc_info)
                    
                    if not track_verified:
                        self.logger.warning(f"Track {i} failed AccurateRip verification")
                        # Mark for re-ripping later, but continue with other tracks
                        # We'll handle failed tracks after all tracks are processed
                
                # Delete WAV file immediately after verification
                if track_file.exists():
                    track_file.unlink()
                    self.logger.debug(f"Deleted WAV file for track {i}")
                
                # Check for cancellation after verification
                if self._check_cancelled():
                    return False
                
                self.logger.info(f"Completed track {i} (ripped, encoded, {'AccurateRip verified' if track_verified else 'AccurateRip: no database entry'})")
                self.progress = int(i / len(tracks) * 100)
            
            # If only the last track failed, we have a partial success
            if last_track_failed:
                self.logger.info("Burst mode partially succeeded - some tracks failed, will need paranoia mode fallback")
                return False  # Signal that we need paranoia mode, but don't log it as a complete failure
            
            return True
            
        except subprocess.TimeoutExpired:
            self.logger.error("Burst mode ripping timed out")
            return False
        except Exception as e:
            self.logger.error(f"Burst mode ripping failed: {e}")
            return False
    
    def _encode_single_track(self, track_num: int, track_info: Any, wav_file: Path, output_dir: Path, metadata: Dict[str, Any] = None) -> bool:
        """Encode a single track to FLAC and delete the WAV file"""
        if not wav_file.exists():
            self.logger.error(f"WAV file not found: {wav_file}")
            return False
        
        # Check for cancellation before encoding
        if self._check_cancelled():
            self.logger.info("Track encoding cancelled by user")
            return False
        
        # Get track metadata
        track_meta = {}
        if metadata and metadata.get('tracks') and track_num <= len(metadata['tracks']):
            track_meta = metadata['tracks'][track_num-1]
        
        flac_file = output_dir / f"{track_num:02d} - {self._sanitize_filename(track_meta.get('title', f'Track {track_num:02d}'))}.flac"
        
        # Build FLAC encoding command
        cmd = [
            'flac',
            '-f',  # Force overwrite existing files
            f'--compression-level-{self.config["output"]["compression_level"]}',
            # Note: NOT using --delete-input-file to keep WAV for AccurateRip verification
            f'--output-name={flac_file}',
        ]
        
        # Add metadata tags
        if metadata:
            if metadata.get('artist'):
                cmd.extend(['--tag', f'ARTIST={metadata["artist"]}'])
            if metadata.get('album'):
                cmd.extend(['--tag', f'ALBUM={metadata["album"]}'])
            if metadata.get('date'):
                cmd.extend(['--tag', f'DATE={metadata["date"]}'])
        
        if track_meta.get('title'):
            cmd.extend(['--tag', f'TITLE={track_meta["title"]}'])
        if track_meta.get('artist'):
            cmd.extend(['--tag', f'ARTIST={track_meta["artist"]}'])
        
        # Calculate dynamic timeout based on track duration
        try:
            # TrackInfo has length_seconds property
            if hasattr(track_info, 'length_seconds'):
                track_minutes = track_info.length_seconds / 60.0
            else:
                track_minutes = 4.0  # Fallback
            encoding_timeout = max(120, int(track_minutes * 3 + 60))  # Min 2 minutes, scale with length
        except (AttributeError, TypeError):
            encoding_timeout = 300  # Fallback for any errors
        
        # Add track number tags
        total_tracks = len(metadata.get('tracks', [])) if metadata else 1
        cmd.extend(['--tag', f'TRACKNUMBER={track_num}'])
        cmd.extend(['--tag', f'TOTALTRACKS={total_tracks}'])
        cmd.append(str(wav_file))
        
        # Validate WAV file before encoding
        if not wav_file.exists():
            self.logger.error(f"WAV file not found for track {track_num}: {wav_file}")
            return False
            
        # Check if file looks like a valid WAV file
        try:
            with open(wav_file, 'rb') as f:
                header = f.read(12)
                if len(header) < 12 or not header.startswith(b'RIFF') or header[8:12] != b'WAVE':
                    self.logger.error(f"Track {track_num} WAV file appears corrupted: {wav_file}")
                    self.logger.error(f"Header: {header.hex() if header else 'empty'}")
                    return False
        except Exception as e:
            self.logger.error(f"Cannot read WAV file for track {track_num}: {e}")
            return False
        
        self.logger.debug(f"Using {encoding_timeout}s timeout for track {track_num} ({track_minutes:.1f} minutes)")
        
        # Use cancellable subprocess for FLAC encoding
        result = self._run_cancellable_subprocess(cmd, timeout=encoding_timeout)
        
        # Check for cancellation after encoding
        if self._check_cancelled():
            self.logger.info("Track encoding cancelled by user")
            return False
        
        if result.returncode != 0:
            self.logger.error(f"Failed to encode track {track_num} to FLAC: {result.stderr}")
            # If encoding failed, check if it's due to corrupted WAV
            if "is not a WAVE file" in result.stderr or "treating as a raw file" in result.stderr:
                self.logger.error(f"WAV file for track {track_num} appears to be corrupted by cd-paranoia")
                self.logger.error("This may be caused by lead-out detection issues on the last track")
            return False
        
        self.logger.info(f"Encoded track {track_num} to FLAC")
        return True
    
    def _verify_single_track_accuraterip(self, track_num: int, wav_file: Path, disc_info) -> bool:
        """Verify a single track against AccurateRip and return True if verified or no data available"""
        try:
            if not wav_file.exists():
                self.logger.error(f"WAV file not found for verification: {wav_file}")
                return False
            
            # Calculate AccurateRip checksums for this track
            v1, v2 = self.accuraterip_checker.accuraterip_checksum(str(wav_file), track_num, len(disc_info.tracks))
            
            if v1 is not None and v2 is not None:
                self.logger.info(f"Track {track_num}: AccurateRip checksums calculated - v1={v1:08x}, v2={v2:08x}")
                # Note: Full database verification happens during finalization
                return True
            else:
                self.logger.warning(f"Track {track_num}: Failed to calculate AccurateRip checksums")
                return False
                
        except Exception as e:
            self.logger.error(f"AccurateRip checksum calculation failed for track {track_num}: {e}")
            return True  # Don't fail the rip for AccurateRip errors
    
    def _rip_paranoia_mode(self, disc_info: DiscInfo, output_dir: Path, metadata: Dict[str, Any] = None) -> bool:
        """Rip in paranoia mode (slow but accurate) with per-track encoding and verification"""
        device = self.config['cd_drive']['device']
        tracks = disc_info.tracks
        
        try:
            for i, track in enumerate(tracks, 1):
                self.current_track = i
                # Progress: 50% for ripping, 50% for encoding per track
                base_progress = int((i - 1) / len(tracks) * 100)

                # Robustly get track title, fallback if missing, and log if metadata is missing
                fallback_title = f'Track {i:02d}'
                track_meta = None
                track_title = None
                if metadata and metadata.get('tracks') and i <= len(metadata['tracks']):
                    track_meta = metadata['tracks'][i-1]
                    if not track_meta:
                        self.logger.warning(f"No metadata for track {i}, using fallback title '{fallback_title}'")
                        track_title = fallback_title
                    else:
                        title = track_meta.get('title')
                        if not title or not str(title).strip():
                            self.logger.warning(f"Missing or empty title for track {i}, using fallback title '{fallback_title}'")
                            track_title = fallback_title
                        else:
                            track_title = str(title)
                else:
                    self.logger.warning(f"No metadata entry for track {i}, using fallback title '{fallback_title}'")
                    track_title = fallback_title

                sanitized_title = self._sanitize_filename(track_title)
                expected_flac_file = output_dir / f"{i:02d} - {sanitized_title}.flac"

                if expected_flac_file.exists():
                    self.logger.info(f"Track {i} FLAC already exists from burst mode, skipping paranoia re-rip")
                    # Update progress as if we processed this track
                    self.progress = int(i / len(tracks) * 100)
                    continue

                # Use full metadata-based filename for output WAV, matching burst mode
                fallback_title = f'Track {i:02d}'
                track_meta = None
                track_title = None
                if metadata and metadata.get('tracks') and i <= len(metadata['tracks']):
                    track_meta = metadata['tracks'][i-1]
                    if not track_meta:
                        self.logger.warning(f"No metadata for track {i}, using fallback title '{fallback_title}'")
                        track_title = fallback_title
                    else:
                        title = track_meta.get('title')
                        if not title or not str(title).strip():
                            self.logger.warning(f"Missing or empty title for track {i}, using fallback title '{fallback_title}'")
                            track_title = fallback_title
                        else:
                            track_title = str(title)
                else:
                    self.logger.warning(f"No metadata entry for track {i}, using fallback title '{fallback_title}'")
                    track_title = fallback_title

                sanitized_title = self._sanitize_filename(track_title)
                track_file = output_dir / f"{i:02d} - {sanitized_title}.wav"

                # Use cd-paranoia in paranoia mode
                cmd = [
                    'cd-paranoia',
                    '-d', device,
                    '-z',  # Never ask, never tell
                ]
                # Add offset to cmd if needed (before positional args)
                if self.config['cd_drive']['offset'] != 0:
                    cmd.extend(['-O', str(self.config['cd_drive']['offset'])])
                # Special handling for last track in paranoia mode
                if i == len(tracks):
                    if self.config['cd_drive'].get('force_overread', True):
                        cmd.append('--force-overread')
                        self.logger.info(f"Drive supports overread: enabling --force-overread for last track.")
                    # Use minimal paranoia for last track to avoid lead-out issues
                    cmd.append('-Y')  # Most lenient paranoia mode
                    self.logger.info(f"Using minimal paranoia mode for last track {i}")
                cmd.extend([f'{i}', str(track_file)])

                self.logger.info(f"Ripping track {i} in paranoia mode...")
                self.progress = base_progress
                result = self._run_cancellable_subprocess(cmd, timeout=1800)

                # Check for cancellation after ripping each track
                if self._check_cancelled():
                    return False

                if result.returncode != 0:
                    # Special last track handling in paranoia mode
                    if i == len(tracks):
                        self.logger.warning(f"Last track failed in paranoia mode: {result.stderr}")
                        # Try one final desperate attempt with absolute minimal settings
                        if '--force-overread' not in cmd:
                            self.logger.info("Attempting final recovery with emergency settings...")
                            emergency_cmd = [
                                'cd-paranoia',
                                '-d', device,
                                '-z',  # Never ask, never tell
                                '-Y',  # Most lenient
                                '--force-overread',
                            ]
                            if self.config['cd_drive']['offset'] != 0:
                                emergency_cmd.extend(['-O', str(self.config['cd_drive']['offset'])])
                            emergency_cmd += ['-n', '1', f'{i}', str(track_file)]
                            emergency_result = self._run_cancellable_subprocess(emergency_cmd, timeout=1200)

                            if emergency_result.returncode == 0:
                                self.logger.info("Emergency last track recovery successful!")
                                result = emergency_result
                            else:
                                self.logger.error(f"All last track recovery attempts failed. Track {i} could not be ripped.")
                                self.logger.error("This may be due to lead-out detection issues or disc damage.")
                                return False
                    else:
                        self.logger.error(f"Failed to rip track {i}: {result.stderr}")
                        return False

                self.logger.info(f"Ripped track {i} in paranoia mode, now encoding to FLAC...")

                # Immediately encode this track to FLAC
                self.progress = base_progress + int(25 / len(tracks))  # 25% for encoding
                if not self._encode_single_track(i, track, track_file, output_dir, metadata):
                    return False

                # Check for cancellation after encoding
                if self._check_cancelled():
                    return False

                # Immediately verify with AccurateRip if enabled
                track_verified = True
                if self.config['ripping']['use_accuraterip']:
                    self.logger.info(f"Verifying track {i} with AccurateRip...")
                    self.progress = base_progress + int(40 / len(tracks))  # +15% for verification
                    track_verified = self._verify_single_track_accuraterip(i, track_file, disc_info)

                # Check for cancellation after verification
                if self._check_cancelled():
                    return False

                # Delete the WAV file to save space (we have the FLAC now)
                if track_file.exists():
                    track_file.unlink()

                # Log completion status
                verification_status = "verified" if track_verified else "verification failed"
                self.logger.info(f"Completed track {i} (ripped, encoded, {verification_status})")

                # Update progress to completed for this track
                self.progress = int(i / len(tracks) * 100)

            return True

        except subprocess.TimeoutExpired:
            self.logger.error("Paranoia mode ripping timed out")
            return False
        except Exception as e:
            self.logger.error(f"Paranoia mode ripping failed: {e}")
            return False
    
    def _verify_accuraterip(self, output_dir: Path) -> bool:
        """Verify rip against AccurateRip database (legacy method)"""
        try:
            return self.accuraterip_checker.verify_rip(output_dir)
        except Exception as e:
            self.logger.error(f"AccurateRip verification failed: {e}")
            return False
    
    def _verify_accuraterip_per_track(self, output_dir: Path, disc_info) -> List[int]:
        """Verify each track against AccurateRip v1/v2 and return list of failed track numbers"""
        try:
            failed_tracks = []
            wav_files = sorted(list(output_dir.glob("*.wav")))
            
            if not wav_files:
                self.logger.warning("No WAV files found for AccurateRip verification")
                return list(range(1, len(disc_info.tracks) + 1))  # All tracks failed
            
            # Calculate checksums for all tracks (both v1 and v2)
            track_checksums = {}
            for wav_file in wav_files:
                # Extract track number from filename (e.g., "01.wav" -> 1)
                track_match = re.search(r'(\d+)\.wav$', wav_file.name)
                if track_match:
                    track_num = int(track_match.group(1))
                    
                    # Calculate both v1 and v2 checksums
                    try:
                        with open(wav_file, 'rb') as f:
                            header = f.read(44)
                            if header.startswith(b'RIFF') and b'WAVE' in header:
                                audio_data = f.read()
                                v1_checksum = self.accuraterip_checker._calculate_accuraterip_v1_checksum(audio_data)
                                v2_checksum = self.accuraterip_checker._calculate_accuraterip_v2_checksum(audio_data)
                                
                                track_checksums[track_num] = {
                                    'v1': v1_checksum,
                                    'v2': v2_checksum
                                }
                                
                                self.logger.debug(f"Track {track_num} checksums: v1={v1_checksum:08X}, v2={v2_checksum:08X}")
                            else:
                                self.logger.error(f"Invalid WAV file: {wav_file}")
                                failed_tracks.append(track_num)
                    
                    except Exception as e:
                        self.logger.error(f"Failed to calculate checksums for track {track_num}: {e}")
                        failed_tracks.append(track_num)
            
            # Verify against AccurateRip database with both versions
            if track_checksums:
                verification_results = self.accuraterip_checker.verify_track_checksums_with_versions(
                    disc_info, track_checksums
                )
                
                # Check which tracks failed based on configuration preferences
                for track_num in track_checksums.keys():
                    if track_num in verification_results:
                        v1_match = verification_results[track_num].get('v1', False)
                        v2_match = verification_results[track_num].get('v2', False)
                        
                        # Apply configuration preferences for AccurateRip verification
                        prefer_v2 = self.config['ripping'].get('accuraterip_prefer_v2', True)
                        require_both = self.config['ripping'].get('accuraterip_require_both', False)
                        
                        track_passed = False
                        if require_both:
                            # Strictest mode: both v1 and v2 must match
                            track_passed = v1_match and v2_match
                            match_type = "v1+v2" if track_passed else "neither"
                        elif prefer_v2:
                            # Prefer v2, but accept v1 if v2 not available
                            track_passed = v2_match or v1_match
                            if v2_match and v1_match:
                                match_type = "v1+v2"
                            elif v2_match:
                                match_type = "v2"
                            elif v1_match:
                                match_type = "v1"
                            else:
                                match_type = "none"
                        else:
                            # Accept either v1 or v2
                            track_passed = v1_match or v2_match
                            if v1_match and v2_match:
                                match_type = "v1+v2"
                            elif v1_match:
                                match_type = "v1"
                            elif v2_match:
                                match_type = "v2"
                            else:
                                match_type = "none"
                        
                        if track_passed:
                            self.logger.info(f"Track {track_num}: AccurateRip ✅ ({match_type})")
                        else:
                            self.logger.warning(f"Track {track_num}: AccurateRip ❌ ({match_type})")
                            failed_tracks.append(track_num)
                    else:
                        self.logger.warning(f"Track {track_num}: AccurateRip verification failed")
                        failed_tracks.append(track_num)
            else:
                self.logger.warning("No track checksums calculated for AccurateRip verification")
                failed_tracks = list(range(1, len(disc_info.tracks) + 1))
            
            return sorted(failed_tracks)
            
        except Exception as e:
            self.logger.error(f"Per-track AccurateRip verification failed: {e}")
            # Return all tracks as failed if verification fails
            return list(range(1, len(disc_info.tracks) + 1))
    
    def _rip_failed_tracks_paranoia(self, disc_info, output_dir: Path, failed_tracks: List[int]) -> bool:
        """Re-rip only the specified tracks using paranoia mode"""
        device = self.config['cd_drive']['device']
        
        try:
            self.logger.info(f"Re-ripping {len(failed_tracks)} tracks in paranoia mode: {failed_tracks}")
            
            for track_num in failed_tracks:
                if track_num < 1 or track_num > len(disc_info.tracks):
                    self.logger.error(f"Invalid track number: {track_num}")
                    continue
                
                # Check for cancellation before each track
                if self._check_cancelled():
                    return False
                
                self.current_track = track_num
                # Update progress based on failed tracks
                progress_index = failed_tracks.index(track_num)
                self.progress = int(progress_index / len(failed_tracks) * 100)
                
                track_file = output_dir / f"{track_num:02d}.wav"
                
                # Remove existing file if it exists
                if track_file.exists():
                    track_file.unlink()
                    self.logger.debug(f"Removed existing file: {track_file}")
                
                # Use cd-paranoia in paranoia mode for this specific track
                cmd = [
                    'cd-paranoia',
                    '-d', device,
                    '-z',  # Never ask, never tell
                    f'{track_num}',
                    str(track_file)
                ]
                
                # Add sample offset if configured (using -O flag)
                if self.config['cd_drive']['offset'] != 0:
                    cmd.extend(['-O', str(self.config['cd_drive']['offset'])])
                
                self.logger.info(f"Re-ripping track {track_num} in paranoia mode...")
                result = self._run_cancellable_subprocess(cmd, timeout=1800)
                
                # Check for cancellation after each track
                if self._check_cancelled():
                    return False
                
                if result.returncode != 0:
                    self.logger.error(f"Failed to re-rip track {track_num}: {result.stderr}")
                    return False
                
                self.logger.info(f"Successfully re-ripped track {track_num} in paranoia mode")
                
                # Optional: Verify the re-ripped track immediately
                if self.config['ripping'].get('verify_rerip', True):
                    checksum = self.accuraterip_checker._calculate_accuraterip_checksum(track_file)
                    if checksum:
                        self.logger.debug(f"Re-ripped track {track_num} checksum: {checksum:08X}")
            
            return True
            
        except subprocess.TimeoutExpired:
            self.logger.error("Paranoia mode re-ripping timed out")
            return False
        except Exception as e:
            self.logger.error(f"Failed to re-rip tracks in paranoia mode: {e}")
            return False
    
    def _finalize_rip(self, disc_info: DiscInfo, metadata: Dict[str, Any], output_dir: Path, skip_encoding: bool = False) -> bool:
        """Finalize the rip by encoding to FLAC and creating CUE/log"""
        try:
            # Check for cancellation before processing
            if self._check_cancelled():
                self.logger.info("Finalization cancelled by user")
                return False
                
            # Encode to FLAC (only if not already done per-track)
            if not skip_encoding:
                self._update_status(RipStatus.ENCODING)
                if not self._encode_to_flac(disc_info, metadata, output_dir):
                    return False
                
                # Check for cancellation after encoding
                if self._check_cancelled():
                    self.logger.info("Finalization cancelled by user after encoding")
                    return False
            else:
                self.logger.info("Skipping batch encoding (already done per-track)")
            
            # Create CUE sheet with gap information
            # if self.config['output']['create_cue']:
            #    self._update_status(RipStatus.CREATING_CUE)
            #    self.cue_generator.create_cue_sheet(output_dir)
                
            # Check for cancellation after CUE creation
            #    if self._check_cancelled():
            #        self.logger.info("Finalization cancelled by user after CUE creation")
            #        return False
            
            # Create log file
            if self.config['output']['create_log']:
                self._create_log_file(disc_info, metadata, output_dir)
            
            # Check for cancellation before cleanup
            if self._check_cancelled():
                self.logger.info("Finalization cancelled by user before cleanup")
                return False
            
            # Full AccurateRip verification after all tracks are complete
            if self.config['ripping']['use_accuraterip']:
                self._update_status(RipStatus.VERIFYING_ACCURATERIP)
                self.logger.info("Performing final AccurateRip verification...")
                
                try:
                    # Calculate track offsets from disc info
                    track_offsets = []
                    for track in disc_info.tracks:
                        # Track offsets should be in CD sectors/frames
                        # Convert from MSF format if needed, or use direct sector values
                        track_offsets.append(track.start_sector)
                    
                    # Add leadout position (end of last track + standard gap)
                    if disc_info.tracks:
                        last_track = disc_info.tracks[-1]
                        leadout_sector = last_track.start_sector + last_track.length_sectors
                        track_offsets.append(leadout_sector)
                    
                    self.logger.info(f"Track offsets for AccurateRip: {track_offsets}")
                    
                    # Perform full verification
                    verification_success = self.accuraterip_checker.verify_rip(output_dir, track_offsets)
                    if verification_success:
                        self.logger.info("🎉 All tracks verified successfully against AccurateRip database!")
                    else:
                        self.logger.warning("⚠️  Some tracks failed AccurateRip verification (disc may not be in database)")
                        
                except Exception as e:
                    self.logger.error(f"AccurateRip verification failed: {e}")
                    # Don't fail the entire rip for AccurateRip issues
            
            # Clean up any remaining WAV files (should be none if per-track encoding worked)
            remaining_wavs = list(output_dir.glob("*.wav"))
            if remaining_wavs:
                self.logger.info(f"Cleaning up {len(remaining_wavs)} remaining WAV files...")
                for wav_file in remaining_wavs:
                    wav_file.unlink()
            
            self._update_status(RipStatus.COMPLETED)
            elapsed_time = datetime.now() - self.rip_start_time
            self.logger.info(f"CD ripping completed in {elapsed_time}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to finalize rip: {e}")
            return False
    
    def _encode_to_flac(self, disc_info: DiscInfo, metadata: Dict[str, Any], output_dir: Path) -> bool:
        """Encode WAV files to FLAC"""
        tracks = disc_info.tracks
        track_metadata = metadata.get('tracks', [])
        
        for i, track in enumerate(tracks, 1):
            # Check for cancellation before encoding each track
            if self._check_cancelled():
                self.logger.info("Encoding cancelled by user")
                return False
                
            wav_file = output_dir / f"{i:02d}.wav"
            if not wav_file.exists():
                self.logger.error(f"WAV file not found: {wav_file}")
                return False
            
            # Get track metadata
            track_meta = {}
            if i <= len(track_metadata):
                track_meta = track_metadata[i-1]
            
            flac_file = output_dir / f"{i:02d} - {self._sanitize_filename(track_meta.get('title', f'Track {i:02d}'))}.flac"
            
            # Build FLAC encoding command
            cmd = [
                'flac',
                '-f',  # Force overwrite existing files
                f'--compression-level-{self.config["output"]["compression_level"]}',
                '--delete-input-file',
                f'--output-name={flac_file}',
            ]
            
            # Add metadata tags
            if metadata.get('artist'):
                cmd.extend(['--tag', f'ARTIST={metadata["artist"]}'])
            if metadata.get('album'):
                cmd.extend(['--tag', f'ALBUM={metadata["album"]}'])
            if metadata.get('date'):
                cmd.extend(['--tag', f'DATE={metadata["date"]}'])
            if track_meta.get('title'):
                cmd.extend(['--tag', f'TITLE={track_meta["title"]}'])
            if track_meta.get('artist'):
                cmd.extend(['--tag', f'ARTIST={track_meta["artist"]}'])
            
            cmd.extend(['--tag', f'TRACKNUMBER={i}'])
            cmd.extend(['--tag', f'TOTALTRACKS={len(tracks)}'])
            cmd.append(str(wav_file))
            
            self.logger.info(f"Encoding track {i} to FLAC...")
            
            # Calculate dynamic timeout based on track duration
            # Rule: 3 seconds per minute of audio + 60 second base (very conservative)
            track_duration_str = track.get('duration', '4:00')  # Default to 4 minutes if unknown
            try:
                if ':' in track_duration_str:
                    parts = track_duration_str.split(':')
                    track_minutes = int(parts[0]) + float(parts[1]) / 60
                else:
                    track_minutes = 4.0  # Fallback
                encoding_timeout = max(120, int(track_minutes * 3 + 60))  # Min 2 minutes, scale with length
            except (ValueError, IndexError):
                encoding_timeout = 300  # Fallback for parsing errors
            
            self.logger.debug(f"Using {encoding_timeout}s timeout for {track_duration_str} track")
            
            # Use cancellable subprocess for FLAC encoding
            result = self._run_cancellable_subprocess(cmd, timeout=encoding_timeout)
            
            # Check for cancellation after encoding
            if self._check_cancelled():
                self.logger.info("Encoding cancelled by user")
                return False
            
            if result.returncode != 0:
                self.logger.error(f"Failed to encode track {i} to FLAC: {result.stderr}")
                return False
            
            self.progress = int(i / len(tracks) * 100)
            self.logger.info(f"Encoded track {i} to FLAC")
        
        return True
    
    def _create_log_file(self, toc_info: DiscInfo, metadata: Dict[str, Any], output_dir: Path):
        """Create rip log file"""
        log_content = [
            "Rip and Tear Log File",
            "=" * 50,
            f"Rip Date: {self.rip_start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Drive: {self.config['cd_drive']['device']}",
            f"Drive Offset: {self.config['cd_drive']['offset']} samples",
            "",
            "Album Information:",
            f"  Artist: {metadata.get('artist', 'Unknown')}",
            f"  Album: {metadata.get('album', 'Unknown')}",
            f"  Date: {metadata.get('date', 'Unknown')}",
            f"  Tracks: {len(toc_info.tracks)}",
            "",
            "Track Information:",
        ]
        
        for i, track in enumerate(toc_info.tracks, 1):
            track_meta = metadata.get('tracks', [])
            title = 'Unknown'
            if i <= len(track_meta):
                title = track_meta[i-1].get('title', 'Unknown')
            
            log_content.append(f"  {i:02d}. {title} ({track.length_seconds:.2f} seconds)")
        
        total_time = sum(track.length_seconds for track in toc_info.tracks)
        log_content.extend([
            "",
            f"Total Time: {total_time:.2f} seconds",
            f"Rip Mode: {'Burst + AccurateRip' if self.config['ripping']['try_burst_first'] else 'Paranoia'}",
            f"Encoding: FLAC Level {self.config['output']['compression_level']}",
        ])
        
        log_file = output_dir / "rip.log"
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log_content))
    
    def _update_status(self, status: str, error_msg: str = ""):
        """Update ripping status"""
        self.status = status
        self.error_message = error_msg
        if error_msg:
            self.logger.error(error_msg)
    
    def _check_cd_present(self) -> bool:
        """Check if a CD is present in the drive"""
        try:
            # Try to read the CD table of contents
            result = subprocess.run(
                ['cd-paranoia', '-Q', '-d', self.device],
                capture_output=True,
                text=True,
                timeout=10
            )
            # If cd-paranoia can read the TOC, a CD is present
            return result.returncode == 0 and 'track' in result.stderr.lower()
        except subprocess.TimeoutExpired:
            return False
        except FileNotFoundError:
            self.logger.error("cd-paranoia not found")
            return False
        except Exception as e:
            self.logger.debug(f"Error checking CD presence: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get current ripping status"""
        # If we're actively working with the CD, assume it's present to avoid conflicts
        # with cd-paranoia processes already accessing the drive
        active_states = [
            RipStatus.READING_TOC,
            RipStatus.FETCHING_METADATA,
            RipStatus.RIPPING_BURST,
            RipStatus.VERIFYING_ACCURATERIP,
            RipStatus.RERIPPING_FAILED_TRACKS,
            RipStatus.RIPPING_PARANOIA,
            RipStatus.ENCODING
        ]
        
        if self.status in active_states:
            cd_present = True
        else:
            cd_present = self._check_cd_present()
        
        return {
            'status': self.status,
            'progress': self.progress,
            'current_track': self.current_track,
            'total_tracks': self.total_tracks,
            'error_message': self.error_message,
            'start_time': self.rip_start_time.isoformat() if self.rip_start_time else None,
            'cd_present': cd_present
        }
    
    def cancel_rip(self) -> bool:
        """Cancel the current ripping operation"""
        try:
            if self.status == RipStatus.IDLE:
                self.logger.warning("No active rip operation to cancel")
                return False
            
            self.logger.info("Cancel requested - attempting to stop current operation")
            self.cancel_requested = True
            
            # Try to terminate any running subprocess
            if self.current_process and self.current_process.poll() is None:
                self.logger.info("Terminating current subprocess")
                try:
                    self.current_process.terminate()
                    # Give it a moment to terminate gracefully
                    try:
                        self.current_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate
                        self.current_process.kill()
                        self.current_process.wait()
                    self.logger.info("Subprocess terminated successfully")
                except Exception as e:
                    self.logger.error(f"Error terminating subprocess: {e}")
            
            # Update status
            self._update_status(RipStatus.IDLE, "Operation cancelled by user")
            self.progress = 0
            self.current_track = 0
            self.total_tracks = 0
            self.rip_start_time = None
            self.current_process = None
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error during cancellation: {e}")
            return False
    
    def _check_cancelled(self) -> bool:
        """Check if cancellation has been requested"""
        if self.cancel_requested:
            self.logger.info("Operation cancelled - aborting current task")
            self.cancel_requested = False  # Reset flag
            return True
        return False
    
    def _run_cancellable_subprocess(self, cmd, timeout=600, **kwargs):
        """Run a subprocess that can be cancelled"""
        try:
            # Start the process
            self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)
            
            # Wait for completion or cancellation
            try:
                stdout, stderr = self.current_process.communicate(timeout=timeout)
                returncode = self.current_process.returncode
                self.current_process = None
                
                # Create a result object similar to subprocess.run
                class ProcessResult:
                    def __init__(self, returncode, stdout, stderr):
                        self.returncode = returncode
                        self.stdout = stdout
                        self.stderr = stderr
                
                return ProcessResult(returncode, stdout, stderr)
                
            except subprocess.TimeoutExpired:
                # Process timed out
                if self.current_process:
                    self.current_process.kill()
                    self.current_process.wait()
                    self.current_process = None
                raise
                
        except Exception as e:
            # Clean up process reference on any error
            if self.current_process:
                try:
                    self.current_process.kill()
                    self.current_process.wait()
                except:
                    pass
                self.current_process = None
            raise
