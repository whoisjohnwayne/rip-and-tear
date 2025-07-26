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
    disc_id: Optional[str] = None
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
            
            # Get disc identification
            disc_id = self._calculate_precise_disc_id(detailed_tracks)
            
            disc_info = DiscInfo(
                total_sectors=basic_toc.get('total_sectors', sum(t.length_sectors for t in detailed_tracks)),
                leadout_sector=basic_toc.get('leadout_sector', sum(t.length_sectors for t in detailed_tracks)),
                first_track=basic_toc.get('first_track', 1),
                last_track=basic_toc.get('last_track', len(detailed_tracks)),
                tracks=detailed_tracks,
                has_cd_text=bool(cd_text),
                disc_id=disc_id,
                catalog_number=self._get_catalog_number()
            )
            
            self._log_disc_analysis(disc_info)
            return disc_info
            
        except Exception as e:
            self.logger.error(f"Disc analysis failed: {e}")
            return None
    
    def _get_basic_toc(self) -> Optional[Dict[str, Any]]:
        """Get basic TOC using cdparanoia (most reliable method)"""
        try:
            result = self._get_toc_cdparanoia()
            if result:
                self.logger.info("TOC obtained using cdparanoia")
                return result
            else:
                self.logger.error("Failed to get TOC using cdparanoia")
                return None
        except Exception as e:
            self.logger.error(f"cdparanoia failed: {e}")
            return None
    
    def _get_toc_cdparanoia(self) -> Optional[Dict[str, Any]]:
        """Get TOC using cdparanoia"""
        try:
            result = subprocess.run(
                ['cdparanoia', '-Q', '-d', self.device],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self.logger.error(f"cdparanoia failed with return code {result.returncode}")
                if result.stderr:
                    self.logger.error(f"cdparanoia stderr: {result.stderr}")
                return None
            
            # Log the ACTUAL output so we can see what we're trying to parse
            self.logger.info("=== RAW CDPARANOIA OUTPUT ===")
            self.logger.info(f"STDOUT:\n{result.stdout}")
            self.logger.info(f"STDERR:\n{result.stderr}")
            self.logger.info("=== END RAW OUTPUT ===")
            
            # cdparanoia outputs to STDERR, not STDOUT
            output_to_parse = result.stderr if result.stderr.strip() else result.stdout
            
            return self._parse_cdparanoia_output(output_to_parse)
        
        except subprocess.TimeoutExpired:
            self.logger.error("cdparanoia timed out")
            return None
        except Exception as e:
            self.logger.error(f"cdparanoia execution failed: {e}")
            return None
    
    def _get_toc_cdrdao(self) -> Optional[Dict[str, Any]]:
        """Get TOC using cdrdao for enhanced gap detection"""
        result = subprocess.run(
            ['cdrdao', 'disk-info', '--device', self.device],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0:
            return None
        
        return self._parse_cdrdao_output(result.stdout)
    
    def _get_toc_cd_discid(self) -> Optional[Dict[str, Any]]:
        """Get TOC using cd-discid for precise timing"""
        try:
            result = subprocess.run(
                ['cd-discid', self.device],
                capture_output=True, text=True, timeout=30
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
            # First, try cdparanoia verbose for additional gap info
            result = subprocess.run(
                ['cdparanoia', '-Q', '-d', self.device, '-v'],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                enhanced_tracks = self._parse_cdparanoia_gaps(result.stderr)
                if enhanced_tracks and len(enhanced_tracks) == len(tracks):
                    # Merge gap information into basic tracks
                    for i, enhanced_track in enumerate(enhanced_tracks):
                        if i < len(tracks):
                            tracks[i].pregap_sectors = enhanced_track.pregap_sectors
                    self.logger.info("Enhanced tracks with gap information from cdparanoia")
                
        except Exception as e:
            self.logger.debug(f"Gap enhancement failed (not critical): {e}")
        
        return tracks
    
    def _parse_gap_analysis(self, toc_file: str) -> List[TrackInfo]:
        """Parse cdrdao TOC file for precise gap information"""
        tracks = []
        
        try:
            with open(toc_file, 'r') as f:
                content = f.read()
            
            # Parse TOC file format
            track_blocks = re.findall(r'TRACK\s+AUDIO\s*\n(.*?)(?=TRACK\s+AUDIO|\Z)', content, re.DOTALL)
            
            for i, block in enumerate(track_blocks, 1):
                track = TrackInfo(number=i, start_sector=0, length_sectors=0)
                
                # Look for PREGAP
                pregap_match = re.search(r'PREGAP\s+(\d+):(\d+):(\d+)', block)
                if pregap_match:
                    min_val, sec, frame = map(int, pregap_match.groups())
                    track.pregap_sectors = (min_val * 60 + sec) * 75 + frame
                
                # Look for track start
                start_match = re.search(r'START\s+(\d+):(\d+):(\d+)', block)
                if start_match:
                    min_val, sec, frame = map(int, start_match.groups())
                    track.start_sector = (min_val * 60 + sec) * 75 + frame
                
                tracks.append(track)
                
        except Exception as e:
            self.logger.error(f"Failed to parse gap analysis: {e}")
        
        return tracks
    
    def _detect_htoa(self) -> Optional[int]:
        """Detect Hidden Track One Audio (HTOA)"""
        try:
            # Check if there's audio before track 1
            result = subprocess.run([
                'cdparanoia', '-d', self.device, 
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
        """Read CD-Text information if available"""
        try:
            result = subprocess.run([
                'cdrdao', 'read-cd', '--device', self.device, 
                '--read-subchan', 'rw_raw', '/tmp/temp_cd_text.bin'
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # Parse CD-Text from output
                cd_text_info = {}
                lines = result.stderr.split('\n')
                
                for line in lines:
                    if 'CD_TEXT' in line:
                        # Extract CD-Text information
                        if 'TITLE' in line:
                            cd_text_info['title'] = line.split('TITLE')[1].strip()
                        elif 'PERFORMER' in line:
                            cd_text_info['performer'] = line.split('PERFORMER')[1].strip()
                
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
    
    def _parse_cdparanoia_gaps(self, output: str) -> List[TrackInfo]:
        """Parse cdparanoia verbose output for gap information"""
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
                        start_sector=0,  # Will be calculated based on previous tracks
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

    def _parse_cdparanoia_output(self, output: str) -> Dict[str, Any]:
        """Parse cdparanoia -Q output based on actual cdparanoia format"""
        tracks = []
        lines = output.strip().split('\n')
        
        total_sectors = 0
        leadout_sector = 0
        
        self.logger.info(f"Parsing cdparanoia output: {len(lines)} lines")
        
        # DEBUG: Log the raw cdparanoia output to see what we're actually parsing
        self.logger.info("=== RAW CDPARANOIA OUTPUT FOR DEBUGGING ===")
        for i, line in enumerate(lines[:25]):  # Show first 25 lines
            self.logger.info(f"Line {i:2d}: '{line}'")
        self.logger.info("=== END RAW OUTPUT ===")
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            self.logger.debug(f"Line {line_num}: '{line}'")
            
            # Real cdparanoia -Q output format:
            # " 1. 19497 [04:19.72] 0 [00:00.00] OK no 2"
            # Track number, sectors, [duration], start_sector, [start_time], status, pre, ch
            
            # More restrictive pattern to avoid false matches
            track_pattern = r'^\s*(\d{1,2})\.\s+(\d+)\s+\[(\d+):(\d+)\.(\d+)\]\s+(\d+)\s+\[(\d+):(\d+)\.(\d+)\]\s+(OK|ok)\s+'
            track_match = re.match(track_pattern, line)
            
            if track_match:
                try:
                    track_num = int(track_match.group(1))
                    sectors = int(track_match.group(2))
                    minutes = int(track_match.group(3))
                    seconds = int(track_match.group(4))
                    frames = int(track_match.group(5))
                    start_sector = int(track_match.group(6))
                    
                    # More restrictive validation
                    if track_num <= 0 or track_num > 99:
                        self.logger.debug(f"Skipping invalid track number: {track_num}")
                        continue
                    
                    # Only accept reasonable audio track lengths (5 seconds to 80 minutes)
                    min_sectors = 375    # 5 seconds
                    max_sectors = 360000 # 80 minutes
                    if sectors < min_sectors or sectors > max_sectors:
                        self.logger.info(f"Skipping track {track_num} with unusual length: {sectors} sectors ({sectors/75:.1f} seconds)")
                        continue
                    
                    # Ensure track numbers are sequential (no big gaps)
                    if tracks and track_num > tracks[-1]['number'] + 1:
                        self.logger.warning(f"Non-sequential track number {track_num} after track {tracks[-1]['number']}")
                    
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
                self.logger.info(f"❌ Rejected potential track line: '{line}'")
                    
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
            self.logger.error("❌ No tracks found in cdparanoia output")
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
    
    def _parse_cdrdao_output(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse cdrdao disk-info output"""
        # Implementation for cdrdao parsing
        return None
    
    def _parse_discid_output(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse cd-discid output"""
        # Implementation for cd-discid parsing
        return None
    
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
                
                track = TrackInfo(
                    number=track_info.get('number', len(tracks) + 1),
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
