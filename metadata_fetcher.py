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
        """Get metadata for the CD with robust error handling"""
        if not self.config['metadata']['use_musicbrainz'] or not MUSICBRAINZ_AVAILABLE:
            return self._get_default_metadata(toc_info)
        
        try:
            # Try to find release using TOC
            disc_id = self._calculate_disc_id(toc_info)
            if disc_id:
                release_info = self._search_by_disc_id(disc_id)
                if release_info:
                    return release_info
            
            # Fallback: try fuzzy search if we have enough tracks
            tracks = toc_info.get('tracks', [])
            if len(tracks) >= 3:  # Only try if we have at least 3 tracks
                fuzzy_result = self._fuzzy_search(toc_info)
                if fuzzy_result:
                    return fuzzy_result
            
        except Exception as e:
            self.logger.error(f"MusicBrainz metadata fetch failed: {e}")
        
        # Always fallback to default metadata
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
        """Perform fuzzy search based on track count and duration with safe access"""
        try:
            tracks = toc_info.get('tracks', [])
            if not tracks:
                self.logger.warning("No tracks in TOC info for fuzzy search")
                return None
                
            track_count = len(tracks)
            
            # Search for releases with similar track count
            query = f'tracks:{track_count}'
            
            result = mb.search_releases(
                query=query,
                limit=10,
                format='json'
            )
            
            # Safe access to search results
            release_list = result.get('release-list', []) if isinstance(result, dict) else []
            if release_list and len(release_list) > 0:
                # Take the first match for now
                release = release_list[0]
                if isinstance(release, dict):
                    return self._parse_musicbrainz_release(release, track_count)
            
            self.logger.info("No matching releases found in fuzzy search")
            return None
            
        except Exception as e:
            self.logger.error(f"Fuzzy search failed: {e}")
            return None
    
    def _parse_musicbrainz_release(self, release: Dict, expected_tracks: int) -> Dict[str, Any]:
        """Parse MusicBrainz release data with robust error handling"""
        try:
            # Get detailed release information
            release_id = release.get('id')
            if not release_id:
                self.logger.warning("No release ID found in MusicBrainz data")
                return None
                
            detailed_release = mb.get_release_by_id(
                release_id,
                includes=['recordings', 'artist-credits']
            )
            
            release_data = detailed_release.get('release', {})
            
            # Extract basic album info with safe attribute access
            metadata = {
                'artist': self._get_artist_name(release_data.get('artist-credit', [])),
                'album': release_data.get('title', 'Unknown Album'),
                'date': self._get_release_date(release_data),
                'musicbrainz_id': release_id,
                'tracks': []
            }
            
            # Extract track information with safe access
            medium_list = release_data.get('medium-list', [])
            if medium_list:
                for medium in medium_list:
                    track_list = medium.get('track-list', [])
                    for track in track_list:
                        if not isinstance(track, dict):
                            continue
                            
                        # Safe track recording access
                        recording = track.get('recording', {})
                        track_title = track.get('title') or recording.get('title', 'Unknown Track')
                        
                        track_info = {
                            'title': track_title,
                            'artist': self._get_artist_name(track.get('artist-credit', []) or recording.get('artist-credit', [])),
                            'length': track.get('length') or recording.get('length'),
                            'position': track.get('position', len(metadata['tracks']) + 1)
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
            
            self.logger.info(f"Found metadata: {metadata['artist']} - {metadata['album']} ({len(metadata['tracks'])} tracks)")
            return metadata
            
        except Exception as e:
            self.logger.error(f"Failed to parse MusicBrainz release: {e}")
            self.logger.debug(f"Release data structure: {release}")
            return None
    
    def _get_artist_name(self, artist_credit: List) -> str:
        """Extract artist name from artist credit with safe access"""
        try:
            if not artist_credit:
                return 'Unknown Artist'
            
            if isinstance(artist_credit, list) and len(artist_credit) > 0:
                first_credit = artist_credit[0]
                if isinstance(first_credit, dict):
                    # Try artist.name first
                    if 'artist' in first_credit:
                        artist = first_credit['artist']
                        if isinstance(artist, dict) and 'name' in artist:
                            return artist['name']
                    
                    # Try direct name field
                    if 'name' in first_credit:
                        return first_credit['name']
            
            return 'Unknown Artist'
            
        except Exception as e:
            self.logger.warning(f"Error extracting artist name: {e}")
            return 'Unknown Artist'
    
    def _get_release_date(self, release_data: Dict) -> str:
        """Extract release date with safe access"""
        try:
            # Try main date field first
            date = release_data.get('date', '')
            if date and isinstance(date, str):
                # Extract year from full date
                return date.split('-')[0]
            
            # Try other date fields
            for date_field in ['first-release-date', 'release-date']:
                if date_field in release_data:
                    date = release_data[date_field]
                    if date and isinstance(date, str):
                        return date.split('-')[0]
            
            return ''
            
        except Exception as e:
            self.logger.warning(f"Error extracting release date: {e}")
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
