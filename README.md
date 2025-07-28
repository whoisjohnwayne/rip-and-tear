# 🎵 Rip and Tear - Automatic FLAC CD Ripping in Docker

A comprehensive Docker-based CD ripping solution that automatically detects CD insertion and rips to FLAC with metadata from MusicBrainz, AccurateRip verification, and a web-based monitoring interface.

## Features

### Core Functionality
- **Automatic CD Detection**: Monitors for CD insertion and starts ripping automatically
- **Dual Ripping Modes**: 
  - Burst mode (fast) with AccurateRip verification
  - Paranoia mode (slow but accurate) as fallback
- **FLAC Encoding**: High-quality FLAC output with configurable compression
- **Metadata Fetching**: Automatic metadata retrieval from MusicBrainz
- **CUE Sheet Generation**: Creates .cue files with precise gap information
- **Detailed Logging**: Comprehensive rip logs for each album

### EAC-Level Advanced Features
- **Pre-gap Detection**: Accurate detection and preservation of track gaps
- **HTOA Support**: Hidden Track One Audio detection and ripping
- **C2 Error Detection**: Support for drives with C2 error pointers
- **Test & Copy Mode**: Optional test read before actual ripping
- **Multiple Read Verification**: Read tracks multiple times for accuracy
- **Precise TOC Analysis**: Sector-accurate track boundary detection
- **CD-Text Reading**: Automatic CD-Text extraction when available
- **ISRC Code Detection**: International Standard Recording Code extraction
- **Catalog Number Detection**: UPC/EAN barcode reading
- **Drive Offset Correction**: Sample-accurate drive offset compensation

### Advanced Features
- **AccurateRip Verification**: Compares rips against the AccurateRip database
- **Selective Re-ripping**: Only re-rips tracks that fail AccurateRip verification (not entire albums)
- **Intelligent Workflow**: Burst mode → per-track verification → selective paranoia re-ripping
- **Drive Offset Correction**: Configurable drive offset for perfect rips
- **Web-based GUI**: Monitor progress and view logs from any browser
- **Docker Deployment**: Easy deployment with persistent configuration
- **Alpine Linux Base**: Lightweight Docker image

## Quick Start

### Using Portainer (Recommended for GUI Management)

1. **Use the pre-built image** in your Portainer stack:
```yaml
version: '3.8'
services:
  rip-and-tear:
    image: ghcr.io/your-username/rip-and-tear:latest
    privileged: true
    ports:
      - "8080:8080"
    volumes:
      - rip_and_tear_config:/config
      - rip_and_tear_output:/output
      - /dev:/dev
    devices:
      - /dev/cdrom:/dev/cdrom
    environment:
      - CONTACT_EMAIL=your-email@example.com  # CHANGE THIS
    restart: unless-stopped
volumes:
  rip_and_tear_config:
  rip_and_tear_output:
```

See [PORTAINER_DEPLOYMENT.md](PORTAINER_DEPLOYMENT.md) for detailed instructions.

### Using Docker Compose (Local Development)

1. **Create docker-compose.yml**:
```yaml
version: '3.8'

services:
  rip-and-tear:
    build: .
    container_name: rip-and-tear
    privileged: true  # Required for CD drive access
    ports:
      - "8080:8080"
    volumes:
      - ./config:/config
      - ./output:/output
      - ./logs:/logs
      - /dev:/dev  # CD drive access
    devices:
      - /dev/cdrom:/dev/cdrom  # Adjust for your CD drive
    environment:
      - OUTPUT_DIR=/output
      - CONFIG_DIR=/config
      - LOG_DIR=/logs
    restart: unless-stopped
```

2. **Start the container**:
```bash
docker-compose up -d
```

3. **Access the web interface**:
   Open http://localhost:8080 in your browser

### Manual Docker Run

```bash
docker build -t rip-and-tear .

docker run -d \
  --name rip-and-tear \
  --privileged \
  -p 8080:8080 \
  -v $(pwd)/config:/config \
  -v $(pwd)/output:/output \
  -v $(pwd)/logs:/logs \
  -v /dev:/dev \
  --device /dev/cdrom:/dev/cdrom \
  rip-and-tear
```

## Configuration

Rip and Tear supports configuration through multiple methods:

1. **Environment Variables** (Docker Compose - Recommended)
2. **YAML Configuration File** (`/config/config.yaml`)
3. **Interactive Configuration** (using `./configure.sh`)

### Quick Configuration

The easiest way to configure Rip and Tear is using the interactive helper:

```bash
./configure.sh
```

This will create a `docker-compose.override.yml` file with your personalized settings.

### Docker Compose Environment Variables

All configuration options are available as environment variables in `docker-compose.yml`:

#### CD Drive Settings
```yaml
environment:
  - CD_DEVICE=/dev/cdrom          # CD drive device path
  - DRIVE_OFFSET=0                # Drive offset correction (samples) - set to your drive's specific offset
  - DRIVE_SPEED=8                 # Ripping speed (1-24 or "max")
  - ENABLE_C2=true                # C2 error detection
  - TEST_AND_COPY=true            # Test read before rip
```

#### Ripping Strategy
```yaml
environment:
  - TRY_BURST_FIRST=true          # Try burst mode first
  - USE_ACCURATERIP=true          # AccurateRip verification
  - VERIFY_RERIP=true             # Verify and re-rip failed tracks
  - SELECTIVE_RERIP=true          # Only re-rip tracks that fail verification
  - PARANOIA_MODE=full            # Paranoia mode: full/overlap/neverskip
  - MAX_RETRIES=10                # Overall retry attempts
  - SECTOR_RETRIES=20             # Per-sector retries
  - ENABLE_GAP_DETECTION=true     # Track gap detection
  - READ_LEAD_IN=true             # HTOA detection
  - MULTIPLE_READ_VERIFICATION=true # Multiple read verification
```

#### Output Settings
```yaml
environment:
  - OUTPUT_FORMAT=flac            # Output format
  - COMPRESSION_LEVEL=8           # FLAC compression (0-8)
  - CREATE_LOG=true               # Create rip logs
  - PRESERVE_HTOA=true            # Extract hidden tracks
  - GAP_HANDLING=preserve         # Gap handling mode
```

#### Metadata Settings
```yaml
environment:
  - USE_MUSICBRAINZ=true          # Use MusicBrainz
  - MUSICBRAINZ_SERVER=musicbrainz.org
  - USER_AGENT=RipAndTear/1.0
  - CONTACT_EMAIL=user@example.com # Required by MusicBrainz
```

### Configuration Templates

For advanced users, copy and customize the template:

```bash
cp docker-compose.override.yml.template docker-compose.override.yml
# Edit docker-compose.override.yml with your settings
```

### YAML Configuration File

You can also edit `/config/config.yaml` directly:

### CD Drive Settings
```yaml
cd_drive:
  device: "/dev/cdrom"        # CD drive device path
  offset: 0                   # Drive offset correction (samples)
  speed: "max"               # Ripping speed
```

### Output Settings
```yaml
output:
  directory: "/output"        # Output directory for ripped files
  format: "flac"             # Output format (currently only FLAC)
  compression_level: 8        # FLAC compression level (0-8)
  create_log: true           # Create rip logs
```

### Enhanced Ripping Settings
```yaml
ripping:
  try_burst_first: true      # Try burst mode first
  use_accuraterip: true      # Verify with AccurateRip
  paranoia_mode: "full"      # Paranoia mode setting
  max_retries: 10            # Maximum retry attempts
  sector_retries: 20         # Retries per problematic sector
  enable_gap_detection: true # Detect track gaps
  read_lead_in: true         # Read lead-in for HTOA
  multiple_read_verification: true # Multiple reads for verification
```

### Advanced Drive Settings
```yaml
cd_drive:
  offset: 6                  # Drive offset in samples
  enable_c2: true           # Enable C2 error detection
  test_and_copy: true       # Test read before ripping
  speed: "4"                # Lower speed for accuracy
```

### Finding Your Drive Offset

Drive offset correction is crucial for accurate rips. Each CD drive has a unique offset that determines how it reads audio data relative to the actual track positions.

#### How to Find Your Drive Offset:

1. **AccurateRip Database**: The most reliable method
   - Look up your exact drive model at http://www.accuraterip.com/driveoffsets.htm
   - Find your drive by manufacturer and model number
   - Use the listed offset value

2. **EAC Drive Features Database**: Alternative source
   - Visit the Exact Audio Copy drive database
   - Search for your drive model
   - Note the "read sample offset correction" value

3. **CUETools Database**: Another option
   - Check the CUETools drive offset database
   - Search by manufacturer and model

4. **Manual Testing**: If your drive isn't listed
   - Rip the same CD with different offset values (-6, 0, +6, +12)
   - Compare with AccurateRip database results
   - The offset that gives AccurateRip matches is correct

#### Common Drive Offsets:
- **Most Pioneer drives**: +6 samples
- **Most LiteOn drives**: +6 samples  
- **Most ASUS drives**: +6 samples
- **Plextor Premium**: +30 samples
- **Default (unknown drives)**: 0 samples (no correction)

#### Setting Your Drive Offset:
```yaml
# In docker-compose.yml
environment:
  - DRIVE_OFFSET=6    # Replace with your drive's actual offset
```

**Important**: Using the wrong offset will result in slight timing errors that prevent AccurateRip verification, even for perfect rips.

### Metadata Settings
```yaml
metadata:
  use_musicbrainz: true      # Fetch metadata from MusicBrainz
  musicbrainz_server: "musicbrainz.org"
  user_agent: "CDRipper/1.0"
  contact_email: "user@example.com"  # Required by MusicBrainz
```

## Selective Re-ripping Workflow

Rip and Tear uses an intelligent selective re-ripping workflow to optimize both speed and accuracy:

### How It Works

1. **Burst Mode Ripping**: All tracks are initially ripped using burst mode (maximum speed)
2. **Per-Track AccurateRip Verification**: Each track is individually verified against the AccurateRip database
3. **Selective Re-ripping**: Only tracks that fail AccurateRip verification are re-ripped using paranoia mode
4. **Final Verification**: Re-ripped tracks are verified again to ensure accuracy

### Benefits

- **Faster Overall Ripping**: Most albums with good discs complete in burst mode
- **Targeted Accuracy**: Only problematic tracks get the slow, careful treatment
- **No Wasted Time**: Don't re-rip entire albums when only 1-2 tracks have issues
- **EAC-Level Accuracy**: Final results are as accurate as Exact Audio Copy

### Configuration

```yaml
ripping:
  try_burst_first: true        # Enable burst mode first
  use_accuraterip: true        # Enable AccurateRip verification
  verify_rerip: true           # Enable verification and re-ripping
  selective_rerip: true        # Only re-rip failed tracks (not entire album)
```

### Example Workflow

For a 12-track album:
1. All 12 tracks ripped in burst mode (fast)
2. Tracks 1-11 pass AccurateRip verification ✅
3. Track 12 fails AccurateRip verification ❌
4. Only Track 12 is re-ripped in paranoia mode
5. Track 12 passes verification on re-rip ✅
6. Album complete with all tracks verified

## Drive Offset Configuration

Different CD drives have different read offsets. For the most accurate rips:

1. Look up your drive on http://accuraterip.com/driveoffsets.htm
2. Set the `offset` value in your configuration
3. Restart the container

Example:
```yaml
cd_drive:
  offset: 6  # For drives with +6 sample offset
```

## Directory Structure

The application creates the following structure:

```
/output/
├── 2023 - Artist Name - Album Name/
│   ├── 01 - Track Name.flac
│   ├── 02 - Another Track.flac
│   ├── Album Name.cue
│   └── rip.log
└── 2024 - Another Artist - Another Album/
    └── ...
```

## Web Interface

The web GUI provides:

- **Real-time Status**: Current ripping progress and status
- **Progress Monitoring**: Track-by-track progress with progress bar
- **Configuration Display**: Current settings overview
- **Log Viewing**: Recent log entries
- **File Browser**: View ripped albums and files

Access at: http://localhost:8080

## System Requirements

### Host System
- Linux with CD drive
- Docker and Docker Compose
- CD drive accessible at `/dev/cdrom` (or configure accordingly)

### Docker Privileges
The container requires `--privileged` mode for CD drive access. This is necessary for:
- Hardware device access
- Low-level CD operations
- Accurate ripping functionality

## Troubleshooting

### CD Not Detected
1. Check that your CD drive is accessible: `ls -la /dev/cdrom`
2. Verify the drive path in configuration
3. Ensure the container has device access

### Permission Issues
1. Ensure the container runs with sufficient privileges
2. Check volume mount permissions
3. Verify the user can access the CD drive

### AccurateRip Not Working
1. Check internet connectivity in container
2. Verify firewall settings
3. Note: Some rare CDs may not be in the AccurateRip database

### Metadata Not Found
1. Verify MusicBrainz connectivity
2. Check the contact email in configuration (required by MusicBrainz)
3. Some CDs may not have metadata available

## Development

### Building from Source
```bash
git clone <repository>
cd rip-and-tear
docker build -t rip-and-tear .
```

### Adding Features
The application is modular with separate components for:
- `cd_ripper.py`: Core ripping functionality
- `metadata_fetcher.py`: MusicBrainz integration
- `web_gui.py`: Flask web interface
- `cd_monitor.py`: CD detection
- `accuraterip_checker.py`: AccurateRip verification

## Dependencies

### System Tools
- `cd-paranoia`: CD ripping
- `flac`: FLAC encoding
- `cdrdao`: CUE sheet support

### Python Libraries
- `flask`: Web interface
- `musicbrainzngs`: MusicBrainz API
- `requests`: HTTP requests
- `pyyaml`: Configuration parsing

## License

This project is open source. Please respect the licenses of the included tools and libraries.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review logs in the web interface
3. Check Docker logs: `docker logs rip-and-tear`

## Acknowledgments

- **cd-paranoia**: CD ripping engine
- **FLAC**: Audio encoding
- **MusicBrainz**: Metadata database
- **AccurateRip**: Rip verification database

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Why MIT License?

The MIT License is chosen for this project because:
- **Maximum Freedom**: Users can use, modify, and distribute the software freely
- **Commercial Use**: Allows commercial use without restrictions
- **No Copyleft**: No requirement to open source derivative works
- **Wide Compatibility**: Compatible with most other licenses
- **Industry Standard**: Most popular permissive license in the open source community

### Third-Party Dependencies

This project uses several open source dependencies, each with their own licenses:
- **Flask**: BSD-3-Clause License
- **cd-paranoia**: GPL-2.0 License (system dependency)
- **FLAC**: BSD-3-Clause License (system dependency)
- **MusicBrainz API**: Creative Commons (data), various licenses (software)

Note: While this application code is MIT licensed, some system dependencies (like cd-paranoia) are GPL licensed. This doesn't affect your use of the application but may impact redistribution of modified versions.
