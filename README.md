# Virt-Manager Linked Clone Extension

This project adds linked clone functionality to virt-manager (Virtual Machine Manager), allowing you to create space-efficient linked clones of virtual machines directly from the virt-manager GUI.

## Overview

Linked clones are virtual machine clones that share the same base disk image as the source VM, using qcow2's copy-on-write (COW) feature. This means:

- **Space Efficient**: Linked clones only store changes from the base image, saving significant disk space
- **Fast Creation**: Creating a linked clone is much faster than a full clone
- **GUI Integration**: Accessible directly from virt-manager's VM context menu

## Features

- **Integrated Menu Item**: Adds a "Create Linked Clone…" option to the VM context menu in virt-manager
- **REST API**: FastAPI-based REST API for programmatic VM management
- **Automatic Disk Management**: Automatically creates qcow2 COW images with proper backing file configuration
- **Permission Handling**: Automatically handles file permissions and SELinux contexts
- **Error Handling**: Provides clear error messages if something goes wrong
- **Connection Support**: Works with both local and remote libvirt connections
- **RPM Package**: Easy installation via RPM package with systemd service integration

## Requirements

- **virt-manager**: Virtual Machine Manager (GUI application)
- **libvirt**: Virtualization library and daemon
- **qemu-img**: QEMU disk image utility (for creating COW images)
- **virt-clone**: Utility for cloning VM definitions (part of virt-manager package)
- **virsh**: Libvirt command-line tool
- **bash**: Shell interpreter
- **sudo**: For handling permission issues (optional but recommended)
- **Python 3**: For the REST API (Python 3.7+)
- **FastAPI, Uvicorn, Pydantic**: Python packages for the REST API (installed via RPM or pip)

## Installation

### RPM Installation (Recommended)

The easiest way to install all components is via the RPM package:

**Option 1: Use the pre-built RPM** (if available in the project folder):
   ```bash
   sudo rpm -ivh vmm-linked-clone-1.0.0-1.fc41.noarch.rpm
   ```

   Or if upgrading:
   ```bash
   sudo rpm -Uvh vmm-linked-clone-1.0.0-1.fc41.noarch.rpm
   ```

**Option 2: Build and install from source**:
1. **Build the RPM**:
   ```bash
   make rpm
   ```

2. **Install the RPM**:
   ```bash
   sudo rpm -ivh ~/rpmbuild/RPMS/noarch/vmm-linked-clone-1.0.0-1.fc41.noarch.rpm
   ```

   Or if upgrading:
   ```bash
   sudo rpm -Uvh ~/rpmbuild/RPMS/noarch/vmm-linked-clone-1.0.0-1.fc41.noarch.rpm
   ```

The RPM package installs:
- virt-manager extension (`manager.py`) to `/usr/share/virt-manager/virtManager/`
- Linked clone script (`vmm_linked_clone.sh`) to `/usr/bin/`
- REST API script (`virsh_api.py`) to `/usr/bin/`
- Python requirements file to `/usr/share/vmm-linked-clone/`
- Systemd service file (`vmm-linked-clone-api.service`) to `/usr/lib/systemd/system/`

The API service is automatically enabled and started after installation. See the [RPM Package](#rpm-package) section for more details.

### Manual Installation

If you prefer to install manually:

1. **Backup the original manager.py**:
   ```bash
   sudo cp /usr/share/virt-manager/virtManager/manager.py \
          /usr/share/virt-manager/virtManager/manager.py.backup
   ```

2. **Install the modified manager.py**:
   ```bash
   sudo cp manager.py /usr/share/virt-manager/virtManager/manager.py
   sudo chmod 644 /usr/share/virt-manager/virtManager/manager.py
   ```

3. **Install the shell script**:
   ```bash
   sudo cp vmm_linked_clone.sh /usr/local/bin/vmm_linked_clone.sh
   sudo chmod 755 /usr/local/bin/vmm_linked_clone.sh
   ```

4. **Install the REST API** (optional):
   ```bash
   sudo cp virsh_api.py /usr/local/bin/virsh_api.py
   sudo chmod 755 /usr/local/bin/virsh_api.py
   pip3 install fastapi uvicorn pydantic
   ```

5. **Restart virt-manager** (if it's running):
   Close and reopen virt-manager for changes to take effect.

## Usage

### Using virt-manager GUI

1. **Open virt-manager** and connect to your libvirt host
2. **Right-click** on a VM in the list
3. **Select "Create Linked Clone…"** from the context menu
4. **Enter a name** for the new linked clone (default: `original-name-linked`)
5. **Click OK** to create the clone

The script will:
- Create a new qcow2 disk image with the source VM's disk as a backing file
- Clone the VM definition with the new disk
- Refresh the virt-manager view to show the new VM

### Using the REST API

The REST API provides programmatic access to VM management operations. After installation via RPM, the API service runs automatically on port 9393.

#### API Endpoints

**General:**
- `GET /` - API information and version

**VM Management:**
- `GET /api/v1/vms` - List all virtual machines
  - Query parameters: `connection_uri` (optional), `state` (optional filter)
- `GET /api/v1/vms/{vm_name}/status` - Get detailed VM status
  - Query parameters: `connection_uri` (optional)
- `POST /api/v1/vms/{vm_name}/start` - Power on a VM
- `POST /api/v1/vms/{vm_name}/shutdown` - Gracefully shutdown a VM
- `POST /api/v1/vms/{vm_name}/destroy` - Force power off a VM
- `POST /api/v1/vms/{vm_name}/reboot` - Reboot a VM
- `POST /api/v1/vms/{vm_name}/pause` - Pause (suspend) a VM
- `POST /api/v1/vms/{vm_name}/resume` - Resume a paused VM
- `GET /api/v1/vms/{vm_name}/console` - Get console information
- `POST /api/v1/vms/{vm_name}/linked-clone` - Create a linked clone
  - Request body: `{"new_vm_name": "clone-name", "disk_target": "optional/path", "connection_uri": "optional"}`
- `DELETE /api/v1/vms/{vm_name}/delete` - Delete a VM and all its storage
  - WARNING: This permanently deletes the VM and all associated disk images
  - Query parameters: `connection_uri` (optional)
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /openapi.json` - OpenAPI specification

#### Example API Usage

```bash
# List all VMs
curl http://localhost:9393/api/v1/vms

# Get VM status
curl http://localhost:9393/api/v1/vms/my-vm/status

# Start a VM
curl -X POST http://localhost:9393/api/v1/vms/my-vm/start

# Create a linked clone
curl -X POST http://localhost:9393/api/v1/vms/my-vm/linked-clone \
  -H "Content-Type: application/json" \
  -d '{"new_vm_name": "my-vm-clone"}'

# Delete a VM and all its storage (WARNING: irreversible)
curl -X DELETE http://localhost:9393/api/v1/vms/my-vm/delete

# View interactive API documentation
# Open http://localhost:9393/docs in your browser
```

#### Service Management

```bash
# Check service status
sudo systemctl status vmm-linked-clone-api

# Start/stop/restart the API service
sudo systemctl start vmm-linked-clone-api
sudo systemctl stop vmm-linked-clone-api
sudo systemctl restart vmm-linked-clone-api

# View logs
sudo journalctl -u vmm-linked-clone-api -f
```

#### API Configuration

The API runs on port 9393 by default. To change the port, edit the systemd service:

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

## How It Works

### Linked Clone Process

1. **Disk Creation**: The script identifies the first qcow2 disk from the source VM
2. **COW Image**: Creates a new qcow2 image using the source disk as a backing file
3. **VM Cloning**: Uses `virt-clone` to duplicate the VM definition, pointing to the new linked disk
4. **Permissions**: Automatically handles file permissions and SELinux contexts

### Technical Details

- **Backing File**: The source VM's disk becomes the backing file for the clone
- **Storage Location**: By default, the clone's disk is created in the same directory as the source disk
- **Format**: Only works with qcow2 disk images (raw/LVM images cannot be linked)
- **Connection URI**: Supports both local and remote libvirt connections

## Troubleshooting

### Permission Errors

If you encounter permission errors:

```bash
# Make the source disk readable
sudo chmod 644 /path/to/source/disk.qcow2

# Ensure target directory is writable
sudo chmod 755 /path/to/target/directory
```

### SELinux Issues (Fedora/RHEL)

If SELinux blocks access:

```bash
# Fix SELinux context
sudo restorecon -Rv /path/to/vm/disks/
```

### VM Not Appearing

If the clone completes but doesn't appear in virt-manager:
- Close and reopen virt-manager
- Or manually refresh the connection

### Script Not Found

If you get "script not found" errors:
- Verify the script is installed: `ls -l /usr/local/bin/vmm_linked_clone.sh`
- Check permissions: `sudo chmod 755 /usr/local/bin/vmm_linked_clone.sh`

## RPM Package

The RPM package provides a complete installation solution that includes:

- **virt-manager extension** - Adds linked clone functionality to the GUI
- **Linked clone script** - Shell script for creating linked clones
- **REST API** - FastAPI-based API for programmatic VM management
- **Systemd service** - Automatic service management for the API

### Building the RPM

See [BUILD.md](BUILD.md) for detailed build instructions. Quick build:

```bash
# Install build dependencies (first time)
make install-deps

# Setup RPM build environment (first time)
rpmdev-setuptree

# Build the RPM
make rpm
```

The built RPM will be at:
```
~/rpmbuild/RPMS/noarch/vmm-linked-clone-1.0.0-1.fc41.noarch.rpm
```

### RPM Installation

**From project folder** (if pre-built RPM is available):
```bash
sudo rpm -ivh vmm-linked-clone-1.0.0-1.fc41.noarch.rpm
```

**From build directory** (after building):
```bash
sudo rpm -ivh ~/rpmbuild/RPMS/noarch/vmm-linked-clone-1.0.0-1.fc41.noarch.rpm
```

Or if upgrading:
```bash
sudo rpm -Uvh vmm-linked-clone-1.0.0-1.fc41.noarch.rpm
# or
sudo rpm -Uvh ~/rpmbuild/RPMS/noarch/vmm-linked-clone-1.0.0-1.fc41.noarch.rpm
```

The service is automatically enabled and started after installation.

### RPM Uninstallation

```bash
sudo rpm -e vmm-linked-clone
```

This will:
- Stop and disable the API service
- Remove all installed files
- Note: The original `manager.py.backup` (if created) will remain

## Uninstallation

### If Installed via RPM

```bash
sudo rpm -e vmm-linked-clone
```

### If Installed Manually

1. **Restore the original manager.py**:
   ```bash
   sudo mv /usr/share/virt-manager/virtManager/manager.py.backup \
          /usr/share/virt-manager/virtManager/manager.py
   ```

2. **Remove the shell script**:
   ```bash
   sudo rm /usr/local/bin/vmm_linked_clone.sh
   ```

3. **Remove the API script** (if installed):
   ```bash
   sudo rm /usr/local/bin/virsh_api.py
   sudo systemctl stop vmm-linked-clone-api 2>/dev/null || true
   sudo systemctl disable vmm-linked-clone-api 2>/dev/null || true
   ```

4. **Restart virt-manager**

## Limitations

- **qcow2 Only**: Linked clones only work with qcow2 disk images
- **Backing File Dependency**: The source VM's disk must remain accessible
- **Single Disk**: Currently handles the first qcow2 disk only
- **No Snapshot Management**: Does not automatically manage backing file chains

## Files

- `manager.py`: Modified virt-manager manager module with linked clone menu integration
- `vmm_linked_clone.sh`: Shell script that performs the actual linked clone operation
- `virsh_api.py`: FastAPI REST API for programmatic VM management
- `vmm-linked-clone.spec`: RPM spec file for building the package
- `vmm-linked-clone-api.service`: Systemd service file for the API
- `vmm-linked-clone-1.0.0-1.fc41.noarch.rpm`: Pre-built RPM package (if available)
- `Makefile`: Build automation for RPM package
- `install.sh`: Manual installation script
- `requirements.txt`: Python dependencies for the API
- `README.md`: This file
- `BUILD.md`: Detailed RPM build instructions
- `RPM_README.md`: RPM package documentation

## License

This project modifies code from virt-manager, which is licensed under the GNU GPLv2 or later. See the COPYING file in the virt-manager source distribution.

## Contributing

This is a modification/extension to virt-manager. If you encounter issues or have improvements:

1. Check that all requirements are met
2. Verify file permissions and paths
3. Review error messages for specific guidance

## Notes

- Always backup your VMs before creating clones
- Linked clones share the base disk, so corruption of the base disk affects all clones
- Consider the implications of deleting the source VM when linked clones exist
- This modification is not officially supported by the virt-manager project

