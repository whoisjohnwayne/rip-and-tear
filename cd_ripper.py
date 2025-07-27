#!/usr/bin/env python3
"""
CD Ripper - Main ripping functionality
Handles the actual CD ripping process with burst mode, AccurateRip verification,
and fallback to cdparanoia
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
                return False
            
            # Get comprehensive CD information with gap detection
            disc_info = self.toc_analyzer.analyze_disc()
            if not disc_info:
                self._update_status(RipStatus.ERROR, "Failed to analyze CD structure")
                return False
            
            # Check for cancellation
            if self._check_cancelled():
                return False
            
            # Validate that we have tracks
            if not hasattr(disc_info, 'tracks') or not disc_info.tracks:
                self._update_status(RipStatus.ERROR, "No tracks found on CD - disc may be damaged or unreadable")
                return False
            
            self.total_tracks = len(disc_info.tracks)
            self.logger.info(f"Found {self.total_tracks} tracks on CD")
            
            # Fetch metadata
            self._update_status(RipStatus.FETCHING_METADATA)
            
            # Check for cancellation
            if self._check_cancelled():
                return False
                
            metadata = self.metadata_fetcher.get_metadata(disc_info.to_dict())
            
            # Create output directory for this album
            album_dir = self._create_album_directory(metadata)
            
            # Try burst mode rip first
            if self.config['ripping']['try_burst_first']:
                # Check for cancellation
                if self._check_cancelled():
                    return False
                    
                self._update_status(RipStatus.RIPPING_BURST)
                burst_success = self._rip_burst_mode(disc_info, album_dir)
                
                # Check for cancellation
                if self._check_cancelled():
                    return False
                
                if burst_success and self.config['ripping']['use_accuraterip']:
                    self._update_status(RipStatus.VERIFYING_ACCURATERIP)
                    failed_tracks = self._verify_accuraterip_per_track(album_dir, disc_info)
                    
                    # Check for cancellation
                    if self._check_cancelled():
                        return False
                    
                    if not failed_tracks:
                        self.logger.info("All tracks verified with AccurateRip in burst mode")
                        return self._finalize_rip(disc_info, metadata, album_dir)
                    else:
                        self.logger.warning(f"AccurateRip verification failed for tracks: {failed_tracks}")
                        self.logger.info("Re-ripping failed tracks in paranoia mode...")
                        
                        # Re-rip only the failed tracks in paranoia mode
                        self._update_status(RipStatus.RERIPPING_FAILED_TRACKS)
                        if self._rip_failed_tracks_paranoia(disc_info, album_dir, failed_tracks):
                            self.logger.info("Successfully re-ripped failed tracks in paranoia mode")
                            return self._finalize_rip(disc_info, metadata, album_dir)
                        else:
                            self.logger.error("Failed to re-rip tracks in paranoia mode")
                            return False
                elif burst_success:
                    self.logger.info("Burst mode rip completed (AccurateRip verification disabled)")
                    return self._finalize_rip(disc_info, metadata, album_dir)
            
            # Fallback to full paranoia mode if burst mode failed completely
            self._update_status(RipStatus.RIPPING_PARANOIA)
            self.logger.info("Burst mode failed, using full paranoia mode for all tracks")
            if self._rip_paranoia_mode(disc_info, album_dir):
                return self._finalize_rip(disc_info, metadata, album_dir)
            else:
                self._update_status(RipStatus.ERROR, "Both burst and paranoia mode ripping failed")
                return False
                
        except Exception as e:
            self.logger.error(f"CD ripping failed: {e}")
            self._update_status(RipStatus.ERROR, str(e))
            return False
    
    def _get_cd_toc(self) -> Optional[Dict[str, Any]]:
        """Get CD table of contents"""
        device = self.config['cd_drive']['device']
        
        try:
            # Use cdparanoia to get TOC
            result = subprocess.run(
                ['cdparanoia', '-Q', '-d', device],
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
        """Parse cdparanoia TOC output"""
        tracks = []
        lines = toc_output.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('track'):
                # Parse track line: "track 01.  audio    00:32.17    760 [00:02.17]"
                parts = line.split()
                if len(parts) >= 4 and parts[2] == 'audio':
                    track_num = int(parts[1].rstrip('.'))
                    duration = parts[3]
                    tracks.append({
                        'number': track_num,
                        'duration': duration,
                        'type': 'audio'
                    })
        
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
    
    def _rip_burst_mode(self, disc_info: DiscInfo, output_dir: Path) -> bool:
        """Rip in burst mode (fast) with enhanced gap handling"""
        device = self.config['cd_drive']['device']
        tracks = disc_info.tracks
        
        try:
            for i, track in enumerate(tracks, 1):
                self.current_track = i
                self.progress = int((i - 1) / len(tracks) * 100)
                
                track_file = output_dir / f"{i:02d}.wav"
                
                # Enhanced ripping with gap handling
                cmd = [
                    'cdparanoia',
                    '-d', device,
                    '-Z',  # Disable all paranoia checks for speed (burst mode)
                    '-z',  # Never ask, never tell
                ]
                
                # Handle pre-gaps and HTOA
                if track.has_htoa and i == 1:
                    # Rip HTOA if present
                    htoa_file = output_dir / "00.wav"
                    htoa_cmd = cmd + [f'-{track.htoa_length//75}', str(htoa_file)]
                    
                    if self.config['cd_drive']['offset'] != 0:
                        htoa_cmd.extend(['-O', str(self.config['cd_drive']['offset'])])
                    
                    self.logger.info(f"Ripping HTOA ({track.htoa_length/75:.2f} seconds)")
                    subprocess.run(htoa_cmd, capture_output=True, text=True, timeout=600)
                
                # Standard track ripping
                track_cmd = cmd + [f'{i}', str(track_file)]
                
                if self.config['cd_drive']['offset'] != 0:
                    track_cmd.extend(['-O', str(self.config['cd_drive']['offset'])])
                
                # Check for cancellation before ripping
                if self._check_cancelled():
                    return False
                
                result = self._run_cancellable_subprocess(track_cmd, timeout=600)
                
                # Check for cancellation after ripping
                if self._check_cancelled():
                    return False
                
                if result.returncode != 0:
                    self.logger.error(f"Failed to rip track {i}: {result.stderr}")
                    return False
                
                self.logger.info(f"Ripped track {i} in burst mode")
            
            return True
            
        except subprocess.TimeoutExpired:
            self.logger.error("Burst mode ripping timed out")
            return False
        except Exception as e:
            self.logger.error(f"Burst mode ripping failed: {e}")
            return False
    
    def _rip_paranoia_mode(self, disc_info: DiscInfo, output_dir: Path) -> bool:
        """Rip in paranoia mode (slow but accurate) with gap preservation"""
        device = self.config['cd_drive']['device']
        tracks = disc_info.tracks
        
        try:
            for i, track in enumerate(tracks, 1):
                self.current_track = i
                self.progress = int((i - 1) / len(tracks) * 100)
                
                track_file = output_dir / f"{i:02d}.wav"
                
                # Use cdparanoia in paranoia mode
                cmd = [
                    'cdparanoia',
                    '-d', device,
                    '-z',  # Never ask, never tell
                    f'{i}',
                    str(track_file)
                ]
                
                # Add sample offset if configured (using -O flag)
                if self.config['cd_drive']['offset'] != 0:
                    cmd.extend(['-O', str(self.config['cd_drive']['offset'])])
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
                
                if result.returncode != 0:
                    self.logger.error(f"Failed to rip track {i}: {result.stderr}")
                    return False
                
                self.logger.info(f"Ripped track {i} in paranoia mode")
            
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
                
                self.current_track = track_num
                # Update progress based on failed tracks
                progress_index = failed_tracks.index(track_num)
                self.progress = int(progress_index / len(failed_tracks) * 100)
                
                track_file = output_dir / f"{track_num:02d}.wav"
                
                # Remove existing file if it exists
                if track_file.exists():
                    track_file.unlink()
                    self.logger.debug(f"Removed existing file: {track_file}")
                
                # Use cdparanoia in paranoia mode for this specific track
                cmd = [
                    'cdparanoia',
                    '-d', device,
                    '-z',  # Never ask, never tell
                    f'{track_num}',
                    str(track_file)
                ]
                
                # Add sample offset if configured (using -O flag)
                if self.config['cd_drive']['offset'] != 0:
                    cmd.extend(['-O', str(self.config['cd_drive']['offset'])])
                
                self.logger.info(f"Re-ripping track {track_num} in paranoia mode...")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
                
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
    
    def _finalize_rip(self, disc_info: DiscInfo, metadata: Dict[str, Any], output_dir: Path) -> bool:
        """Finalize the rip by encoding to FLAC and creating CUE/log"""
        try:
            # Encode to FLAC
            self._update_status(RipStatus.ENCODING)
            if not self._encode_to_flac(disc_info, metadata, output_dir):
                return False
            
            # Create CUE sheet with gap information
            if self.config['output']['create_cue']:
                self._update_status(RipStatus.CREATING_CUE)
                self.cue_generator.create_cue_sheet(disc_info, metadata, output_dir)
            
            # Create log file
            if self.config['output']['create_log']:
                self._create_log_file(disc_info, metadata, output_dir)
            
            # Clean up WAV files
            for wav_file in output_dir.glob("*.wav"):
                wav_file.unlink()
            
            self._update_status(RipStatus.COMPLETED)
            elapsed_time = datetime.now() - self.rip_start_time
            self.logger.info(f"CD ripping completed in {elapsed_time}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to finalize rip: {e}")
            return False
    
    def _encode_to_flac(self, toc_info: Dict[str, Any], metadata: Dict[str, Any], output_dir: Path) -> bool:
        """Encode WAV files to FLAC"""
        tracks = toc_info['tracks']
        track_metadata = metadata.get('tracks', [])
        
        for i, track in enumerate(tracks, 1):
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
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to encode track {i} to FLAC: {result.stderr}")
                return False
            
            self.progress = int(i / len(tracks) * 100)
            self.logger.info(f"Encoded track {i} to FLAC")
        
        return True
    
    def _create_log_file(self, toc_info: Dict[str, Any], metadata: Dict[str, Any], output_dir: Path):
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
            f"  Tracks: {len(toc_info['tracks'])}",
            "",
            "Track Information:",
        ]
        
        for i, track in enumerate(toc_info['tracks'], 1):
            track_meta = metadata.get('tracks', [])
            title = 'Unknown'
            if i <= len(track_meta):
                title = track_meta[i-1].get('title', 'Unknown')
            
            log_content.append(f"  {i:02d}. {title} ({track['duration']})")
        
        log_content.extend([
            "",
            f"Total Time: {toc_info['total_time']}",
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
                ['cdparanoia', '-Q', '-d', self.device],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # If cdparanoia can read the TOC, a CD is present
            return result.returncode == 0 and 'track' in result.stderr.lower()
            
        except subprocess.TimeoutExpired:
            self.logger.warning("CD check timed out")
            return False
        except FileNotFoundError:
            self.logger.error("cdparanoia not found")
            return False
        except Exception as e:
            self.logger.debug(f"Error checking CD presence: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get current ripping status"""
        # If we're actively working with the CD, assume it's present to avoid conflicts
        # with cdparanoia processes already accessing the drive
        active_states = [
            RipStatus.READING_TOC,
            RipStatus.FETCHING_METADATA,
            RipStatus.RIPPING_BURST,
            RipStatus.VERIFYING_ACCURATERIP,
            RipStatus.RERIPPING_FAILED_TRACKS,
            RipStatus.RIPPING_PARANOIA,
            RipStatus.ENCODING,
            RipStatus.CREATING_CUE
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
