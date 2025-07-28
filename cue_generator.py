#!/usr/bin/env python3
"""
CUE Generator - Creates CUE sheets for ripped CDs
"""

import logging
from pathlib import Path
import subprocess

class CueGenerator:
    """Generates CUE sheets for CD rips"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def create_cue_sheet(self, output_dir: Path) -> Path:
        """Create a CUE sheet for the ripped CD using toc2cue"""
        try:
            # Generate cue file
            cue_file = output_dir / f"{self._sanitize_filename(metadata.get('album', 'Unknown Album'))}.cue"
            toc_file = output_dir / f"{self._sanitize_filename(metadata.get('album', 'Unknown Album'))}.toc"

            # Convert TOC to CUE using toc2cue
            result = subprocess.run(
                ['toc2cue', str(toc_file), str(cue_file)],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                self.logger.error(f"toc2cue failed with return code {result.returncode}")
                if result.stderr:
                    self.logger.error(f"toc2cue stderr: {result.stderr}")
                raise RuntimeError("Failed to convert TOC to CUE")

            self.logger.info(f"Created CUE sheet: {cue_file}")
            return cue_file

        except Exception as e:
            self.logger.error(f"Failed to create CUE sheet: {e}")
            raise
    
    
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
