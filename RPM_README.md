# RPM Package for vmm-linked-clone

This RPM package installs:
1. **virt-manager extension** (`manager.py`) - Adds linked clone functionality to virt-manager
2. **Linked clone script** (`vmm_linked_clone.sh`) - Creates space-efficient VM clones
3. **FastAPI REST API** (`virsh_api.py`) - REST API for managing VMs via virsh commands
4. **Systemd service** - Automatically starts the API server on port 9393

## Quick Start

### Build the RPM

```bash
# Install build dependencies (first time only)
make install-deps

# Setup RPM build environment (first time only)
rpmdev-setuptree

# Build the RPM
make rpm
```

### Install the RPM

```bash
sudo rpm -ivh ~/rpmbuild/RPMS/noarch/vmm-linked-clone-1.0.0-1.noarch.rpm
```

The service will automatically start and be enabled for boot.

### Verify Installation

```bash
# Check service status
sudo systemctl status vmm-linked-clone-api

# Test the API
curl http://localhost:9393/

# View API documentation
# Open http://localhost:9393/docs in your browser
```

## Package Contents

| File | Location | Description |
|------|----------|-------------|
| manager.py | `/usr/share/virt-manager/virtManager/` | virt-manager extension |
| vmm_linked_clone.sh | `/usr/bin/` | Linked clone script |
| virsh_api.py | `/usr/bin/` | FastAPI REST API |
| requirements.txt | `/usr/share/vmm-linked-clone/` | Python dependencies |
| vmm-linked-clone-api.service | `/usr/lib/systemd/system/` | Systemd service |

## Service Management

```bash
# Start service
sudo systemctl start vmm-linked-clone-api

# Stop service
sudo systemctl stop vmm-linked-clone-api

# Restart service
sudo systemctl restart vmm-linked-clone-api

# Enable/disable at boot
sudo systemctl enable vmm-linked-clone-api
sudo systemctl disable vmm-linked-clone-api

# View logs
sudo journalctl -u vmm-linked-clone-api -f
```

## API Endpoints

Once installed, the API is available at `http://localhost:9393`:

- `GET /` - API information
- `GET /api/v1/vms` - List all VMs
- `GET /api/v1/vms/{vm_name}/status` - Get VM status
- `POST /api/v1/vms/{vm_name}/start` - Power on VM
- `POST /api/v1/vms/{vm_name}/shutdown` - Power off VM
- `POST /api/v1/vms/{vm_name}/linked-clone` - Create linked clone
- `GET /docs` - Interactive API documentation

## Configuration

The API server runs on port 9393 by default. To change the port, edit the systemd service:

```bash
sudo systemctl edit vmm-linked-clone-api
```

Add:
```ini
[Service]
Environment="VIRSH_API_PORT=8080"
```

Then restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart vmm-linked-clone-api
```

## Uninstallation

```bash
sudo rpm -e vmm-linked-clone
```

This will:
- Stop and disable the API service
- Remove all installed files
- Note: Original `manager.py.backup` (if created) will remain

## Troubleshooting

### Service won't start

1. Check logs:
   ```bash
   sudo journalctl -u vmm-linked-clone-api -n 50
   ```

2. Verify Python dependencies:
   ```bash
   python3 -c "import fastapi, uvicorn, pydantic"
   ```

3. Check if port is in use:
   ```bash
   sudo netstat -tlnp | grep 9393
   ```

### API not accessible

1. Check firewall:
   ```bash
   sudo firewall-cmd --list-ports
   sudo firewall-cmd --add-port=9393/tcp --permanent
   sudo firewall-cmd --reload
   ```

2. Verify service is running:
   ```bash
   sudo systemctl status vmm-linked-clone-api
   ```

### virt-manager extension not working

1. Restart virt-manager after installation
2. Check if manager.py was installed:
   ```bash
   ls -l /usr/share/virt-manager/virtManager/manager.py
   ```
3. Check for backup file:
   ```bash
   ls -l /usr/share/virt-manager/virtManager/manager.py.backup
   ```

## Building from Source

See [BUILD.md](BUILD.md) for detailed build instructions.

