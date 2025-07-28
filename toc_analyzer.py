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
            basic_toc = self._get_toc_cdrdao()
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

    def _get_toc_cdrdao(self) -> Optional[Dict[str, Any]]:
        """Get TOC using cdrdao read-toc"""
        try:
            create_toc = subprocess.Popen(
                ['cdrdao', 'read-toc', '--fast-toc', '--device', self.device, '--datafile', 'toc.toc'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            create_toc.wait()

            with open('toc.toc', r) as fh:
                toc_data = fh.read()

            if create_toc.returncode != 0:
                self.logger.error(f"cdrdao read-toc failed with return code {create_toc.returncode}")
                if create_toc.stderr:
                    self.logger.error(f"cdrdao stderr: {create_toc.stderr}")
                return None

            self.logger.info("=== RAW CDRDAO OUTPUT ===")
            self.logger.info(print(toc_data))
            self.logger.info("=== END RAW OUTPUT ===")

            # Parse TOC for track information and gaps
            parsed_toc = self._parse_cdrdao_output(toc_data)

            # Extract CD-Text information
            cd_text_info = self._extract_cd_text(toc_data)
            if cd_text_info:
                parsed_toc['cd_text'] = cd_text_info

            return parsed_toc

        except subprocess.TimeoutExpired:
            self.logger.error("cdrdao read-toc timed out")
            return None
        except Exception as e:
            self.logger.error(f"cdrdao read-toc execution failed: {e}")
            return None

    def _parse_cdrdao_output(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse cdrdao TOC file output"""
        try:
            parsed_data = {
                'tracks': []
            }
            lines = output.splitlines()

            for line in lines:
                line = line.strip()

                # Parse catalog number
                if line.startswith('CATALOG'):
                    match = re.search(r'"(\d{13})"', line)
                    if match:
                        parsed_data['catalog_number'] = match.group(1)

                # Parse track information
                elif line.startswith('TRACK AUDIO'):
                    track = {
                        'number': len(parsed_data['tracks']) + 1,
                        'start_sector': 0,
                        'length_sectors': 0
                    }
                    parsed_data['tracks'].append(track)

                # Parse file information
                elif line.startswith('FILE'):
                    match = re.search(r'FILE "(.*?)" (\d+:\d+:\d+) (\d+:\d+:\d+)', line)
                    if match and parsed_data['tracks']:
                        file_name = match.group(1)
                        start_time = match.group(2)
                        length_time = match.group(3)

                        # Convert start time and length time to sectors
                        start_sector = self._time_to_sectors(start_time)
                        length_sectors = self._time_to_sectors(length_time)

                        # Update the last track with file information
                        track = parsed_data['tracks'][-1]
                        track['file'] = file_name
                        track['start_sector'] = start_sector
                        track['length_sectors'] = length_sectors

            return parsed_data

        except Exception as e:
            self.logger.error(f"Failed to parse cdrdao output: {e}")
            return None

    def _time_to_sectors(self, time: str) -> int:
        """Convert MM:SS:FF time format to sectors"""
        try:
            minutes, seconds, frames = map(int, time.split(':'))
            return (minutes * 60 + seconds) * 75 + frames
        except ValueError:
            self.logger.warning(f"Invalid time format: {time}")
            return 0

    
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
        """Read CD-Text information using cdrdao read-toc"""
        try:
            result = subprocess.run([
                'cdrdao', 'read-toc', '--device', self.device
            ], capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                # Parse CD-Text from output
                cd_text_info = {}
                lines = result.stdout.split('\n')

                for line in lines:
                    line = line.strip()
                    if 'CD_TEXT' in line:
                        try:
                            if 'TITLE' in line.upper():
                                title_parts = line.split('TITLE', 1)
                                if len(title_parts) > 1:
                                    title = title_parts[1].strip().strip('"\'')
                                    if title:
                                        cd_text_info['title'] = title
                            elif 'PERFORMER' in line.upper():
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
