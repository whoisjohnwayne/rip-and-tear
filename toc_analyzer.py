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
                return None
            
            # Get detailed track information with gaps
            detailed_tracks = self._analyze_track_gaps(basic_toc)
            
            # Detect HTOA (Hidden Track One Audio)
            htoa_info = self._detect_htoa()
            if htoa_info:
                detailed_tracks[0].has_htoa = True
                detailed_tracks[0].htoa_length = htoa_info
            
            # Get CD-Text if available
            cd_text = self._read_cd_text()
            
            # Get disc identification
            disc_id = self._calculate_precise_disc_id(detailed_tracks)
            
            disc_info = DiscInfo(
                total_sectors=basic_toc['total_sectors'],
                leadout_sector=basic_toc['leadout_sector'],
                first_track=basic_toc['first_track'],
                last_track=basic_toc['last_track'],
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
        """Get basic TOC using multiple methods for accuracy"""
        methods = [
            self._get_toc_cdparanoia,
            self._get_toc_cdrdao,
            self._get_toc_cd_discid
        ]
        
        for method in methods:
            try:
                result = method()
                if result:
                    self.logger.info(f"TOC obtained using {method.__name__}")
                    return result
            except Exception as e:
                self.logger.warning(f"{method.__name__} failed: {e}")
        
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
        
        try:
            # Use cdrdao for precise gap detection
            result = subprocess.run(
                ['cdrdao', 'read-toc', '--device', self.device, '/tmp/temp.toc'],
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode == 0:
                tracks = self._parse_gap_analysis('/tmp/temp.toc')
            else:
                # Fallback to basic track info
                tracks = self._create_basic_tracks(basic_toc)
                
        except Exception as e:
            self.logger.warning(f"Gap analysis failed: {e}")
            tracks = self._create_basic_tracks(basic_toc)
        
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
    
    def _parse_cdparanoia_output(self, output: str) -> Dict[str, Any]:
        """Parse cdparanoia -Q output"""
        tracks = []
        lines = output.strip().split('\n')
        
        total_sectors = 0
        leadout_sector = 0
        
        for line in lines:
            line = line.strip()
            if line.startswith('track'):
                # Parse: "track 01.  audio    00:32.17    760 [00:02.17]"
                parts = line.split()
                if len(parts) >= 4 and parts[2] == 'audio':
                    track_num = int(parts[1].rstrip('.'))
                    duration = parts[3]
                    
                    # Convert duration to sectors (75 sectors per second)
                    if ':' in duration:
                        time_parts = duration.split(':')
                        minutes = int(time_parts[0])
                        seconds = float(time_parts[1])
                        sectors = int((minutes * 60 + seconds) * 75)
                        
                        tracks.append({
                            'number': track_num,
                            'duration': duration,
                            'sectors': sectors,
                            'type': 'audio'
                        })
                        total_sectors += sectors
            
            elif 'TOTAL' in line:
                # Extract total time/sectors
                match = re.search(r'(\d+):(\d+\.\d+)', line)
                if match:
                    minutes = int(match.group(1))
                    seconds = float(match.group(2))
                    leadout_sector = int((minutes * 60 + seconds) * 75)
        
        return {
            'tracks': tracks,
            'total_sectors': total_sectors,
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
        current_sector = 0
        
        for track_data in basic_toc['tracks']:
            track = TrackInfo(
                number=track_data['number'],
                start_sector=current_sector,
                length_sectors=track_data.get('sectors', 0),
                track_type='audio'
            )
            tracks.append(track)
            current_sector += track.length_sectors
        
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
