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
        
        # Set up MusicBrainz user agent as required by their API
        mb.set_useragent("Rip-and-Tear", "1.0", "https://github.com/user/rip-and-tear")
        
        # Configure MusicBrainz if additional settings are provided
        if 'metadata' in config:
            metadata_config = config['metadata']
            if 'user_agent' in metadata_config:
                mb.set_useragent(
                    metadata_config['user_agent'],
                    "1.0",
                    metadata_config.get('contact_email', "contact@example.com")
                )
            
            if metadata_config.get('musicbrainz_server', 'musicbrainz.org') != 'musicbrainz.org':
                mb.set_hostname(metadata_config['musicbrainz_server'])
    
    def _safe_get(self, data, *keys, default=None):
        """Safely navigate nested dictionary structure"""
        current = data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current if current is not None else default
    
    def _safe_get_string(self, data, *keys, default=''):
        """Safely get string value from nested dictionary"""
        value = self._safe_get(data, *keys, default=default)
        return str(value) if value is not None else default
    
    def _safe_get_list(self, data, *keys, default=None):
        """Safely get list value from nested dictionary"""
        if default is None:
            default = []
        value = self._safe_get(data, *keys, default=default)
        return value if isinstance(value, list) else default
    
    def get_metadata(self, toc_info: Dict[str, Any]) -> Dict[str, Any]:
        """Get metadata for the CD with robust error handling"""
        # Check if automatic metadata fetching is disabled
        metadata_config = self.config.get('metadata', {})
        if not metadata_config.get('auto_fetch', True):
            self.logger.info("Automatic metadata fetching disabled - using default track names for AccurateRip accuracy")
            return self._get_default_metadata(toc_info)
            
        if not metadata_config.get('use_musicbrainz', True) or not MUSICBRAINZ_AVAILABLE:
            return self._get_default_metadata(toc_info)
        
        try:
            # Prefer MusicBrainz disc ID if available, fall back to general disc_id
            musicbrainz_disc_id = toc_info.get('musicbrainz_disc_id')
            disc_id = toc_info.get('disc_id')
            
            if musicbrainz_disc_id:
                self.logger.info(f"Using MusicBrainz disc ID: {musicbrainz_disc_id}")
                release_info = self._search_by_disc_id(musicbrainz_disc_id)
                if release_info:
                    self.logger.info(f"Found exact MusicBrainz disc match: {release_info['artist']} - {release_info['album']}")
                    return release_info
            elif disc_id and disc_id != "UNKNOWN":
                self.logger.info(f"Using fallback disc ID: {disc_id}")
                release_info = self._search_by_disc_id(disc_id)
                if release_info:
                    self.logger.info(f"Found exact disc match: {release_info['artist']} - {release_info['album']}")
                    return release_info
            
            # DISABLE fuzzy search for now - it causes wrong album matches
            # This is critical for AccurateRip verification accuracy
            self.logger.warning("No exact disc ID match found - using default metadata to ensure AccurateRip accuracy")
            
        except Exception as e:
            self.logger.error(f"MusicBrainz metadata fetch failed: {e}")
        
        # Always fallback to default metadata
        return self._get_default_metadata(toc_info)
    
    def _calculate_disc_id(self, toc_info: Dict[str, Any]) -> Optional[str]:
        """Calculate MusicBrainz disc ID - DEPRECATED: Use real disc_id from TOC analysis"""
        # This method is deprecated - we now use the actual disc ID 
        # calculated from track offsets in the TOC analyzer
        self.logger.warning("Using deprecated disc ID calculation - should use real disc_id from TOC")
        return None
    
    def _search_by_disc_id(self, disc_id: str) -> Optional[Dict[str, Any]]:
        """Search MusicBrainz by disc ID using the proper disc ID lookup"""
        try:
            self.logger.info(f"Searching MusicBrainz for disc ID: {disc_id}")
            
            # Use the proper MusicBrainz disc ID lookup method
            result = mb.get_releases_by_discid(
                id=disc_id,
                includes=['artist-credits', 'recordings'],
                cdstubs=True
            )
            
            # Check for direct disc match
            if 'disc' in result:
                disc_data = result['disc']
                release_list = disc_data.get('release-list', [])
                if release_list:
                    self.logger.info(f"Found {len(release_list)} releases for disc ID {disc_id}")
                    # Use the first release
                    release = release_list[0]
                    if isinstance(release, dict):
                        return self._parse_musicbrainz_release(release, 0)  # Track count will be determined from MB data
            
            # Check for fuzzy match results
            if 'release-list' in result:
                release_list = result['release-list']
                if release_list:
                    self.logger.info(f"Found {len(release_list)} fuzzy matches for disc ID {disc_id}")
                    # Use the first fuzzy match
                    release = release_list[0]
                    if isinstance(release, dict):
                        return self._parse_musicbrainz_release(release, 0)  # Track count will be determined from MB data
            
            # Check for CD stub match
            if 'cdstub' in result:
                cdstub = result['cdstub']
                self.logger.info(f"Found CD stub for disc ID {disc_id}: {cdstub.get('title', 'Unknown')}")
                # Convert CD stub to release format for compatibility
                stub_release = {
                    'title': cdstub.get('title', 'Unknown Album'),
                    'artist-credit': [{'name': cdstub.get('artist', 'Unknown Artist')}],
                    'id': f"cdstub-{disc_id}",
                    'status': 'CD Stub'
                }
                return self._parse_musicbrainz_release(stub_release, 0)
            
            self.logger.info(f"No matches found for disc ID: {disc_id}")
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
                    if not isinstance(medium, dict):
                        continue
                        
                    track_list = medium.get('track-list', [])
                    for track in track_list:
                        if not isinstance(track, dict):
                            continue
                        
                        try:
                            # Safe track recording access
                            recording = track.get('recording', {})
                            if not isinstance(recording, dict):
                                recording = {}
                            
                            # Safe title extraction
                            track_title = track.get('title') or recording.get('title')
                            if not track_title or not isinstance(track_title, str):
                                track_title = 'Unknown Track'
                            
                            # Safe artist credit extraction
                            track_artist_credit = track.get('artist-credit', [])
                            recording_artist_credit = recording.get('artist-credit', [])
                            
                            # Use track artist credit first, fallback to recording
                            artist_credit = track_artist_credit if track_artist_credit else recording_artist_credit
                            track_artist = self._get_artist_name(artist_credit)
                            
                            # Safe length extraction with validation
                            track_length = track.get('length') or recording.get('length')
                            if track_length and isinstance(track_length, (str, int)):
                                try:
                                    # Ensure length is numeric (milliseconds)
                                    if isinstance(track_length, str):
                                        if track_length.isdigit():
                                            track_length = int(track_length)
                                        else:
                                            track_length = None
                                    elif isinstance(track_length, int) and track_length < 0:
                                        track_length = None
                                except (ValueError, TypeError):
                                    track_length = None
                            
                            # Safe position extraction with validation
                            position = track.get('position')
                            if position is not None:
                                try:
                                    if isinstance(position, str):
                                        if position.isdigit():
                                            position = int(position)
                                        else:
                                            position = len(metadata['tracks']) + 1
                                    elif not isinstance(position, int) or position <= 0:
                                        position = len(metadata['tracks']) + 1
                                except (ValueError, TypeError):
                                    position = len(metadata['tracks']) + 1
                            else:
                                position = len(metadata['tracks']) + 1
                            
                            track_info = {
                                'title': track_title,
                                'artist': track_artist,
                                'length': track_length,
                                'position': position
                            }
                            metadata['tracks'].append(track_info)
                            
                        except (AttributeError, KeyError, TypeError) as e:
                            self.logger.warning(f"Error processing track data: {e}")
                            # Add a default track instead of failing completely
                            track_num = len(metadata['tracks']) + 1
                            metadata['tracks'].append({
                                'title': f'Track {track_num:02d}',
                                'artist': metadata['artist'],
                                'length': None,
                                'position': track_num
                            })
                        except Exception as e:
                            self.logger.warning(f"Unexpected error processing track: {e}")
                            continue
            
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
    
    def _get_artist_name(self, artist_credit) -> str:
        """Extract artist name from artist credit with comprehensive field support"""
        try:
            if not artist_credit:
                return 'Unknown Artist'
            
            # Handle various artist credit formats from MusicBrainz
            if isinstance(artist_credit, list) and len(artist_credit) > 0:
                first_credit = artist_credit[0]
                if isinstance(first_credit, dict):
                    
                    # Try direct name field first (most common in artist-credit)
                    direct_name = self._safe_get_string(first_credit, 'name')
                    if direct_name and direct_name != '':
                        return direct_name
                    
                    # Try artist.name (nested structure)
                    artist_name = self._safe_get_string(first_credit, 'artist', 'name')
                    if artist_name and artist_name != '':
                        return artist_name
                    
                    # Try artist.sort-name as fallback
                    artist_sort_name = self._safe_get_string(first_credit, 'artist', 'sort-name')
                    if artist_sort_name and artist_sort_name != '':
                        return artist_sort_name
                    
                    # Try credited-as name (for aliased credits)
                    credited_as = self._safe_get_string(first_credit, 'credited-as')
                    if credited_as and credited_as != '':
                        return credited_as
                    
                    # Handle artist disambiguation fields gracefully
                    # MusicBrainz can return: type, type-id, gender, gender-id, 
                    # country, area, begin-area, end-area, life-span, etc.
                    # We just want the name, so we ignore these extra fields
                    
                    # Try any other name-like fields
                    for name_field in ['display-name', 'credit-name', 'artist-name']:
                        name_value = self._safe_get_string(first_credit, name_field)
                        if name_value and name_value != '':
                            return name_value
            
            # Handle single artist credit (not in list)
            elif isinstance(artist_credit, dict):
                artist_name = self._safe_get_string(artist_credit, 'name')
                if artist_name and artist_name != '':
                    return artist_name
            
            return 'Unknown Artist'
            
        except Exception as e:
            self.logger.warning(f"Unexpected error extracting artist name: {type(e).__name__}: {e}")
            self.logger.debug(f"Artist credit data type: {type(artist_credit)}")
            return 'Unknown Artist'
    
    def _get_release_date(self, release_data: Dict) -> str:
        """Extract release date with comprehensive field support"""
        try:
            # All possible date fields that MusicBrainz might return
            date_fields = [
                'date',                    # Primary date field
                'first-release-date',      # First release date
                'release-date',            # Release date
                'original-release-date',   # Original release date
                'recording-date',          # Recording date
                'earliest-release-date'    # Earliest known release
            ]
            
            # Try each date field
            for date_field in date_fields:
                date_value = self._safe_get_string(release_data, date_field)
                if date_value and date_value.strip():
                    # Extract year from date (handle various formats)
                    try:
                        # Handle YYYY, YYYY-MM, YYYY-MM-DD, and partial dates
                        date_clean = date_value.strip()
                        
                        # Remove common prefixes/suffixes
                        for prefix in ['ca. ', 'c. ', '~', 'circa ', 'about ']:
                            if date_clean.lower().startswith(prefix):
                                date_clean = date_clean[len(prefix):].strip()
                        
                        # Extract year part
                        year_part = date_clean.split('-')[0].split('/')[0].split('.')[0]
                        
                        # Validate year format (4 digits, reasonable range)
                        if year_part.isdigit() and len(year_part) == 4:
                            year_int = int(year_part)
                            if 1900 <= year_int <= 2030:  # Reasonable CD release range
                                return year_part
                    except (ValueError, IndexError):
                        continue
            
            # Try release-event-list (contains area and date info)
            release_events = self._safe_get_list(release_data, 'release-event-list')
            for event in release_events:
                if isinstance(event, dict):
                    # Try date field in release event
                    event_date = self._safe_get_string(event, 'date')
                    if event_date and event_date.strip():
                        try:
                            year = event_date.split('-')[0]
                            if year.isdigit() and len(year) == 4:
                                return year
                        except (ValueError, IndexError):
                            continue
                    
                    # Try area.date or other nested date fields
                    area_date = self._safe_get_string(event, 'area', 'date')
                    if area_date and area_date.strip():
                        try:
                            year = area_date.split('-')[0]
                            if year.isdigit() and len(year) == 4:
                                return year
                        except (ValueError, IndexError):
                            continue
            
            # Try label-info-list for label release dates
            label_info_list = self._safe_get_list(release_data, 'label-info-list')
            for label_info in label_info_list:
                if isinstance(label_info, dict):
                    label_date = self._safe_get_string(label_info, 'label', 'date')
                    if label_date and label_date.strip():
                        try:
                            year = label_date.split('-')[0]
                            if year.isdigit() and len(year) == 4:
                                return year
                        except (ValueError, IndexError):
                            continue
            
            # Try cover-art-archive date as last resort
            caa_date = self._safe_get_string(release_data, 'cover-art-archive', 'date')
            if caa_date and caa_date.strip():
                try:
                    year = caa_date.split('-')[0]
                    if year.isdigit() and len(year) == 4:
                        return year
                except (ValueError, IndexError):
                    pass
            
            return ''
            
        except Exception as e:
            self.logger.warning(f"Unexpected error extracting release date: {type(e).__name__}: {e}")
            available_fields = list(release_data.keys()) if isinstance(release_data, dict) else []
            self.logger.debug(f"Available release data fields: {available_fields}")
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
