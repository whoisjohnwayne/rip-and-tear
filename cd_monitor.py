#!/usr/bin/env python3
"""
CD Monitor - Detects CD insertion and triggers ripping
"""

import os
import time
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

class CDMonitor:
    """Monitors for CD insertion and triggers ripping"""
    
    def __init__(self, cd_ripper, config: Dict[str, Any]):
        self.cd_ripper = cd_ripper
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.last_disc_id = None
        
    def start_monitoring(self):
        """Start monitoring for CD insertion"""
        self.running = True
        self.logger.info("Starting CD monitoring...")
        
        while self.running:
            try:
                if self._check_cd_inserted():
                    disc_id = self._get_disc_id()
                    if disc_id and disc_id != self.last_disc_id:
                        self.logger.info(f"New CD detected: {disc_id}")
                        self.last_disc_id = disc_id
                        
                        # Start ripping in a separate thread
                        rip_thread = threading.Thread(
                            target=self._handle_cd_insertion,
                            args=(disc_id,),
                            daemon=True
                        )
                        rip_thread.start()
                
                else:
                    # No CD detected, reset last disc ID
                    if self.last_disc_id:
                        self.logger.info("CD ejected")
                        self.last_disc_id = None
                
                time.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                self.logger.error(f"Error in CD monitoring: {e}")
                time.sleep(5)  # Wait longer on error
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False
        self.logger.info("Stopped CD monitoring")
    
    def _check_cd_inserted(self) -> bool:
        """Check if a CD is inserted"""
        device = self.config['cd_drive']['device']
        
        try:
            # Try to read the CD table of contents
            result = subprocess.run(
                ['cd-paranoia', '-Q', f'--device={device}'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # If cd-paranoia can read the TOC, a CD is present
            return result.returncode == 0 and 'track' in result.stderr.lower()
            
        except subprocess.TimeoutExpired:
            self.logger.warning("CD check timed out")
            return False
        except FileNotFoundError:
            self.logger.error("cd-paranoia not found")
            return False
        except Exception as e:
            self.logger.error(f"Error checking CD: {e}")
            return False
    
    def _get_disc_id(self) -> Optional[str]:
        """Get a unique identifier for the disc"""
        device = self.config['cd_drive']['device']
        
        try:
            # Use cd-discid to get a unique disc identifier
            result = subprocess.run(
                ['cd-discid', device],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                # First part of the output is the disc ID
                return result.stdout.strip().split()[0]
            
            # Fallback: use cd-paranoia to get track count as a simple ID
            result = subprocess.run(
                ['cd-paranoia', '-Q', f'--device={device}'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                # Count tracks from output
                tracks = [line for line in result.stderr.split('\n') 
                         if 'track' in line.lower() and '.' in line]
                return f"tracks_{len(tracks)}"
            
        except subprocess.TimeoutExpired:
            self.logger.warning("Disc ID check timed out")
        except FileNotFoundError:
            self.logger.warning("cd-discid not found, using fallback")
        except Exception as e:
            self.logger.error(f"Error getting disc ID: {e}")
        
        return None
    
    def _handle_cd_insertion(self, disc_id: str):
        """Handle CD insertion by starting the ripping process"""
        try:
            self.logger.info(f"Starting rip process for disc: {disc_id}")
            self.cd_ripper.rip_cd()
            
        except Exception as e:
            self.logger.error(f"Error handling CD insertion: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get monitoring status"""
        return {
            'monitoring': self.running,
            'cd_inserted': self._check_cd_inserted(),
            'last_disc_id': self.last_disc_id
        }
