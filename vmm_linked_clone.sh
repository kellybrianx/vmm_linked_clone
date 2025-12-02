#!/usr/bin/env bash
# vmm_linked_clone.sh <SOURCE_VM> <NEW_VM_NAME> [<DISK_TARGET>] [<CONNECTION_URI>]
# If <DISK_TARGET> omitted, we'll reuse the same storage dir as the source.
# If <CONNECTION_URI> provided, use it for virsh commands.

set -euo pipefail

SRC="$1"
NEW="$2"
TARGET="${3:-}"
CONN_URI="${4:-}"

if [[ -z "${SRC:-}" || -z "${NEW:-}" ]]; then
  echo "Usage: vmm_linked_clone.sh <SOURCE_VM> <NEW_VM_NAME> [<DISK_TARGET>] [<CONNECTION_URI>]" >&2
  exit 2
fi

# Verify domain exists first
if [[ -n "${CONN_URI:-}" ]]; then
  if ! virsh -c "$CONN_URI" dominfo "$SRC" >/dev/null 2>&1; then
    echo "error: failed to get domain '$SRC'" >&2
    echo "Available domains:" >&2
    virsh -c "$CONN_URI" list --all --name 2>&1 | sed 's/^/  - /' >&2
    exit 1
  fi
  # Get all block devices from the source domain
  BLK_LIST=$(virsh -c "$CONN_URI" domblklist --domain "$SRC")
  # Get first qcow2 disk path from the source domain (for backward compatibility)
  SRC_DISK=$(echo "$BLK_LIST" | awk '/qcow2/ {print $2; exit}')
else
  if ! virsh dominfo "$SRC" >/dev/null 2>&1; then
    echo "error: failed to get domain '$SRC'" >&2
    echo "Available domains:" >&2
    virsh list --all --name 2>&1 | sed 's/^/  - /' >&2
    exit 1
  fi
  # Get all block devices from the source domain
  BLK_LIST=$(virsh domblklist --domain "$SRC")
  # Get first qcow2 disk path from the source domain (for backward compatibility)
  SRC_DISK=$(echo "$BLK_LIST" | awk '/qcow2/ {print $2; exit}')
fi
if [[ -z "${SRC_DISK:-}" ]]; then
  echo "No qcow2 disk found on $SRC (raw/LVM images can't be linked)" >&2
  exit 3
fi

# Parse all block devices to identify which ones need to be handled
# Format: Target Source (e.g., "vda /path/to/disk.qcow2" or "vdb -")
# We need to collect all qcow2 disks and their device targets
declare -a QCOW2_DISKS=()
declare -a QCOW2_TARGETS=()
declare -a OTHER_DEVICES=()

# Parse block list (skip header lines)
while IFS= read -r line; do
  # Skip empty lines and header lines
  [[ -z "$line" || "$line" =~ ^(Target|-----|$) ]] && continue
  
  # Extract target device and source
  target=$(echo "$line" | awk '{print $1}')
  source=$(echo "$line" | awk '{print $2}')
  
  # Skip if no target or source is "-" (empty device)
  [[ -z "$target" ]] && continue
  
  if [[ "$source" == *".qcow2"* ]]; then
    # This is a qcow2 disk - we'll handle it
    QCOW2_TARGETS+=("$target")
    QCOW2_DISKS+=("$source")
  elif [[ "$source" != "-" && -n "$source" ]]; then
    # This is a non-qcow2 block device (CD-ROM, raw disk, etc.) - we'll ignore it
    OTHER_DEVICES+=("$target")
  fi
done <<< "$BLK_LIST"

# If we have multiple qcow2 disks, we'll clone all of them as linked clones
if [[ ${#QCOW2_DISKS[@]} -gt 1 ]]; then
  echo "Source VM has ${#QCOW2_DISKS[@]} qcow2 disk(s). All disks will be cloned as linked clones." >&2
  echo "Disks: ${QCOW2_TARGETS[*]}" >&2
fi

# Determine target directory for new disks
if [[ -z "${TARGET:-}" ]]; then
  TARGET_DIR=$(dirname "$SRC_DISK")
else
  mkdir -p "$TARGET"
  TARGET_DIR="$TARGET"
fi

# Create linked clone disk files for ALL qcow2 disks
# Store the mapping of target device -> new disk path
declare -A NEW_DISK_PATHS=()

for i in "${!QCOW2_DISKS[@]}"; do
  TARGET_DEV="${QCOW2_TARGETS[$i]}"
  SRC_DISK_PATH="${QCOW2_DISKS[$i]}"
  
  # Generate new disk filename based on target device
  # vda -> ${NEW}.qcow2, vdb -> ${NEW}-vdb.qcow2, etc.
  if [[ "$TARGET_DEV" == "${QCOW2_TARGETS[0]}" ]]; then
    # First disk uses the base name
    NEW_DISK_PATH="${TARGET_DIR}/${NEW}.qcow2"
  else
    # Additional disks get a suffix
    NEW_DISK_PATH="${TARGET_DIR}/${NEW}-${TARGET_DEV}.qcow2"
  fi
  
  NEW_DISK_PATHS["$TARGET_DEV"]="$NEW_DISK_PATH"
done

# For backward compatibility, set NEW_DISK to the first disk
NEW_DISK="${NEW_DISK_PATHS[${QCOW2_TARGETS[0]}]}"

# Create a qcow2 COW image using the source as the backing file
# Check if we can read the backing file - if not, try to fix permissions
if [[ ! -r "$SRC_DISK" ]]; then
  echo "Warning: Cannot read backing file $SRC_DISK (permission denied)" >&2
  echo "The backing file is owned by root. Attempting to fix permissions..." >&2
  
  # Try to add read permission for group/others (if we have sudo access)
  if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    echo "Adding read permissions to backing file..." >&2
    sudo chmod 644 "$SRC_DISK" 2>/dev/null || {
      echo "Failed to fix permissions. Please run manually:" >&2
      echo "  sudo chmod 644 $SRC_DISK" >&2
      exit 4
    }
  else
    echo "Cannot fix permissions automatically. Please run:" >&2
    echo "  sudo chmod 644 $SRC_DISK" >&2
    exit 4
  fi
fi

# Create the qcow2 image with backing file
# Ensure the target directory exists and is writable
TARGET_DIR=$(dirname "$NEW_DISK")
if [[ ! -d "$TARGET_DIR" ]]; then
  mkdir -p "$TARGET_DIR" || {
    echo "Failed to create target directory: $TARGET_DIR" >&2
    exit 4
  }
fi

# Check if we can write to the target directory
# If not, we'll need to use sudo
NEED_SUDO=false
if [[ ! -w "$TARGET_DIR" ]]; then
  if command -v sudo >/dev/null 2>&1; then
    NEED_SUDO=true
    echo "Target directory is not writable, using sudo for disk creation..." >&2
  else
    echo "Cannot write to target directory: $TARGET_DIR" >&2
    echo "And sudo is not available. Please fix permissions or install sudo." >&2
    exit 4
  fi
fi

# Create linked clone images for ALL qcow2 disks
# Use sudo if needed, but preserve user context for file ownership
CURRENT_USER=${SUDO_USER:-$USER}
CURRENT_UID=$(id -u "$CURRENT_USER" 2>/dev/null || echo "")
CURRENT_GID=$(id -g "$CURRENT_USER" 2>/dev/null || echo "")

for i in "${!QCOW2_DISKS[@]}"; do
  TARGET_DEV="${QCOW2_TARGETS[$i]}"
  SRC_DISK_PATH="${QCOW2_DISKS[$i]}"
  NEW_DISK_PATH="${NEW_DISK_PATHS[$TARGET_DEV]}"
  
  # Check if source disk is readable
  if [[ ! -r "$SRC_DISK_PATH" ]]; then
    echo "Warning: Cannot read backing file $SRC_DISK_PATH for $TARGET_DEV (permission denied)" >&2
    if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
      sudo chmod 644 "$SRC_DISK_PATH" 2>/dev/null || {
        echo "Failed to fix permissions for $SRC_DISK_PATH" >&2
        exit 4
      }
    else
      echo "Cannot fix permissions automatically. Please run:" >&2
      echo "  sudo chmod 644 $SRC_DISK_PATH" >&2
      exit 4
    fi
  fi
  
  # Create the linked clone image
  if [[ "$NEED_SUDO" == "true" ]]; then
    QEMU_OUTPUT=$(sudo -u "$CURRENT_USER" qemu-img create -f qcow2 -F qcow2 -b "$SRC_DISK_PATH" "$NEW_DISK_PATH" 2>&1)
    QEMU_EXIT=$?
    
    if [[ $QEMU_EXIT -ne 0 ]]; then
      QEMU_OUTPUT=$(sudo qemu-img create -f qcow2 -F qcow2 -b "$SRC_DISK_PATH" "$NEW_DISK_PATH" 2>&1)
      QEMU_EXIT=$?
      if [[ $QEMU_EXIT -eq 0 && -n "$CURRENT_UID" && -n "$CURRENT_GID" ]]; then
        sudo chown "$CURRENT_UID:$CURRENT_GID" "$NEW_DISK_PATH" 2>/dev/null || true
      fi
    fi
  else
    QEMU_OUTPUT=$(qemu-img create -f qcow2 -F qcow2 -b "$SRC_DISK_PATH" "$NEW_DISK_PATH" 2>&1)
    QEMU_EXIT=$?
  fi
  
  if [[ $QEMU_EXIT -ne 0 ]]; then
    echo "$QEMU_OUTPUT" >&2
    echo "Failed to create qcow2 image for $TARGET_DEV with backing file $SRC_DISK_PATH" >&2
    exit 4
  fi
  
  echo "Created linked clone for $TARGET_DEV: $NEW_DISK_PATH" >&2
done

# Clone the VM definition but point storage at our new linked disk
# --preserve-data tells virt-clone to keep our pre-created disk intact.
# --file specifies the path for the first disk (virt-clone will try to clone all disks)
# We'll handle additional disks by removing them after cloning if virt-clone fails
FIRST_TARGET="${QCOW2_TARGETS[0]:-vda}"

# Build virt-clone command
VIRT_CLONE_CMD=()
if [[ -n "${CONN_URI:-}" ]]; then
  VIRT_CLONE_CMD+=(--connect "$CONN_URI")
fi
# Use --file without device specification - it replaces the first disk
VIRT_CLONE_CMD+=(--original "$SRC" --name "$NEW" --file "$NEW_DISK" --preserve-data)

# Run virt-clone - it may fail if there are additional devices without source info
# In that case, we'll handle it by removing those devices after cloning
VIRT_CLONE_OUTPUT=""
VIRT_CLONE_EXIT=0

if [[ -n "${CONN_URI:-}" ]]; then
  VIRT_CLONE_OUTPUT=$(virt-clone "${VIRT_CLONE_CMD[@]}" 2>&1) || VIRT_CLONE_EXIT=$?
else
  VIRT_CLONE_OUTPUT=$(virt-clone "${VIRT_CLONE_CMD[@]}" 2>&1) || VIRT_CLONE_EXIT=$?
fi

# Check if virt-clone failed due to missing source information for additional devices
if [[ $VIRT_CLONE_EXIT -ne 0 ]]; then
  if echo "$VIRT_CLONE_OUTPUT" | grep -q "missing source information"; then
    echo "Warning: virt-clone failed due to additional devices. Creating VM manually..." >&2
    
    # virt-clone failed because it can't handle multiple disks without source info
    # We'll manually create the VM by cloning the XML and editing it
    TEMP_XML=$(mktemp)
    
    # Dump the source VM XML
    if [[ -n "${CONN_URI:-}" ]]; then
      virsh -c "$CONN_URI" dumpxml "$SRC" > "$TEMP_XML" 2>/dev/null || {
        echo "Failed to dump XML from source VM." >&2
        rm -f "$TEMP_XML"
        exit 5
      }
    else
      virsh dumpxml "$SRC" > "$TEMP_XML" 2>/dev/null || {
        echo "Failed to dump XML from source VM." >&2
        rm -f "$TEMP_XML"
        exit 5
      }
    fi
    
    # Edit the XML: change name, UUID, and remove additional disks
    # Use sed to:
    # 1. Change the VM name
    # 2. Remove UUID (let libvirt generate a new one)
    # 3. Remove all disk devices except the first one (vda)
    # 4. Update the first disk source to point to our new linked disk
    
    # Create a temporary edited XML
    TEMP_XML_EDITED=$(mktemp)
    
    # Change VM name
    sed "s|<name>${SRC}</name>|<name>${NEW}</name>|g" "$TEMP_XML" > "$TEMP_XML_EDITED"
    
    # Remove UUID (let libvirt generate new one)
    sed -i '/<uuid>/d' "$TEMP_XML_EDITED"
    
    # Remove MAC addresses from interfaces (let libvirt generate new ones)
    sed -i 's/<mac address="[^"]*"\/>/<mac address=""/g' "$TEMP_XML_EDITED"
    sed -i 's/<mac address="[^"]*">/<mac address="">/g' "$TEMP_XML_EDITED"
    
    # Use Python to properly edit the disk section
    # Update all qcow2 disks to point to their new linked clone files, remove non-qcow2 disks
    # Build the disk mapping string to pass to Python
    DISK_MAPPING_STR=""
    for target_dev in "${QCOW2_TARGETS[@]}"; do
      DISK_MAPPING_STR="${DISK_MAPPING_STR}${target_dev}:${NEW_DISK_PATHS[$target_dev]};"
    done
    
    python3 << PYTHON_SCRIPT
import sys
import xml.etree.ElementTree as ET

# Parse disk mapping from bash
disk_mapping_str = "${DISK_MAPPING_STR}"
new_disk_paths = {}
if disk_mapping_str:
    for mapping in disk_mapping_str.rstrip(';').split(';'):
        if ':' in mapping:
            target_dev, disk_path = mapping.split(':', 1)
            new_disk_paths[target_dev] = disk_path

try:
    tree = ET.parse("$TEMP_XML_EDITED")
    root = tree.getroot()
    
    # Find all disk devices
    devices = root.find('.//devices')
    if devices is not None:
        disks = devices.findall('disk')
        disks_to_remove = []
        
        for disk in disks:
            target = disk.find('target')
            if target is not None:
                target_dev = target.get('dev', '')
                
                # Check if this is a qcow2 disk we're cloning
                if target_dev in new_disk_paths:
                    # Update the source file for this disk
                    source = disk.find('source')
                    if source is not None:
                        source.set('file', new_disk_paths[target_dev])
                else:
                    # Remove non-qcow2 disks (CD-ROMs, etc.) or disks we're not cloning
                    disks_to_remove.append(disk)
        
        # Remove disks that shouldn't be cloned
        for disk in disks_to_remove:
            devices.remove(disk)
    
    # Write the modified XML
    tree.write("$TEMP_XML_EDITED", encoding='unicode', xml_declaration=True)
    sys.exit(0)
except Exception as e:
    print(f"Error editing XML: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON_SCRIPT
    
    if [[ $? -ne 0 ]]; then
      echo "Failed to edit VM XML." >&2
      rm -f "$TEMP_XML" "$TEMP_XML_EDITED"
      exit 5
    fi
    
    # Define the new VM from the edited XML
    if [[ -n "${CONN_URI:-}" ]]; then
      virsh -c "$CONN_URI" define "$TEMP_XML_EDITED" >/dev/null 2>&1 || {
        echo "Failed to define new VM from XML." >&2
        rm -f "$TEMP_XML" "$TEMP_XML_EDITED"
        exit 5
      }
    else
      virsh define "$TEMP_XML_EDITED" >/dev/null 2>&1 || {
        echo "Failed to define new VM from XML." >&2
        rm -f "$TEMP_XML" "$TEMP_XML_EDITED"
        exit 5
      }
    fi
    
    # Clean up temp files
    rm -f "$TEMP_XML" "$TEMP_XML_EDITED"
    
    echo "Successfully created VM manually by editing XML." >&2
  else
    # Different error - show it and exit
    echo "$VIRT_CLONE_OUTPUT" >&2
    echo "Failed to create linked clone." >&2
    exit 5
  fi
else
  # virt-clone succeeded, but we should still clean up any additional devices
  # that might have been cloned but we don't want
  if [[ ${#QCOW2_TARGETS[@]} -gt 1 ]] || [[ ${#OTHER_DEVICES[@]} -gt 0 ]]; then
    echo "Removing additional block devices that were not intended to be cloned..." >&2
    # Remove additional qcow2 disks
    for target in "${QCOW2_TARGETS[@]:1}"; do
      if [[ -n "${CONN_URI:-}" ]]; then
        virsh -c "$CONN_URI" detach-disk --domain "$NEW" --target "$target" --persistent 2>/dev/null || true
      else
        virsh detach-disk --domain "$NEW" --target "$target" --persistent 2>/dev/null || true
      fi
    done
    # Remove non-qcow2 devices
    for target in "${OTHER_DEVICES[@]}"; do
      if [[ -n "${CONN_URI:-}" ]]; then
        virsh -c "$CONN_URI" detach-disk --domain "$NEW" --target "$target" --persistent 2>/dev/null || true
      else
        virsh detach-disk --domain "$NEW" --target "$target" --persistent 2>/dev/null || true
      fi
    done
  fi
fi

# Ensure SELinux context (Fedora)
command -v restorecon >/dev/null 2>&1 && restorecon -Rv "$(dirname "$NEW_DISK")" >/dev/null 2>&1 || true

echo "Linked clone '$NEW' created at $NEW_DISK"
