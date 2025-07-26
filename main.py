#!/usr/bin/env python3
"""
Rip and Tear Main Application
Automatically detects CD insertion and rips to FLAC with metadata

Copyright (c) 2025 Rip and Tear Contributors
Licensed under the MIT License - see LICENSE file for details
"""

import os
import sys
import time
import threading
import logging
from pathlib import Path

from cd_ripper import CDRipper
from web_gui import WebGUI
from config_manager import ConfigManager
from cd_monitor import CDMonitor

def setup_logging():
    """Setup logging configuration"""
    log_dir = Path(os.getenv('LOG_DIR', '/logs'))
    log_dir.mkdir(exist_ok=True)
    
    # Custom filter to exclude health check logs
    class HealthCheckFilter(logging.Filter):
        def filter(self, record):
            # Filter out health check requests
            if hasattr(record, 'getMessage'):
                message = record.getMessage()
                return '/health' not in message
            return True
    
    # Configure main logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / 'rip_and_tear.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Apply filter to werkzeug (Flask's HTTP logger) to suppress health check logs
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.addFilter(HealthCheckFilter())
    werkzeug_logger.setLevel(logging.WARNING)  # Reduce werkzeug verbosity overall

def main():
    """Main application entry point"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Rip and Tear application")
    
    try:
        # Load configuration
        config_manager = ConfigManager()
        config = config_manager.load_config()
        
        # Initialize CD ripper
        cd_ripper = CDRipper(config)
        
        # Start web GUI in background thread
        web_gui = WebGUI(cd_ripper, config)
        gui_thread = threading.Thread(target=web_gui.run, daemon=True)
        gui_thread.start()
        logger.info("Web GUI started on port 8080")
        
        # Start CD monitoring
        cd_monitor = CDMonitor(cd_ripper, config)
        monitor_thread = threading.Thread(target=cd_monitor.start_monitoring, daemon=True)
        monitor_thread.start()
        logger.info("CD monitoring started")
        
        # Keep main thread alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down Rip and Tear application")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
