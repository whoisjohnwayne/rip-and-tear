#!/usr/bin/env python3
"""
Metadata Fetcher - Fetches CD metadata from MusicBrainz
"""

import logging
from typing import Dict, Any, List, Optional

try:
    import musicbrainzngs as mb
    MUSICBRAINZ_AVAILABLE = True
except ImportError:
    mb = None
    MUSICBRAINZ_AVAILABLE = False

class MetadataFetcher:
    """Fetches metadata from MusicBrainz"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        if not MUSICBRAINZ_AVAILABLE:
            self.logger.warning("MusicBrainz package not available - metadata fetching disabled")
            return
        
        # Configure MusicBrainz
        mb.set_useragent(
            config['metadata']['user_agent'],
            "1.0",
            config['metadata']['contact_email']
        )
        
        if config['metadata']['musicbrainz_server'] != 'musicbrainz.org':
            mb.set_hostname(config['metadata']['musicbrainz_server'])
    
    def get_metadata(self, toc_info: Dict[str, Any]) -> Dict[str, Any]:
        """Get metadata for the CD"""
        if not self.config['metadata']['use_musicbrainz']:
            return self._get_default_metadata(toc_info)
        
        try:
            # Try to find release using TOC
            disc_id = self._calculate_disc_id(toc_info)
            if disc_id:
                release_info = self._search_by_disc_id(disc_id)
                if release_info:
                    return release_info
            
            # Fallback: try fuzzy search if we have enough tracks
            if len(toc_info['tracks']) >= 3:
                return self._fuzzy_search(toc_info)
            
            self.logger.warning("Could not find metadata, using defaults")
            return self._get_default_metadata(toc_info)
            
        except Exception as e:
            self.logger.error(f"Metadata fetching failed: {e}")
            return self._get_default_metadata(toc_info)
    
    def _calculate_disc_id(self, toc_info: Dict[str, Any]) -> Optional[str]:
        """Calculate MusicBrainz disc ID"""
        # This is a simplified disc ID calculation
        # In practice, you'd want to use libdiscid or similar
        try:
            tracks = toc_info['tracks']
            if not tracks:
                return None
            
            # Simple hash based on track count and total time
            track_count = len(tracks)
            total_time = toc_info.get('total_time', '00:00')
            
            # This is a placeholder - real implementation would use proper disc ID
            simple_id = f"{track_count}_{total_time.replace(':', '')}"
            return simple_id
            
        except Exception as e:
            self.logger.error(f"Failed to calculate disc ID: {e}")
            return None
    
    def _search_by_disc_id(self, disc_id: str) -> Optional[Dict[str, Any]]:
        """Search MusicBrainz by disc ID"""
        try:
            # Note: This is a simplified search
            # Real implementation would use proper MusicBrainz disc ID lookup
            self.logger.info(f"Searching MusicBrainz for disc ID: {disc_id}")
            
            # For now, return None to trigger fuzzy search
            return None
            
        except Exception as e:
            self.logger.error(f"Disc ID search failed: {e}")
            return None
    
    def _fuzzy_search(self, toc_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Perform fuzzy search based on track count and duration"""
        try:
            tracks = toc_info['tracks']
            track_count = len(tracks)
            
            # Search for releases with similar track count
            query = f'tracks:{track_count}'
            
            result = mb.search_releases(
                query=query,
                limit=10,
                format='json'
            )
            
            if result['release-list']:
                # Take the first match for now
                release = result['release-list'][0]
                return self._parse_musicbrainz_release(release, track_count)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Fuzzy search failed: {e}")
            return None
    
    def _parse_musicbrainz_release(self, release: Dict, expected_tracks: int) -> Dict[str, Any]:
        """Parse MusicBrainz release data"""
        try:
            # Get detailed release information
            release_id = release['id']
            detailed_release = mb.get_release_by_id(
                release_id,
                includes=['recordings', 'artist-credits']
            )
            
            release_data = detailed_release['release']
            
            # Extract basic album info
            metadata = {
                'artist': self._get_artist_name(release_data.get('artist-credit', [])),
                'album': release_data.get('title', 'Unknown Album'),
                'date': self._get_release_date(release_data),
                'musicbrainz_id': release_id,
                'tracks': []
            }
            
            # Extract track information
            if 'medium-list' in release_data:
                for medium in release_data['medium-list']:
                    if 'track-list' in medium:
                        for track in medium['track-list']:
                            track_info = {
                                'title': track.get('title', 'Unknown Track'),
                                'artist': self._get_artist_name(track.get('artist-credit', [])),
                                'length': track.get('length'),
                                'position': track.get('position', 0)
                            }
                            metadata['tracks'].append(track_info)
            
            # Pad with default tracks if we don't have enough
            while len(metadata['tracks']) < expected_tracks:
                track_num = len(metadata['tracks']) + 1
                metadata['tracks'].append({
                    'title': f'Track {track_num:02d}',
                    'artist': metadata['artist'],
                    'position': track_num
                })
            
            self.logger.info(f"Found metadata: {metadata['artist']} - {metadata['album']}")
            return metadata
            
        except Exception as e:
            self.logger.error(f"Failed to parse MusicBrainz release: {e}")
            return None
    
    def _get_artist_name(self, artist_credit: List) -> str:
        """Extract artist name from artist credit"""
        if not artist_credit:
            return 'Unknown Artist'
        
        if isinstance(artist_credit, list) and len(artist_credit) > 0:
            if 'artist' in artist_credit[0]:
                return artist_credit[0]['artist'].get('name', 'Unknown Artist')
            elif 'name' in artist_credit[0]:
                return artist_credit[0]['name']
        
        return 'Unknown Artist'
    
    def _get_release_date(self, release_data: Dict) -> str:
        """Extract release date"""
        date = release_data.get('date', '')
        if date:
            # Extract year from full date
            return date.split('-')[0]
        
        # Try other date fields
        for date_field in ['first-release-date', 'release-date']:
            if date_field in release_data:
                date = release_data[date_field]
                if date:
                    return date.split('-')[0]
        
        return ''
    
    def _get_default_metadata(self, toc_info: Dict[str, Any]) -> Dict[str, Any]:
        """Get default metadata when MusicBrainz lookup fails"""
        tracks = toc_info['tracks']
        
        metadata = {
            'artist': 'Unknown Artist',
            'album': 'Unknown Album',
            'date': '',
            'tracks': []
        }
        
        for i, track in enumerate(tracks, 1):
            metadata['tracks'].append({
                'title': f'Track {i:02d}',
                'artist': 'Unknown Artist',
                'position': i
            })
        
        return metadata
