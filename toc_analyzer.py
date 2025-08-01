#!/usr/bin/env python3
"""
TOC Analyzer - Advanced Table of Contents analysis with pre-gap detection
Enhanced to match EAC-level precision for gap detection and HTOA
"""

import subprocess
import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

try:
    import discid
    DISCID_AVAILABLE = True
except ImportError:
    DISCID_AVAILABLE = False

@dataclass
class TrackInfo:
    """Enhanced track information with gap data"""
    number: int
    start_sector: int
    length_sectors: int
    pregap_sectors: int = 0
    postgap_sectors: int = 0
    has_htoa: bool = False
    htoa_length: int = 0
    track_type: str = "audio"
    isrc: Optional[str] = None
    cd_text: Optional[str] = None
    
    @property
    def end_sector(self) -> int:
        """Calculate end sector from start + length"""
        return self.start_sector + self.length_sectors
    
    @property
    def length_seconds(self) -> float:
        """Calculate length in seconds (75 sectors per second)"""
        return self.length_sectors / 75.0
    
    @property 
    def pre_gap(self) -> int:
        """Alias for pregap_sectors for compatibility"""
        return self.pregap_sectors
    
    @property
    def post_gap(self) -> int:
        """Alias for postgap_sectors for compatibility"""
        return self.postgap_sectors

@dataclass
class DiscInfo:
    """Complete disc information"""
    total_sectors: int
    leadout_sector: int
    first_track: int
    last_track: int
    tracks: List[TrackInfo]
    has_cd_text: bool = False
    disc_id: Optional[str] = None  # General disc ID (cd-discid output)
    musicbrainz_disc_id: Optional[str] = None  # MusicBrainz-specific disc ID
    catalog_number: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for metadata fetcher"""
        return {
            'total_sectors': self.total_sectors,
            'leadout_sector': self.leadout_sector,
            'first_track': self.first_track,
            'last_track': self.last_track,
            'tracks': [
                {
                    'number': track.number,
                    'start_sector': track.start_sector,
                    'end_sector': track.end_sector,
                    'length_sectors': track.length_sectors,
                    'length_seconds': track.length_seconds,
                    'pre_gap': track.pre_gap,
                    'post_gap': track.post_gap,
                    'has_htoa': track.has_htoa,
                    'isrc': track.isrc,
                    'cd_text': track.cd_text
                }
                for track in self.tracks
            ],
            'has_cd_text': self.has_cd_text,
            'disc_id': self.disc_id,
            'musicbrainz_disc_id': self.musicbrainz_disc_id,
            'catalog_number': self.catalog_number
        }

class TOCAnalyzer:
    """Advanced TOC analysis with EAC-level precision"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.device = config['cd_drive']['device']
        
    def analyze_disc(self) -> Optional[DiscInfo]:
        """Perform comprehensive disc analysis"""
        try:
            self.logger.info("Starting comprehensive disc analysis...")
            
            # Get basic TOC information
            basic_toc = self._get_basic_toc()
            if not basic_toc:
                self.logger.error("Failed to read basic TOC from CD")
                return None
            
            # Get detailed track information with gaps
            detailed_tracks = self._analyze_track_gaps(basic_toc)
            if not detailed_tracks:
                self.logger.error("Failed to analyze track structure")
                return None
            
            # Detect HTOA (Hidden Track One Audio)
            htoa_info = self._detect_htoa()
            if htoa_info and len(detailed_tracks) > 0:
                detailed_tracks[0].has_htoa = True
                detailed_tracks[0].htoa_length = htoa_info
            
            # Get CD-Text if available
            cd_text = self._read_cd_text()
            
            # CRITICAL: Filter out any duplicate tracks before creating DiscInfo
            # This prevents MusicBrainz from seeing wrong track counts (e.g., 12 instead of 6)
            filtered_tracks = self._filter_duplicate_tracks(detailed_tracks)
            
            # Get disc identification from filtered tracks
            disc_id = self._calculate_precise_disc_id(filtered_tracks)
            
            # Calculate MusicBrainz disc ID using python-discid if available
            musicbrainz_disc_id = self._calculate_musicbrainz_disc_id(filtered_tracks)
            
            disc_info = DiscInfo(
                total_sectors=basic_toc.get('total_sectors', sum(t.length_sectors for t in filtered_tracks)),
                leadout_sector=basic_toc.get('leadout_sector', sum(t.length_sectors for t in filtered_tracks)),
                first_track=basic_toc.get('first_track', 1),
                last_track=basic_toc.get('last_track', len(filtered_tracks)),
                tracks=filtered_tracks,
                has_cd_text=bool(cd_text),
                disc_id=disc_id,
                musicbrainz_disc_id=musicbrainz_disc_id,
                catalog_number=self._get_catalog_number()
            )
            
            self._log_disc_analysis(disc_info)
            return disc_info
            
        except Exception as e:
            self.logger.error(f"Disc analysis failed: {e}")
            return None
    
    def _get_basic_toc(self) -> Optional[Dict[str, Any]]:
        """Get basic TOC using cd-paranoia (most reliable method)"""
        try:
            result = self._get_toc_cd_paranoia()
            if result:
                self.logger.info("TOC obtained using cd-paranoia")
                return result
            else:
                self.logger.error("Failed to get TOC using cd-paranoia")
                return None
        except Exception as e:
            self.logger.error(f"cd-paranoia failed: {e}")
            return None
    
    def _get_toc_cd_paranoia(self) -> Optional[Dict[str, Any]]:
        """Get TOC using cd-paranoia"""
        try:
            result = subprocess.run(
                ['cd-paranoia', '-Q', '-d', self.device],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self.logger.error(f"cd-paranoia failed with return code {result.returncode}")
                if result.stderr:
                    self.logger.error(f"cd-paranoia stderr: {result.stderr}")
                return None
            
            # Log the ACTUAL output so we can see what we're trying to parse
            self.logger.info("=== RAW CD-PARANOIA OUTPUT ===")
            self.logger.info(f"STDOUT:\n{result.stdout}")
            self.logger.info(f"STDERR:\n{result.stderr}")
            self.logger.info("=== END RAW OUTPUT ===")
            
            # cd-paranoia outputs to STDERR, not STDOUT
            output_to_parse = result.stderr if result.stderr.strip() else result.stdout
            
            return self._parse_cd_paranoia_output(output_to_parse)
        
        except subprocess.TimeoutExpired:
            self.logger.error("cd-paranoia timed out")
            return None
        except Exception as e:
            self.logger.error(f"cd-paranoia execution failed: {e}")
            return None
    
    def _get_toc_cd_discid(self) -> Optional[Dict[str, Any]]:
        """Get TOC using cd-discid for precise timing"""
        try:
            result = subprocess.run(
                ['cd-discid', self.device],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return self._parse_discid_output(result.stdout)
        except FileNotFoundError:
            self.logger.debug("cd-discid not available")
        
        return None
    
    def _analyze_track_gaps(self, basic_toc: Dict[str, Any]) -> List[TrackInfo]:
        """Analyze gaps between tracks with EAC-level precision"""
        tracks = []
        
        # Always start with basic tracks as foundation
        tracks = self._create_basic_tracks(basic_toc)
        
        self.logger.info(f"Created {len(tracks)} basic tracks from TOC data")
        
        # Try to enhance with gap information if tools are available
        try:
            # First, try cd-paranoia verbose for additional gap info
            result = subprocess.run(
                ['cd-paranoia', '-Q', '-d', self.device, '-v'],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                enhanced_tracks = self._parse_cd_paranoia_gaps(result.stderr)
                if enhanced_tracks and len(enhanced_tracks) == len(tracks):
                    # Merge gap information into basic tracks
                    for i, enhanced_track in enumerate(enhanced_tracks):
                        if i < len(tracks):
                            tracks[i].pregap_sectors = enhanced_track.pregap_sectors
                    self.logger.info("Enhanced tracks with gap information from cd-paranoia")
                
        except Exception as e:
            self.logger.debug(f"Gap enhancement failed (not critical): {e}")
        
        return tracks
    
    def _detect_htoa(self) -> Optional[int]:
        """Detect Hidden Track One Audio (HTOA)"""
        try:
            # Check if there's audio before track 1
            result = subprocess.run([
                'cd-paranoia', '-d', self.device, 
                '-Q', '-v'  # Query mode with verbose output
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                # Look for negative sector references or pre-track audio
                lines = result.stderr.split('\n')
                for line in lines:
                    if 'track 00' in line.lower() or 'hidden' in line.lower():
                        # Extract HTOA length if found
                        duration_match = re.search(r'(\d+):(\d+)\.(\d+)', line)
                        if duration_match:
                            min_val, sec, frame = map(int, duration_match.groups())
                            return (min_val * 60 + sec) * 75 + frame
                        return 150  # Default 2 seconds if found but can't measure
            
        except Exception as e:
            self.logger.debug(f"HTOA detection failed: {e}")
        
        return None
    
    def _read_cd_text(self) -> Optional[Dict[str, str]]:
        """Read CD-Text information if available with robust parsing"""
        try:
            result = subprocess.run([
                'cdrdao', 'read-cd', '--device', self.device, 
                '--read-subchan', 'rw_raw', '/tmp/temp_cd_text.bin'
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Parse CD-Text from output with robust error handling
                cd_text_info = {}
                lines = result.stderr.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if 'CD_TEXT' in line:
                        try:
                            # Extract CD-Text information with proper validation
                            if 'TITLE' in line and 'TITLE' in line.upper():
                                title_parts = line.split('TITLE', 1)
                                if len(title_parts) > 1:
                                    title = title_parts[1].strip().strip('"\'')
                                    if title:
                                        cd_text_info['title'] = title
                            elif 'PERFORMER' in line and 'PERFORMER' in line.upper():
                                performer_parts = line.split('PERFORMER', 1)
                                if len(performer_parts) > 1:
                                    performer = performer_parts[1].strip().strip('"\'')
                                    if performer:
                                        cd_text_info['performer'] = performer
                        except (IndexError, AttributeError) as e:
                            self.logger.debug(f"Failed to parse CD-Text line '{line}': {e}")
                            continue
                
                return cd_text_info if cd_text_info else None
                
        except Exception as e:
            self.logger.debug(f"CD-Text reading failed: {e}")
        
        return None
    
    def _calculate_precise_disc_id(self, tracks: List[TrackInfo]) -> str:
        """Calculate precise disc ID using track offsets"""
        try:
            # Calculate MusicBrainz-compatible disc ID
            track_offsets = []
            for track in tracks:
                offset = track.start_sector + 150  # Add standard 2-second offset
                track_offsets.append(offset)
            
            # Add leadout offset
            if tracks:
                leadout = tracks[-1].start_sector + tracks[-1].length_sectors + 150
                track_offsets.append(leadout)
            
            # Generate disc ID hash
            disc_id_data = f"{len(tracks)}"
            for offset in track_offsets:
                disc_id_data += f" {offset}"
            
            import hashlib
            return hashlib.sha1(disc_id_data.encode()).hexdigest()[:8].upper()
            
        except Exception as e:
            self.logger.error(f"Disc ID calculation failed: {e}")
            return "UNKNOWN"
    
    def _calculate_musicbrainz_disc_id(self, tracks: List[TrackInfo]) -> Optional[str]:
        """Calculate proper MusicBrainz disc ID using python-discid with correct algorithm"""
        try:
            if not DISCID_AVAILABLE:
                self.logger.warning("python-discid not available, falling back to manual calculation")
                return self._calculate_musicbrainz_disc_id_manual(tracks)
            
            # Use python-discid for proper MusicBrainz disc ID calculation
            self.logger.info("Calculating MusicBrainz disc ID using python-discid")
            
            # Create track offsets list for discid - CRITICAL: correct format for python-discid
            # python-discid.put() expects: first_track, last_track, leadout_offset, [track_offsets]
            
            first_track = 1
            last_track = len(tracks)
            
            # Calculate track offsets (in sectors, including the standard 150-sector offset)
            track_offsets = []
            for track in tracks:
                # MusicBrainz standard: actual CD sectors + 150 (2-second lead-in)
                offset = track.start_sector + 150
                track_offsets.append(offset)
            
            # Calculate leadout offset
            if tracks:
                last_track_info = tracks[-1]
                leadout_offset = last_track_info.start_sector + last_track_info.length_sectors + 150
            else:
                leadout_offset = 150
            
            self.logger.debug(f"MusicBrainz calculation: first={first_track}, last={last_track}, leadout={leadout_offset}")
            self.logger.debug(f"Track offsets: {track_offsets}")
            
            # Use python-discid with correct parameters
            disc = discid.put(first_track, last_track, leadout_offset, track_offsets)
            musicbrainz_id = disc.id
            
            self.logger.info(f"Calculated MusicBrainz disc ID: {musicbrainz_id}")
            return musicbrainz_id
            
        except Exception as e:
            self.logger.error(f"MusicBrainz disc ID calculation failed: {e}")
            return self._calculate_musicbrainz_disc_id_manual(tracks)
    
    def _calculate_musicbrainz_disc_id_manual(self, tracks: List[TrackInfo]) -> Optional[str]:
        """Manual MusicBrainz disc ID calculation following official specification"""
        try:
            import hashlib
            import base64
            
            if not tracks:
                return None
            
            self.logger.info("Calculating MusicBrainz disc ID manually using official algorithm")
            
            # Step 1: Build the hex string according to MusicBrainz specification
            first_track = 1
            last_track = len(tracks)
            
            # Calculate track offsets
            track_offsets = []
            for track in tracks:
                # MusicBrainz uses sector offsets + 150 (2-second lead-in)
                offset = track.start_sector + 150
                track_offsets.append(offset)
            
            # Calculate lead-out offset
            if tracks:
                last_track_info = tracks[-1]
                leadout_offset = last_track_info.start_sector + last_track_info.length_sectors + 150
            else:
                leadout_offset = 150
            
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
            
            self.logger.debug(f"MusicBrainz hex string (length {len(hex_string)}): {hex_string[:100]}...")
            
            # Step 2: SHA-1 hash the hex string
            sha1 = hashlib.sha1()
            sha1.update(hex_string.encode('ascii'))
            digest = sha1.digest()
            
            # Step 3: Base64 encode with MusicBrainz character substitutions
            # Standard base64
            b64 = base64.b64encode(digest).decode('ascii')
            
            # MusicBrainz substitutions: + -> ., / -> _, = -> -
            mb_b64 = b64.replace('+', '.').replace('/', '_').replace('=', '-')
            
            self.logger.info(f"Manual MusicBrainz disc ID: {mb_b64}")
            return mb_b64
            
        except Exception as e:
            self.logger.error(f"Manual MusicBrainz disc ID calculation failed: {e}")
            return self._calculate_musicbrainz_disc_id_fallback(tracks)
    
    def _calculate_musicbrainz_disc_id_fallback(self, tracks: List[TrackInfo]) -> Optional[str]:
        """Fallback MusicBrainz disc ID calculation using cd-discid command"""
        try:
            self.logger.info("Using cd-discid fallback for MusicBrainz disc ID")
            
            result = subprocess.run(
                ['cd-discid', self.device],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # cd-discid output format: "discid track_count offset1 offset2 ... leadout_offset track_length"
                parts = result.stdout.strip().split()
                if len(parts) >= 1:
                    disc_id = parts[0]
                    self.logger.info(f"MusicBrainz disc ID from cd-discid: {disc_id}")
                    return disc_id
            
            self.logger.warning("cd-discid fallback failed")
            return None
            
        except Exception as e:
            self.logger.error(f"MusicBrainz disc ID fallback failed: {e}")
            return None
    
    def _filter_duplicate_tracks(self, tracks: List[TrackInfo]) -> List[TrackInfo]:
        """Filter out duplicate tracks by track number to prevent MusicBrainz errors"""
        try:
            if not tracks:
                return tracks
            
            # Check for duplicates
            track_numbers = [track.number for track in tracks]
            unique_numbers = list(set(track_numbers))
            
            if len(track_numbers) == len(unique_numbers):
                self.logger.debug(f"No duplicate tracks found ({len(tracks)} tracks)")
                return tracks
            
            # Filter duplicates - keep first occurrence of each track number
            self.logger.warning(f"Found duplicate tracks! Raw: {track_numbers}, Unique: {unique_numbers}")
            
            seen_numbers = set()
            filtered_tracks = []
            
            for track in tracks:
                if track.number not in seen_numbers:
                    seen_numbers.add(track.number)
                    filtered_tracks.append(track)
                else:
                    self.logger.warning(f"Removing duplicate track {track.number}")
            
            self.logger.info(f"Filtered tracks: {len(tracks)} → {len(filtered_tracks)} (removed {len(tracks) - len(filtered_tracks)} duplicates)")
            return filtered_tracks
            
        except Exception as e:
            self.logger.error(f"Error filtering duplicate tracks: {e}")
            return tracks  # Return original tracks if filtering fails
    
    def _get_catalog_number(self) -> Optional[str]:
        """Get catalog number (UPC/EAN) if available"""
        try:
            result = subprocess.run([
                'cd-info', '--no-header', '--no-device-info', self.device
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'catalog' in line.lower() or 'upc' in line.lower():
                        match = re.search(r'(\d{13})', line)
                        if match:
                            return match.group(1)
                            
        except Exception as e:
            self.logger.debug(f"Catalog number detection failed: {e}")
        
        return None
    
    def _parse_cd_paranoia_gaps(self, output: str) -> List[TrackInfo]:
        """Parse cd-paranoia verbose output for gap information"""
        tracks = []
        lines = output.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('track'):
                # Parse: "track 01.  audio    00:32.17    760 [00:02.17]"
                # The part in brackets is often the pregap
                parts = line.split()
                if len(parts) >= 4 and parts[2] == 'audio':
                    track_num = int(parts[1].rstrip('.'))
                    duration = parts[3]
                    
                    # Convert duration to sectors (75 sectors per second)
                    sectors = 0
                    if ':' in duration:
                        time_parts = duration.split(':')
                        minutes = int(time_parts[0])
                        seconds = float(time_parts[1])
                        sectors = int((minutes * 60 + seconds) * 75)
                    
                    # Look for pregap info in brackets
                    pregap_sectors = 0
                    bracket_match = re.search(r'\[(\d+):(\d+\.\d+)\]', line)
                    if bracket_match:
                        pregap_min = int(bracket_match.group(1))
                        pregap_sec = float(bracket_match.group(2))
                        pregap_sectors = int((pregap_min * 60 + pregap_sec) * 75)
                    
                    track = TrackInfo(
                        number=track_num,
                        start_sector=0,
                        length_sectors=sectors,
                        pregap_sectors=pregap_sectors,
                        track_type='audio'
                    )
                    tracks.append(track)
        
        # Calculate start sectors
        current_sector = 0
        for track in tracks:
            track.start_sector = current_sector
            current_sector += track.length_sectors
        
        return tracks

    def _parse_cd_paranoia_output(self, output: str) -> Dict[str, Any]:
        """Parse cd-paranoia -Q output based on actual cd-paranoia format"""
        tracks = []
        lines = output.strip().split('\n')
        
        total_sectors = 0
        leadout_sector = 0
        
        self.logger.info(f"Parsing cd-paranoia output: {len(lines)} lines")
        
        # DEBUG: Log the raw cd-paranoia output to see what we're actually parsing
        self.logger.info("=== RAW CD-PARANOIA OUTPUT FOR DEBUGGING ===")
        for i, line in enumerate(lines[:25]):  # Show first 25 lines
            self.logger.info(f"Line {i:2d}: '{line}'")
        self.logger.info("=== END RAW OUTPUT ===")
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            self.logger.debug(f"Line {line_num}: '{line}'")
            
            # Real cd-paranoia -Q output format:
            # " 1. 19497 [04:19.72] 0 [00:00.00] OK no 2"
            # Track number, sectors, [duration], start_sector, [start_time], status, pre, ch
            
            # Flexible pattern that matches the essential parts but allows variation
            track_pattern = r'^\s*(\d{1,2})\.\s+(\d+)\s+\[(\d+):(\d+)\.(\d+)\]\s+(\d+)\s+\[(\d+):(\d+)\.(\d+)\]\s+(\w+)'
            track_match = re.match(track_pattern, line)
            
            # If the main pattern doesn't match, try a simpler fallback pattern
            if not track_match:
                # Simpler pattern: " 1. 19497 [04:19.72] ..."
                simple_pattern = r'^\s*(\d{1,2})\.\s+(\d+)\s+\[(\d+):(\d+)\.(\d+)\]'
                simple_match = re.match(simple_pattern, line)
                if simple_match:
                    self.logger.info(f"Using simple pattern for line: '{line}'")
                    track_match = simple_match
            
            if track_match:
                try:
                    track_num = int(track_match.group(1))
                    sectors = int(track_match.group(2))
                    minutes = int(track_match.group(3))
                    seconds = int(track_match.group(4))
                    frames = int(track_match.group(5))
                    
                    # Handle different match group counts
                    if len(track_match.groups()) >= 10:
                        # Full pattern match
                        start_sector = int(track_match.group(6))
                        status = track_match.group(10)
                    else:
                        # Simple pattern match - estimate start sector
                        start_sector = sum(t['sectors'] for t in tracks)  # Rough estimate
                        status = 'unknown'
                    
                    # Check if we already have this track (avoid duplicates)
                    existing_track = next((t for t in tracks if t['number'] == track_num), None)
                    if existing_track:
                        self.logger.debug(f"Track {track_num} already exists, skipping duplicate")
                        continue
                    
                    # Flexible validation - allow reasonable track numbers and lengths
                    if track_num <= 0 or track_num > 99:
                        self.logger.debug(f"Skipping invalid track number: {track_num}")
                        continue
                    
                    # More flexible track length validation (1 second to 90 minutes)
                    min_sectors = 75      # 1 second minimum
                    max_sectors = 405000  # 90 minutes maximum
                    if sectors < min_sectors or sectors > max_sectors:
                        self.logger.info(f"Skipping track {track_num} with unusual length: {sectors} sectors ({sectors/75:.1f} seconds)")
                        continue
                    
                    # Prefer tracks with "OK" status but don't require it
                    if status.lower() not in ['ok', 'good', 'pass', 'unknown']:
                        self.logger.debug(f"Track {track_num} has status '{status}' - accepting anyway")
                    
                    # Warn about non-sequential track numbers but accept them
                    if tracks and track_num > tracks[-1]['number'] + 1:
                        self.logger.warning(f"Non-sequential track number {track_num} after track {tracks[-1]['number']} - accepting anyway")
                    
                    duration = f"{minutes}:{seconds:02d}.{frames:02d}"
                    
                    tracks.append({
                        'number': track_num,
                        'duration': duration,
                        'sectors': sectors,
                        'start_sector': start_sector,
                        'type': 'audio'
                    })
                    total_sectors += sectors
                    self.logger.info(f"✓ Accepted track {track_num}: {duration} ({sectors} sectors, {sectors/75:.1f}s, start: {start_sector})")
                    
                except (ValueError, IndexError) as e:
                    self.logger.warning(f"Could not parse track from line '{line}': {e}")
            
            # Log lines that look like tracks but don't match our pattern
            elif re.search(r'^\s*\d+\.\s+\d+\s+\[', line):
                self.logger.warning(f"❌ Track-like line didn't match pattern: '{line}'")
                    
            # Look for any total information if present
            elif 'total' in line.lower() and 'sectors' in line.lower():
                total_pattern = r'(\d+)\s+sectors'
                total_match = re.search(total_pattern, line, re.IGNORECASE)
                if total_match:
                    leadout_sector = int(total_match.group(1))
                    self.logger.info(f"✓ Found total: {leadout_sector} sectors")
        
        # Sort tracks by track number
        tracks.sort(key=lambda t: t['number'])
        
        # Calculate total sectors if not found
        if not leadout_sector and tracks:
            last_track = tracks[-1]
            leadout_sector = last_track['start_sector'] + last_track['sectors']
        
        self.logger.info(f"🎵 Track parsing summary: {len(tracks)} valid audio tracks found")
        if tracks:
            self.logger.info(f"   📀 Track range: {tracks[0]['number']} to {tracks[-1]['number']}")
            total_duration = sum(t['sectors'] for t in tracks) / 75 / 60  # minutes
            self.logger.info(f"   ⏱️  Total duration: {total_duration:.1f} minutes")
        
        if not tracks:
            self.logger.error("❌ No tracks found in cd-paranoia output")
            # Log the raw output for debugging
            self.logger.error("Raw output was:")
            for i, line in enumerate(lines[:20]):  # First 20 lines for more context
                self.logger.error(f"  {i}: '{line}'")
            return {
                'tracks': [],
                'total_sectors': 0,
                'leadout_sector': 0,
                'first_track': 1,
                'last_track': 0
            }
        
        result = {
            'tracks': tracks,
            'total_sectors': leadout_sector if leadout_sector > 0 else total_sectors,
            'leadout_sector': leadout_sector if leadout_sector > 0 else total_sectors,
            'first_track': tracks[0]['number'],
            'last_track': tracks[-1]['number']
        }
        
        self.logger.info(f"=== PARSE RESULT ===")
        self.logger.info(f"Result keys: {list(result.keys())}")
        self.logger.info(f"Tracks count: {len(result['tracks'])}")
        self.logger.info(f"Total sectors: {result['total_sectors']}")
        self.logger.info(f"Track range: {result['first_track']}-{result['last_track']}")
        for track in result['tracks']:
            self.logger.info(f"  Track {track['number']}: {track['sectors']} sectors")
        self.logger.info(f"=== END PARSE RESULT ===")
        
        return result
    
    def _create_basic_tracks(self, basic_toc: Dict[str, Any]) -> List[TrackInfo]:
        """Create basic track info from parsed TOC data"""
        tracks = []
        
        self.logger.info(f"=== _create_basic_tracks DEBUG ===")
        self.logger.info(f"basic_toc type: {type(basic_toc)}")
        self.logger.info(f"basic_toc keys: {list(basic_toc.keys()) if basic_toc else 'None'}")
        self.logger.info(f"basic_toc content: {basic_toc}")
        
        if not basic_toc:
            self.logger.error("No basic_toc data available for creating tracks")
            return []
            
        # Try to extract track info from TOC data
        track_data = basic_toc.get('tracks', [])
        self.logger.info(f"track_data type: {type(track_data)}")
        self.logger.info(f"track_data length: {len(track_data) if track_data else 0}")
        self.logger.info(f"track_data content: {track_data}")
        
        if not track_data:
            self.logger.error("No track data found in TOC")
            return []
            
        try:
            for i, track_info in enumerate(track_data):
                self.logger.info(f"Processing track {i}: {track_info}")
                if not isinstance(track_info, dict):
                    self.logger.warning(f"Invalid track data format: {track_info}")
                    continue
                    
                # Use start_sector from parsed data if available, otherwise calculate
                start_sector = track_info.get('start_sector', 0)
                track_number = track_info.get('number', len(tracks) + 1)

                # Skip appending if the track is a leadout and its number equals len(tracks) + 1
                if track_number == len(tracks) + 1 and track_info.get('track_type') == 'leadout':
                    self.logger.info(f"Skipping leadout track with number {track_number}")
                    continue

                track = TrackInfo(
                    number=track_number,
                    start_sector=start_sector,
                    length_sectors=track_info.get('sectors', 0),
                    track_type='audio'
                )
                tracks.append(track)
                self.logger.info(f"✓ Created track {track.number}: {track.length_sectors} sectors, start: {track.start_sector}")
                
        except Exception as e:
            self.logger.error(f"Error creating basic tracks: {e}")
            self.logger.error(f"basic_toc content: {basic_toc}")
            return []
        
        self.logger.info(f"=== _create_basic_tracks RESULT: {len(tracks)} tracks ===")
        return tracks
    
    def _log_disc_analysis(self, disc_info: DiscInfo):
        """Log comprehensive disc analysis results"""
        self.logger.info("=== Disc Analysis Results ===")
        self.logger.info(f"Disc ID: {disc_info.disc_id}")
        if disc_info.musicbrainz_disc_id:
            self.logger.info(f"MusicBrainz Disc ID: {disc_info.musicbrainz_disc_id}")
        self.logger.info(f"Total sectors: {disc_info.total_sectors}")
        self.logger.info(f"Tracks: {disc_info.first_track}-{disc_info.last_track}")
        self.logger.info(f"CD-Text available: {disc_info.has_cd_text}")
        
        if disc_info.catalog_number:
            self.logger.info(f"Catalog number: {disc_info.catalog_number}")
        
        for track in disc_info.tracks:
            gap_info = ""
            if track.pregap_sectors > 0:
                gap_info += f" [Pregap: {track.pregap_sectors/75:.2f}s]"
            if track.has_htoa:
                gap_info += f" [HTOA: {track.htoa_length/75:.2f}s]"
            
            self.logger.info(f"Track {track.number:02d}: "
                           f"{track.length_sectors} sectors{gap_info}")
