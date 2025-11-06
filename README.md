# Virt-Manager Linked Clone Extension

This project adds linked clone functionality to virt-manager (Virtual Machine Manager), allowing you to create space-efficient linked clones of virtual machines directly from the virt-manager GUI.

## Overview

Linked clones are virtual machine clones that share the same base disk image as the source VM, using qcow2's copy-on-write (COW) feature. This means:

- **Space Efficient**: Linked clones only store changes from the base image, saving significant disk space
- **Fast Creation**: Creating a linked clone is much faster than a full clone
- **GUI Integration**: Accessible directly from virt-manager's VM context menu

## Features

- **Integrated Menu Item**: Adds a "Create Linked Clone…" option to the VM context menu in virt-manager
- **Automatic Disk Management**: Automatically creates qcow2 COW images with proper backing file configuration
- **Permission Handling**: Automatically handles file permissions and SELinux contexts
- **Error Handling**: Provides clear error messages if something goes wrong
- **Connection Support**: Works with both local and remote libvirt connections

## Requirements

- **virt-manager**: Virtual Machine Manager (GUI application)
- **libvirt**: Virtualization library and daemon
- **qemu-img**: QEMU disk image utility (for creating COW images)
- **virt-clone**: Utility for cloning VM definitions (part of virt-manager package)
- **virsh**: Libvirt command-line tool
- **bash**: Shell interpreter
- **sudo**: For handling permission issues (optional but recommended)

## Installation

### Quick Install

Run the provided install script:

```bash
sudo ./install.sh
```

The install script will:
1. Detect your virt-manager installation location
2. Backup the original `manager.py` file
3. Install the modified `manager.py` to `/usr/share/virt-manager/virtManager/`
4. Install `vmm_linked_clone.sh` to `/usr/local/bin/`
5. Set proper permissions on all files

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

4. **Restart virt-manager** (if it's running):
   Close and reopen virt-manager for changes to take effect.

## Usage

1. **Open virt-manager** and connect to your libvirt host
2. **Right-click** on a VM in the list
3. **Select "Create Linked Clone…"** from the context menu
4. **Enter a name** for the new linked clone (default: `original-name-linked`)
5. **Click OK** to create the clone

The script will:
- Create a new qcow2 disk image with the source VM's disk as a backing file
- Clone the VM definition with the new disk
- Refresh the virt-manager view to show the new VM

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

## Uninstallation

To remove this extension:

1. **Restore the original manager.py**:
   ```bash
   sudo mv /usr/share/virt-manager/virtManager/manager.py.backup \
          /usr/share/virt-manager/virtManager/manager.py
   ```

2. **Remove the shell script** (optional):
   ```bash
   sudo rm /usr/local/bin/vmm_linked_clone.sh
   ```

3. **Restart virt-manager**

## Limitations

- **qcow2 Only**: Linked clones only work with qcow2 disk images
- **Backing File Dependency**: The source VM's disk must remain accessible
- **Single Disk**: Currently handles the first qcow2 disk only
- **No Snapshot Management**: Does not automatically manage backing file chains

## Files

- `manager.py`: Modified virt-manager manager module with linked clone menu integration
- `vmm_linked_clone.sh`: Shell script that performs the actual linked clone operation
- `install.sh`: Installation script
- `README.md`: This file

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

