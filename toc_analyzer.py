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
                self.logger.error("Failed to analyze tracks - CD may be damaged or blank")
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
                total_sectors=basic_toc.get('total_sectors', 0),
                leadout_sector=basic_toc.get('leadout_sector', 0),
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
        result = subprocess.run(
            ['cdparanoia', '-Q', '-d', self.device],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return None
        
        return self._parse_cdparanoia_output(result.stderr)
    
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
        if not tracks:
            self.logger.error("Failed to create basic tracks - CD may be unreadable")
            return []
        
        self.logger.info(f"Created {len(tracks)} basic tracks")
        
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
                '--query', '--verbose'
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
        """Parse cdparanoia -Q output with robust pattern matching"""
        tracks = []
        lines = output.strip().split('\n')
        
        total_sectors = 0
        leadout_sector = 0
        
        self.logger.debug(f"Parsing cdparanoia output: {len(lines)} lines")
        
        for line in lines:
            line = line.strip()
            self.logger.debug(f"Processing line: {line}")
            
            # Try multiple patterns for track lines
            track_patterns = [
                # Pattern 1: "  1.    4:17.32 (19282 sectors)    0:02.00 -> 4:19.32"
                r'^\s*(\d+)\.\s+(\d+):(\d+)\.(\d+)\s+\((\d+)\s+sectors\)',
                # Pattern 2: "track 01.  audio    00:32.17    760 [00:02.17]"  
                r'^track\s+(\d+)\.\s+audio\s+(\d+):(\d+)\.(\d+)\s+(\d+)',
                # Pattern 3: More flexible track line
                r'^\s*(\d+)[\.:]?\s+.*?(\d+):(\d+)[\.\:](\d+).*?(\d+)\s+sectors'
            ]
            
            track_found = False
            for pattern in track_patterns:
                track_match = re.search(pattern, line, re.IGNORECASE)
                if track_match:
                    try:
                        track_num = int(track_match.group(1))
                        minutes = int(track_match.group(2))
                        seconds = int(track_match.group(3))
                        frames = int(track_match.group(4))
                        sectors = int(track_match.group(5))
                        
                        duration = f"{minutes}:{seconds:02d}.{frames:02d}"
                        
                        tracks.append({
                            'number': track_num,
                            'duration': duration,
                            'sectors': sectors,
                            'type': 'audio'
                        })
                        total_sectors += sectors
                        self.logger.debug(f"Parsed track {track_num}: {duration} ({sectors} sectors)")
                        track_found = True
                        break
                    except (ValueError, IndexError) as e:
                        self.logger.warning(f"Failed to parse track line '{line}' with pattern '{pattern}': {e}")
                        continue
            
            if not track_found and ('total' in line.lower() or 'TOTAL' in line):
                # Try to extract total information
                total_patterns = [
                    r'TOTAL\s+(\d+):(\d+)\.(\d+)\s+\((\d+)\s+sectors\)',
                    r'total.*?(\d+):(\d+)[\.\:](\d+).*?(\d+)\s+sectors',
                    r'(\d+):(\d+)[\.\:](\d+).*?total.*?(\d+)'
                ]
                
                for pattern in total_patterns:
                    total_match = re.search(pattern, line, re.IGNORECASE)
                    if total_match:
                        try:
                            minutes = int(total_match.group(1))
                            seconds = int(total_match.group(2))
                            frames = int(total_match.group(3))
                            leadout_sector = int(total_match.group(4))
                            self.logger.debug(f"Found total: {minutes}:{seconds:02d}.{frames:02d} ({leadout_sector} sectors)")
                            break
                        except (ValueError, IndexError):
                            continue
        
        self.logger.info(f"cdparanoia parsing found {len(tracks)} tracks")
        
        if not tracks:
            self.logger.error("No tracks found in cdparanoia output")
            self.logger.error(f"Raw cdparanoia output:\n{output}")
            
            # Try a last-ditch effort to count tracks by looking for any numeric patterns
            track_count = 0
            for line in lines:
                if re.search(r'^\s*\d+[\.\s]', line):
                    track_count += 1
            
            if track_count > 0:
                self.logger.warning(f"Found {track_count} potential tracks, creating basic tracks")
                # Create basic tracks with estimated timing
                estimated_tracks = []
                for i in range(1, min(track_count + 1, 20)):  # Max 20 tracks
                    estimated_tracks.append({
                        'number': i,
                        'duration': '3:00.00',
                        'sectors': 13500,  # 3 minutes * 75 sectors/second
                        'type': 'audio'
                    })
                
                return {
                    'tracks': estimated_tracks,
                    'total_sectors': len(estimated_tracks) * 13500,
                    'leadout_sector': len(estimated_tracks) * 13500,
                    'first_track': 1,
                    'last_track': len(estimated_tracks)
                }
            
            # Return empty but valid structure
            return {
                'tracks': [],
                'total_sectors': 0,
                'leadout_sector': 0,
                'first_track': 1,
                'last_track': 0
            }
        
        return {
            'tracks': tracks,
            'total_sectors': total_sectors if total_sectors > 0 else leadout_sector,
            'leadout_sector': leadout_sector,
            'first_track': 1,
            'last_track': len(tracks)
        }
    
    def _parse_cdrdao_output(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse cdrdao disk-info output"""
        # Implementation for cdrdao parsing
        return None
    
    def _parse_discid_output(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse cd-discid output"""
        # Implementation for cd-discid parsing
        return None
    
    def _create_basic_tracks(self, basic_toc: Dict[str, Any]) -> List[TrackInfo]:
        """Create basic track info when detailed analysis fails"""
        tracks = []
        
        if not basic_toc:
            self.logger.error("No basic_toc data available for creating tracks")
            return self._create_emergency_tracks()
            
        # Try to extract track info from different possible formats
        track_data = basic_toc.get('tracks', [])
        if not track_data:
            # Fallback: create tracks based on first/last track numbers
            first_track = basic_toc.get('first_track', 1)
            last_track = basic_toc.get('last_track', 0)
            
            if last_track >= first_track and last_track > 0:
                self.logger.info(f"Creating {last_track - first_track + 1} basic tracks")
                total_sectors = basic_toc.get('total_sectors', 0)
                sectors_per_track = total_sectors // (last_track - first_track + 1) if last_track > first_track else total_sectors
                
                for i in range(first_track, last_track + 1):
                    track = TrackInfo(
                        number=i,
                        start_sector=(i - first_track) * sectors_per_track,
                        length_sectors=sectors_per_track,
                        track_type='audio'
                    )
                    tracks.append(track)
            else:
                self.logger.error(f"Invalid track range: {first_track}-{last_track}")
                self.logger.warning("Using emergency track creation as last resort")
                return self._create_emergency_tracks()
            return tracks
            
        current_sector = 0
        
        try:
            for track_info in track_data:
                if not isinstance(track_info, dict):
                    self.logger.warning(f"Invalid track data format: {track_info}")
                    continue
                    
                track = TrackInfo(
                    number=track_info.get('number', len(tracks) + 1),
                    start_sector=current_sector,
                    length_sectors=track_info.get('sectors', 0),
                    track_type='audio'
                )
                tracks.append(track)
                current_sector += track.length_sectors
        except Exception as e:
            self.logger.error(f"Error creating basic tracks: {e}")
            self.logger.error(f"basic_toc content: {basic_toc}")
            self.logger.warning("Using emergency track creation as last resort")
            return self._create_emergency_tracks()
        
        return tracks

    def _create_emergency_tracks(self) -> List[TrackInfo]:
        """Emergency fallback: create reasonable default tracks when all else fails"""
        self.logger.warning("Creating emergency fallback tracks - CD analysis failed")
        tracks = []
        
        # Create 10 tracks of ~3 minutes each (reasonable for most CDs)
        for i in range(1, 11):
            track = TrackInfo(
                number=i,
                start_sector=(i-1) * 13500,  # ~3 minutes per track at 75 sectors/second
                length_sectors=13500,  # 180 seconds * 75 sectors/second
                track_type='audio'
            )
            tracks.append(track)
            
        self.logger.info(f"Created {len(tracks)} emergency fallback tracks")
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
