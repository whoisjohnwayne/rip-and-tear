#!/usr/bin/env python3
"""
Configuration Manager for Rip and Tear
Handles loading and saving configuration settings
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any

class ConfigManager:
    """Manages application configuration"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.config_dir = Path(os.getenv('CONFIG_DIR', '/config'))
        self.config_file = self.config_dir / 'config.yaml'
        self.default_config_file = Path(__file__).parent / 'config' / 'default_config.yaml'
        
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file and environment variables"""
        try:
            # Load base configuration from file
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = yaml.safe_load(f)
                self.logger.info(f"Loaded configuration from {self.config_file}")
            else:
                config = self._load_default_config()
                self.save_config(config)
                self.logger.info("Created new configuration from defaults")
            
            # Override with environment variables
            config = self._apply_environment_overrides(config)
            
            return self._validate_config(config)
            
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            config = self._load_default_config()
            return self._apply_environment_overrides(config)
    
    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file"""
        try:
            self.config_dir.mkdir(exist_ok=True)
            with open(self.config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, indent=2)
            self.logger.info(f"Saved configuration to {self.config_file}")
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
    
    def _load_default_config(self) -> Dict[str, Any]:
        """Load default configuration"""
        return {
            'cd_drive': {
                'device': '/dev/cdrom',
                'offset': 0,  # Drive offset correction in samples
                'speed': 'max',  # Ripping speed
            },
            'output': {
                'directory': os.getenv('OUTPUT_DIR', '/output'),
                'format': 'flac',
                'compression_level': 5,  # Better speed/size balance than level 8
                'create_cue': True,
                'create_log': True,
            },
            'ripping': {
                'try_burst_first': True,
                'use_accuraterip': True,
                'accuraterip_prefer_v2': True,
                'accuraterip_require_both': False,
                'paranoia_mode': 'full',  # full, overlap, neverskip
                'max_retries': 10,
                'last_track_retries': 1,  # Very aggressive - just try once and move on
                'last_track_paranoia': 'minimal',  # Bypass lead-out verification by default
                'leadout_detection': 'disabled',  # Completely bypass lead-out logic by default
            },
            'metadata': {
                'use_musicbrainz': True,
                'musicbrainz_server': 'musicbrainz.org',
                'user_agent': 'CDRipper/1.0',
                'contact_email': 'user@example.com',
            },
            'web_gui': {
                'host': '0.0.0.0',
                'port': 8080,
                'debug': False,
            },
            'logging': {
                'level': 'INFO',
                'max_log_files': 10,
                'max_log_size_mb': 50,
            }
        }
    
    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and fill missing configuration values"""
        default_config = self._load_default_config()
        
        def merge_configs(default: Dict, user: Dict) -> Dict:
            """Recursively merge user config with defaults"""
            result = default.copy()
            for key, value in user.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = merge_configs(result[key], value)
                else:
                    result[key] = value
            return result
        
        return merge_configs(default_config, config)
    
    def _apply_environment_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration"""
        env_mappings = {
            # CD Drive settings
            'CD_DEVICE': ('cd_drive', 'device'),
            'DRIVE_OFFSET': ('cd_drive', 'offset', int),
            'DRIVE_SPEED': ('cd_drive', 'speed'),
            'ENABLE_C2': ('cd_drive', 'enable_c2', self._str_to_bool),
            'TEST_AND_COPY': ('cd_drive', 'test_and_copy', self._str_to_bool),
            
            # Output settings
            'OUTPUT_FORMAT': ('output', 'format'),
            'COMPRESSION_LEVEL': ('output', 'compression_level', int),
            'CREATE_CUE': ('output', 'create_cue', self._str_to_bool),
            'CREATE_LOG': ('output', 'create_log', self._str_to_bool),
            'PRESERVE_HTOA': ('output', 'preserve_htoa', self._str_to_bool),
            'GAP_HANDLING': ('output', 'gap_handling'),
            
            # Ripping settings
            'TRY_BURST_FIRST': ('ripping', 'try_burst_first', self._str_to_bool),
            'USE_ACCURATERIP': ('ripping', 'use_accuraterip', self._str_to_bool),
            'ACCURATERIP_PREFER_V2': ('ripping', 'accuraterip_prefer_v2', self._str_to_bool),
            'ACCURATERIP_REQUIRE_BOTH': ('ripping', 'accuraterip_require_both', self._str_to_bool),
            'PARANOIA_MODE': ('ripping', 'paranoia_mode'),
            'MAX_RETRIES': ('ripping', 'max_retries', int),
            'LAST_TRACK_RETRIES': ('ripping', 'last_track_retries', int),
            'LAST_TRACK_PARANOIA': ('ripping', 'last_track_paranoia'),
            'LEADOUT_DETECTION': ('ripping', 'leadout_detection'),
            'SECTOR_RETRIES': ('ripping', 'sector_retries', int),
            'ENABLE_GAP_DETECTION': ('ripping', 'enable_gap_detection', self._str_to_bool),
            'READ_LEAD_IN': ('ripping', 'read_lead_in', self._str_to_bool),
            'MULTIPLE_READ_VERIFICATION': ('ripping', 'multiple_read_verification', self._str_to_bool),
            'VERIFY_RERIP': ('ripping', 'verify_rerip', self._str_to_bool),
            'SELECTIVE_RERIP': ('ripping', 'selective_rerip', self._str_to_bool),
            
            # Metadata settings
            'USE_MUSICBRAINZ': ('metadata', 'use_musicbrainz', self._str_to_bool),
            'MUSICBRAINZ_SERVER': ('metadata', 'musicbrainz_server'),
            'USER_AGENT': ('metadata', 'user_agent'),
            'CONTACT_EMAIL': ('metadata', 'contact_email'),
            
            # Web GUI settings
            'WEB_HOST': ('web_gui', 'host'),
            'WEB_PORT': ('web_gui', 'port', int),
            'WEB_DEBUG': ('web_gui', 'debug', self._str_to_bool),
            
            # Logging settings
            'LOG_LEVEL': ('logging', 'level'),
            'MAX_LOG_FILES': ('logging', 'max_log_files', int),
            'MAX_LOG_SIZE_MB': ('logging', 'max_log_size_mb', int),
        }
        
        for env_var, mapping in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                try:
                    section = mapping[0]
                    key = mapping[1]
                    converter = mapping[2] if len(mapping) > 2 else str
                    
                    # Ensure section exists
                    if section not in config:
                        config[section] = {}
                    
                    # Convert and set value
                    if converter == int:
                        try:
                            config[section][key] = int(env_value)
                        except ValueError:
                            self.logger.warning(f"Invalid integer value for {env_var}: {env_value}")
                            continue
                    elif callable(converter):
                        config[section][key] = converter(env_value)
                    else:
                        config[section][key] = env_value
                    
                    self.logger.debug(f"Applied environment override: {env_var}={env_value}")
                    
                except Exception as e:
                    self.logger.warning(f"Failed to apply environment override {env_var}: {e}")
        
        return config
    
    def _str_to_bool(self, value: str) -> bool:
        """Convert string to boolean"""
        return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
    
    def get_cd_device(self, config: Dict[str, Any]) -> str:
        """Get CD device path, with auto-detection fallback"""
        device = config['cd_drive']['device']
        
        # Try to auto-detect if default device doesn't exist
        if not os.path.exists(device):
            potential_devices = ['/dev/cdrom', '/dev/sr0', '/dev/sr1', '/dev/cdrom0']
            for dev in potential_devices:
                if os.path.exists(dev):
                    self.logger.info(f"Auto-detected CD device: {dev}")
                    return dev
            
            self.logger.warning(f"CD device {device} not found, using anyway")
        
        return device
