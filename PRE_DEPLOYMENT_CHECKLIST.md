# Pre-Deployment Checklist for Rip and Tear

Before deploying Rip and Tear in Portainer, please verify these items:

## 🖥️ **Host System Requirements**

### Hardware
- [ ] **Physical CD/DVD drive** connected to the Docker host
- [ ] **Sufficient storage space** for ripped FLAC files (700MB per CD minimum)
- [ ] **Network connectivity** for MusicBrainz metadata and AccurateRip verification

### Operating System
- [ ] **Linux Docker host** (Windows/macOS may have device access limitations)
- [ ] **CD drive accessible** at `/dev/cdrom`, `/dev/sr0`, or similar device path
- [ ] **Privileged containers allowed** (required for device access)

### Test CD Drive Access
```bash
# On the Docker host, verify CD drive is accessible:
ls -la /dev/cdrom /dev/sr* /dev/dvd*

# Test with a CD inserted:
cd-paranoia -Q  # Should show disc information
```

## 🐳 **Docker Environment**

### Portainer Setup
- [ ] **Portainer deployed** and managing the target Docker host
- [ ] **Privileged container support** enabled in Portainer
- [ ] **Device mapping support** available (Linux hosts)

### Registry Access
- [ ] **Container registry** accessible (GitHub Container Registry, Docker Hub, etc.)
- [ ] **Image pushed** to registry if using pre-built method
- [ ] **Registry authentication** configured if using private registry

## 📝 **Configuration Items to Update**

### Required Changes
- [ ] **Update image name** in docker-compose.portainer.yml:
  ```yaml
  image: ghcr.io/YOUR-USERNAME/rip-and-tear:latest
  ```

- [ ] **Set contact email** (required by MusicBrainz):
  ```yaml
  - CONTACT_EMAIL=your-actual-email@example.com
  ```

### Optional But Recommended
- [ ] **Set drive offset** for your specific CD drive:
  ```yaml
  - DRIVE_OFFSET=6  # Look up your drive at accuraterip.com
  ```

- [ ] **Verify CD device path**:
  ```yaml
  - CD_DEVICE=/dev/cdrom  # Change if your device is different
  ```

- [ ] **Adjust output directory** if using bind mounts:
  ```yaml
  volumes:
    - /your/host/path/output:/output
  ```

## 🔒 **Security Considerations**

### Privileged Mode
- [ ] **Understand security implications** of privileged containers
- [ ] **Network isolation** considered if running on shared systems
- [ ] **Access controls** in place for web interface (port 8080)

### Volume Security
- [ ] **Output directory permissions** appropriate for your environment
- [ ] **Log directory access** controlled if using bind mounts

## 🌐 **Network Requirements**

### Outbound Access Required
- [ ] **MusicBrainz API**: `musicbrainz.org` (port 443)
- [ ] **AccurateRip database**: `www.accuraterip.com` (port 80/443)
- [ ] **Container registry**: For image pulls if needed

### Inbound Access
- [ ] **Port 8080** accessible for web interface
- [ ] **Firewall rules** configured if needed

## 📁 **File System Considerations**

### Storage Requirements
- [ ] **Minimum 1GB free space** per CD (FLAC files are ~300-700MB per CD)
- [ ] **Fast storage recommended** for better ripping performance
- [ ] **Backup strategy** for ripped files if important

### Volume Strategy Decision
Choose one approach:

**Named Volumes (Default)**:
```yaml
volumes:
  - rip_and_tear_output:/output
```
- ✅ Easy Portainer management
- ❌ Need commands to access files

**Bind Mounts**:
```yaml
volumes:
  - /host/path/music:/output
```
- ✅ Direct file access
- ❌ Host path dependencies

## 🧪 **Testing Plan**

### After Deployment
1. [ ] **Container starts successfully** (check Portainer logs)
2. [ ] **Web interface accessible** at `http://docker-host:8080`
3. [ ] **CD detection working** (insert test CD, check logs)
4. [ ] **Test rip** with a disposable CD
5. [ ] **File output** appears in expected location
6. [ ] **Metadata fetching** works (requires internet)

### Test Commands
```bash
# Check container health
docker ps | grep rip-and-tear

# View logs
docker logs rip-and-tear

# Test CD drive access inside container
docker exec rip-and-tear cd-paranoia -Q

# Check output files
docker exec rip-and-tear ls -la /output
```

## 🚨 **Common Issues to Avoid**

### Device Access
- **Wrong device path**: Verify actual CD device path on host
- **No privileged mode**: Container must be privileged for device access
- **SELinux/AppArmor**: May block device access, check security policies

### Portainer Specific
- **Image not found**: Ensure image is pushed to accessible registry
- **Volume permissions**: Named volumes may have permission issues
- **Health check failures**: Allow time for application startup (40s start period)

### Environment Variables
- **Missing email**: MusicBrainz requires valid contact email
- **Invalid drive offset**: Can cause track boundary issues
- **Configuration typos**: YAML syntax errors prevent deployment

## ✅ **Ready to Deploy**

Once all items are checked:

1. **Copy** `docker-compose.portainer.yml` content
2. **Update** configuration values as needed
3. **Deploy** in Portainer: Stacks → Add Stack
4. **Monitor** container startup in Portainer logs
5. **Test** with a CD insertion

## 📞 **Support Resources**

- **Drive offsets**: http://accuraterip.com/driveoffsets.htm
- **MusicBrainz API**: https://musicbrainz.org/doc/MusicBrainz_API
- **Docker device mapping**: https://docs.docker.com/engine/reference/run/#runtime-privilege-and-linux-capabilities
- **Portainer documentation**: https://documentation.portainer.io/

---

**Note**: This application requires physical hardware access (CD drive) and privileged container mode. It's designed for trusted environments where you control the Docker host.
