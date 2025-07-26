#!/usr/bin/env python3
"""
CUE Generator - Creates CUE sheets for ripped CDs
"""

import logging
from pathlib import Path
from typing import Dict, Any, List

class CueGenerator:
    """Generates CUE sheets for CD rips"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def create_cue_sheet(self, disc_info, metadata: Dict[str, Any], output_dir: Path) -> Path:
        """Create a CUE sheet for the ripped CD with precise gap information"""
        try:
            cue_file = output_dir / f"{self._sanitize_filename(metadata.get('album', 'Unknown Album'))}.cue"
            
            cue_content = self._generate_cue_content(disc_info, metadata, output_dir)
            
            with open(cue_file, 'w', encoding='utf-8') as f:
                f.write(cue_content)
            
            self.logger.info(f"Created CUE sheet: {cue_file}")
            return cue_file
            
        except Exception as e:
            self.logger.error(f"Failed to create CUE sheet: {e}")
            raise
    
    def _generate_cue_content(self, disc_info, metadata: Dict[str, Any], output_dir: Path) -> str:
        """Generate CUE sheet content with precise gap information"""
        lines = []
        
        # Header information
        lines.append(f'REM GENRE "Unknown"')
        lines.append(f'REM DATE "{metadata.get("date", "")}"')
        lines.append(f'REM DISCID "{disc_info.disc_id}"')
        lines.append(f'REM COMMENT "Ripped with Rip and Tear"')
        
        if disc_info.catalog_number:
            lines.append(f'CATALOG {disc_info.catalog_number}')
        
        lines.append(f'PERFORMER "{metadata.get("artist", "Unknown Artist")}"')
        lines.append(f'TITLE "{metadata.get("album", "Unknown Album")}"')
        
        # Handle HTOA if present
        if disc_info.tracks and disc_info.tracks[0].has_htoa:
            lines.append(f'FILE "00.flac" WAVE')
            lines.append(f'  TRACK 00 AUDIO')
            lines.append(f'    TITLE "Hidden Track"')
            lines.append(f'    PERFORMER "{metadata.get("artist", "Unknown Artist")}"')
            lines.append(f'    INDEX 01 00:00:00')
        
        # Process regular tracks with gap information
        track_metadata = metadata.get('tracks', [])
        
        for i, track in enumerate(disc_info.tracks, 1):
            # Get track metadata
            track_meta = {}
            if i <= len(track_metadata):
                track_meta = track_metadata[i-1]
            
            track_title = track_meta.get('title', f'Track {i:02d}')
            track_artist = track_meta.get('artist', metadata.get('artist', 'Unknown Artist'))
            
            # Find the corresponding FLAC file
            flac_files = list(output_dir.glob(f"{i:02d} - *.flac"))
            if flac_files:
                flac_file = flac_files[0].name
            else:
                flac_file = f"{i:02d} - {self._sanitize_filename(track_title)}.flac"
            
            lines.append(f'FILE "{flac_file}" WAVE')
            lines.append(f'  TRACK {i:02d} AUDIO')
            lines.append(f'    TITLE "{track_title}"')
            lines.append(f'    PERFORMER "{track_artist}"')
            
            # Add ISRC if available
            if track.isrc:
                lines.append(f'    ISRC {track.isrc}')
            
            # Handle pre-gaps
            if track.pregap_sectors > 0:
                pregap_time = self._sectors_to_time(track.pregap_sectors)
                lines.append(f'    PREGAP {pregap_time}')
            
            # Main track index
            lines.append(f'    INDEX 01 00:00:00')
            
            # Handle post-gaps if any
            if track.postgap_sectors > 0:
                postgap_time = self._sectors_to_time(track.postgap_sectors)
                lines.append(f'    POSTGAP {postgap_time}')
        
        return '\n'.join(lines)
    
    def _sectors_to_time(self, sectors: int) -> str:
        """Convert sectors to MM:SS:FF format"""
        total_frames = sectors
        minutes = total_frames // (75 * 60)
        seconds = (total_frames % (75 * 60)) // 75
        frames = total_frames % 75
        return f"{minutes:02d}:{seconds:02d}:{frames:02d}"
    
    def _add_time(self, time1: str, duration: str) -> str:
        """Add duration to time (simplified implementation)"""
        try:
            # Parse time1 (MM:SS:FF format)
            t1_parts = time1.split(':')
            minutes1 = int(t1_parts[0])
            seconds1 = int(t1_parts[1])
            frames1 = int(t1_parts[2]) if len(t1_parts) > 2 else 0
            
            # Parse duration (MM:SS.FF format)
            if '.' in duration:
                duration_parts = duration.split(':')
                minutes2 = int(duration_parts[0])
                sec_frame = duration_parts[1].split('.')
                seconds2 = int(sec_frame[0])
                frames2 = int(sec_frame[1]) if len(sec_frame) > 1 else 0
            else:
                # Simple MM:SS format
                duration_parts = duration.split(':')
                minutes2 = int(duration_parts[0])
                seconds2 = int(duration_parts[1])
                frames2 = 0
            
            # Add times (75 frames per second for CD audio)
            total_frames = frames1 + frames2
            total_seconds = seconds1 + seconds2 + (total_frames // 75)
            total_minutes = minutes1 + minutes2 + (total_seconds // 60)
            
            result_frames = total_frames % 75
            result_seconds = total_seconds % 60
            
            return f"{total_minutes:02d}:{result_seconds:02d}:{result_frames:02d}"
            
        except Exception as e:
            self.logger.warning(f"Time calculation failed: {e}")
            return "00:00:00"
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem compatibility"""
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
        
        return ' '.join(filename.split()).strip()
