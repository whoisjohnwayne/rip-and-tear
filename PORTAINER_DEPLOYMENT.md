# Portainer Deployment Guide for Rip and Tear

This guide shows how to deploy Rip and Tear using Portainer.

## Prerequisites

**🚨 Important**: Run `./validate-setup.sh` first to check your environment!

1. **Docker Host with CD Drive**: Portainer must be managing a Docker host that has a physical CD drive
2. **Privileged Container Support**: The host must allow privileged containers for CD drive access
3. **Device Access**: The CD drive device (usually `/dev/cdrom` or `/dev/sr0`) must be available
4. **Linux Host Recommended**: CD drive access works best on Linux Docker hosts

## Deployment Methods

### Method 1: Using Pre-built Image (Recommended)

1. **Push Image to Registry** (if you built locally):
   ```bash
   # Build and tag the image
   docker build -t ghcr.io/your-username/rip-and-tear:latest .
   
   # Push to GitHub Container Registry
   docker push ghcr.io/your-username/rip-and-tear:latest
   ```

2. **Deploy in Portainer**:
   - Go to **Stacks** → **Add Stack**
   - Name: `rip-and-tear`
   - Build method: **Web editor**
   - **For first-time users**: Use `docker-compose.portainer-minimal.yml`
   - **For advanced users**: Use `docker-compose.portainer.yml` (all options)
   - Update the image name to match your registry
   - Update `CONTACT_EMAIL` environment variable
   - Deploy the stack

### Method 2: Using Docker Hub Public Image

If you publish to Docker Hub:

```yaml
services:
  rip-and-tear:
    image: your-dockerhub-username/rip-and-tear:latest
    # ... rest of configuration
```

### Method 3: Build from Git Repository

1. In Portainer, go to **Stacks** → **Add Stack**
2. Build method: **Repository**
3. Repository URL: `https://github.com/your-username/rip-and-tear`
4. Compose path: `docker-compose.yml`
5. Deploy

## Configuration in Portainer

### Required Changes

Before deploying, update these environment variables in the compose file:

```yaml
environment:
  - CONTACT_EMAIL=your-email@example.com  # REQUIRED: Change this to your email
  - DRIVE_OFFSET=0                        # OPTIONAL: Set your drive's offset
  - CD_DEVICE=/dev/cdrom                  # OPTIONAL: Change if your CD device is different
```

### CD Drive Device Path

Check your CD drive device path on the Docker host:

```bash
# Find CD drive devices
ls -la /dev/cdrom /dev/sr* /dev/dvd*

# Test CD drive access
cd-paranoia -Q
```

Common device paths:
- `/dev/cdrom` (symlink to actual device)
- `/dev/sr0` (first SCSI CD/DVD drive)
- `/dev/sr1` (second SCSI CD/DVD drive)

### Volume Configuration

The Portainer version uses named volumes instead of bind mounts:

- `rip_and_tear_config`: Configuration files
- `rip_and_tear_output`: Ripped FLAC files
- `rip_and_tear_logs`: Application logs

To access files, you can:
1. Use Portainer's volume browser
2. Create a temporary container to access volumes
3. Set up bind mounts to host directories instead

### Alternative with Host Bind Mounts

If you prefer host directories, change the volumes section:

```yaml
volumes:
  - /path/on/host/config:/config
  - /path/on/host/output:/output
  - /path/on/host/logs:/logs
```

## Post-Deployment

1. **Check Container Status**: Verify the container is running in Portainer
2. **View Logs**: Check container logs for any startup errors
3. **Access Web Interface**: Navigate to `http://docker-host-ip:8080`
4. **Test CD Detection**: Insert a CD and monitor the logs

## Troubleshooting

### Common Issues

1. **CD Drive Not Detected**:
   - Verify device path in docker-compose
   - Check host permissions for CD drive
   - Ensure privileged mode is enabled

2. **Permission Denied**:
   - Container needs privileged mode for device access
   - Check if Portainer allows privileged containers

3. **Image Not Found**:
   - Verify image name and registry
   - Check if image is public or if authentication is needed

4. **Health Check Failing**:
   - Web interface may take time to start
   - Check if port 8080 is available

### Viewing Output Files

To access ripped files when using named volumes:

```bash
# Create temporary container to access volume
docker run --rm -v rip_and_tear_output:/output alpine ls -la /output

# Copy files from volume to host
docker run --rm -v rip_and_tear_output:/output -v $(pwd):/backup alpine cp -r /output/* /backup/
```

## Security Considerations

- **Privileged Mode**: Required for CD drive access, but increases security risk
- **Device Access**: Only expose necessary devices
- **Network**: Consider restricting web interface access if needed
- **Volumes**: Use appropriate permissions for output directories

## Example Complete Portainer Stack

```yaml
version: '3.8'

services:
  rip-and-tear:
    image: ghcr.io/your-username/rip-and-tear:latest
    container_name: rip-and-tear
    privileged: true
    ports:
      - "8080:8080"
    volumes:
      - rip_and_tear_config:/config
      - rip_and_tear_output:/output
      - rip_and_tear_logs:/logs
      - /dev:/dev
    devices:
      - /dev/cdrom:/dev/cdrom
    environment:
      - CONTACT_EMAIL=your-email@example.com
      - DRIVE_OFFSET=6  # Set for your specific drive
      - TRY_BURST_FIRST=true
      - USE_ACCURATERIP=true
      - SELECTIVE_RERIP=true
    restart: unless-stopped

volumes:
  rip_and_tear_config:
  rip_and_tear_output:
  rip_and_tear_logs:
```

After deployment, access the web interface at `http://your-docker-host:8080` to monitor ripping progress.
