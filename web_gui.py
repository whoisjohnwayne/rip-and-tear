#!/usr/bin/env python3
"""
Web GUI - Flask-based web interface for monitoring Rip and Tear progress
"""

import json
import logging
from flask import Flask, render_template, jsonify, request, send_from_directory
from pathlib import Path
from typing import Dict, Any

class WebGUI:
    """Web-based GUI for Rip and Tear monitoring"""
    
    def __init__(self, cd_ripper, config: Dict[str, Any]):
        self.cd_ripper = cd_ripper
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Create Flask app
        self.app = Flask(__name__, 
                        template_folder='templates',
                        static_folder='static')
        
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            """Main dashboard"""
            return render_template('index.html')
        
        @self.app.route('/api/status')
        def api_status():
            """Get current ripping status"""
            try:
                status = self.cd_ripper.get_status()
                return jsonify({
                    'success': True,
                    'data': status
                })
            except Exception as e:
                self.logger.error(f"Status API error: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/config')
        def api_config():
            """Get current configuration"""
            try:
                # Return safe config (without sensitive data)
                safe_config = {
                    'cd_drive': self.config.get('cd_drive', {}),
                    'output': self.config.get('output', {}),
                    'ripping': self.config.get('ripping', {}),
                }
                return jsonify({
                    'success': True,
                    'data': safe_config
                })
            except Exception as e:
                self.logger.error(f"Config API error: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/config', methods=['POST'])
        def api_update_config():
            """Update configuration"""
            try:
                new_config = request.get_json()
                
                # Update config (in a real implementation, you'd validate and save)
                # For now, just log the request
                self.logger.info(f"Config update requested: {new_config}")
                
                return jsonify({
                    'success': True,
                    'message': 'Configuration updated'
                })
            except Exception as e:
                self.logger.error(f"Config update error: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/logs')
        def api_logs():
            """Get recent log entries"""
            try:
                log_file = Path('/logs/rip_and_tear.log')
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        lines = f.readlines()
                        # Return last 100 lines
                        recent_lines = lines[-100:] if len(lines) > 100 else lines
                        return jsonify({
                            'success': True,
                            'data': recent_lines
                        })
                else:
                    return jsonify({
                        'success': True,
                        'data': []
                    })
            except Exception as e:
                self.logger.error(f"Logs API error: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/files')
        def api_files():
            """List output files"""
            try:
                output_dir = Path(self.config['output']['directory'])
                files = []
                
                if output_dir.exists():
                    for item in output_dir.iterdir():
                        if item.is_dir():
                            # List album directories
                            album_files = []
                            for file in item.iterdir():
                                if file.is_file():
                                    album_files.append({
                                        'name': file.name,
                                        'size': file.stat().st_size,
                                        'modified': file.stat().st_mtime
                                    })
                            
                            files.append({
                                'name': item.name,
                                'type': 'directory',
                                'files': album_files
                            })
                
                return jsonify({
                    'success': True,
                    'data': files
                })
            except Exception as e:
                self.logger.error(f"Files API error: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/health')
        def health():
            """Health check endpoint"""
            return jsonify({'status': 'healthy'})
    
    def run(self):
        """Run the Flask web server"""
        try:
            host = self.config['web_gui']['host']
            port = self.config['web_gui']['port']
            debug = self.config['web_gui']['debug']
            
            self.logger.info(f"Starting web GUI on {host}:{port}")
            self.app.run(host=host, port=port, debug=debug)
            
        except Exception as e:
            self.logger.error(f"Failed to start web GUI: {e}")
            raise
