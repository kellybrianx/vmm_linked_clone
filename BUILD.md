# Building the RPM Package

This document describes how to build the RPM package for vmm-linked-clone.

## Prerequisites

1. **RPM build tools**:
   ```bash
   sudo dnf install -y rpm-build rpmdevtools
   # or on RHEL/CentOS:
   sudo yum install -y rpm-build rpmdevtools
   ```

2. **Python dependencies** (for the API):
   ```bash
   sudo dnf install -y python3-fastapi python3-uvicorn python3-pydantic
   # or install via pip:
   pip3 install fastapi uvicorn pydantic
   ```

3. **Setup RPM build environment** (first time only):
   ```bash
   rpmdev-setuptree
   ```

## Building the RPM

### Using the Makefile (Recommended)

```bash
# Build the RPM
make rpm

# Build only the source RPM
make srpm

# Clean build artifacts
make clean

# Install build dependencies
make install-deps
```

The built RPM will be located at:
```
~/rpmbuild/RPMS/noarch/vmm-linked-clone-1.0.0-1.noarch.rpm
```

### Manual Build

1. **Prepare the source tarball**:
   ```bash
   mkdir -p ~/rpmbuild/SOURCES
   tar -czf ~/rpmbuild/SOURCES/vmm-linked-clone-1.0.0.tar.gz \
       --transform="s,^,vmm-linked-clone-1.0.0/," \
       manager.py vmm_linked_clone.sh virsh_api.py \
       requirements.txt vmm-linked-clone-api.service README.md
   ```

2. **Copy the spec file**:
   ```bash
   cp vmm-linked-clone.spec ~/rpmbuild/SPECS/
   cp vmm-linked-clone-api.service ~/rpmbuild/SOURCES/
   ```

3. **Build the RPM**:
   ```bash
   rpmbuild -ba ~/rpmbuild/SPECS/vmm-linked-clone.spec
   ```

## Installing the RPM

```bash
sudo rpm -ivh ~/rpmbuild/RPMS/noarch/vmm-linked-clone-1.0.0-1.noarch.rpm
```

Or if upgrading:
```bash
sudo rpm -Uvh ~/rpmbuild/RPMS/noarch/vmm-linked-clone-1.0.0-1.noarch.rpm
```

## What Gets Installed

- `/usr/share/virt-manager/virtManager/manager.py` - virt-manager extension
- `/usr/bin/vmm_linked_clone.sh` - Linked clone script
- `/usr/bin/virsh_api.py` - FastAPI REST API
- `/usr/share/vmm-linked-clone/requirements.txt` - Python requirements
- `/usr/lib/systemd/system/vmm-linked-clone-api.service` - Systemd service

## Service Management

After installation, the service is automatically enabled and started. You can manage it with:

```bash
# Check status
sudo systemctl status vmm-linked-clone-api

# Start/stop/restart
sudo systemctl start vmm-linked-clone-api
sudo systemctl stop vmm-linked-clone-api
sudo systemctl restart vmm-linked-clone-api

# View logs
sudo journalctl -u vmm-linked-clone-api -f
```

## API Access

The API will be available at:
- HTTP: `http://localhost:9393`
- API Docs: `http://localhost:9393/docs`
- OpenAPI Spec: `http://localhost:9393/openapi.json`

## Uninstalling

```bash
sudo rpm -e vmm-linked-clone
```

This will:
- Stop and disable the systemd service
- Remove all installed files
- Note: The original `manager.py.backup` (if created) will remain

