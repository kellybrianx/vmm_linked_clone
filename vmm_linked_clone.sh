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
  # Get first qcow2 disk path from the source domain
  SRC_DISK=$(virsh -c "$CONN_URI" domblklist --domain "$SRC" | awk '/qcow2/ {print $2; exit}')
else
  if ! virsh dominfo "$SRC" >/dev/null 2>&1; then
    echo "error: failed to get domain '$SRC'" >&2
    echo "Available domains:" >&2
    virsh list --all --name 2>&1 | sed 's/^/  - /' >&2
    exit 1
  fi
  # Get first qcow2 disk path from the source domain
  SRC_DISK=$(virsh domblklist --domain "$SRC" | awk '/qcow2/ {print $2; exit}')
fi
if [[ -z "${SRC_DISK:-}" ]]; then
  echo "No qcow2 disk found on $SRC (raw/LVM images can’t be linked)" >&2
  exit 3
fi

# New disk path
if [[ -z "${TARGET:-}" ]]; then
  TARGET_DIR=$(dirname "$SRC_DISK")
  NEW_DISK="${TARGET_DIR}/${NEW}.qcow2"
else
  mkdir -p "$TARGET"
  NEW_DISK="${TARGET%/}/${NEW}.qcow2"
fi

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

# Create the image
# Use sudo if needed, but preserve user context for file ownership
if [[ "$NEED_SUDO" == "true" ]]; then
  # Use sudo but ensure file is created with correct ownership
  # Get the current user and group
  CURRENT_USER=${SUDO_USER:-$USER}
  CURRENT_UID=$(id -u "$CURRENT_USER" 2>/dev/null || echo "")
  CURRENT_GID=$(id -g "$CURRENT_USER" 2>/dev/null || echo "")
  
  # Create the image with sudo
  QEMU_OUTPUT=$(sudo -u "$CURRENT_USER" qemu-img create -f qcow2 -F qcow2 -b "$SRC_DISK" "$NEW_DISK" 2>&1)
  QEMU_EXIT=$?
  
  # If that failed (user might not have sudo), try direct sudo
  if [[ $QEMU_EXIT -ne 0 ]]; then
    QEMU_OUTPUT=$(sudo qemu-img create -f qcow2 -F qcow2 -b "$SRC_DISK" "$NEW_DISK" 2>&1)
    QEMU_EXIT=$?
    # Fix ownership if we used direct sudo
    if [[ $QEMU_EXIT -eq 0 && -n "$CURRENT_UID" && -n "$CURRENT_GID" ]]; then
      sudo chown "$CURRENT_UID:$CURRENT_GID" "$NEW_DISK" 2>/dev/null || true
    fi
  fi
else
  QEMU_OUTPUT=$(qemu-img create -f qcow2 -F qcow2 -b "$SRC_DISK" "$NEW_DISK" 2>&1)
  QEMU_EXIT=$?
fi

if [[ $QEMU_EXIT -ne 0 ]]; then
  echo "$QEMU_OUTPUT" >&2
  echo "Failed to create qcow2 image with backing file $SRC_DISK" >&2
  echo "Error details:" >&2
  echo "  Source disk: $SRC_DISK" >&2
  echo "  Target disk: $NEW_DISK" >&2
  echo "  Source readable: $([ -r "$SRC_DISK" ] && echo "yes" || echo "no")" >&2
  echo "  Target dir writable: $([ -w "$TARGET_DIR" ] && echo "yes" || echo "no")" >&2
  echo "" >&2
  echo "This usually means:" >&2
  echo "  1. The backing file is not readable (permission denied)" >&2
  echo "  2. The backing file path is incorrect" >&2
  echo "  3. Cannot write to target directory" >&2
  echo "" >&2
  echo "To fix permission issues, run:" >&2
  echo "  sudo chmod 644 $SRC_DISK" >&2
  exit 4
fi

# If we get here, qemu-img succeeded
echo "$QEMU_OUTPUT" >&1

# Clone the VM definition but point storage at our new linked disk
# --preserve-data tells virt-clone to keep our pre-created disk intact.
if [[ -n "${CONN_URI:-}" ]]; then
  virt-clone --connect "$CONN_URI" --original "$SRC" --name "$NEW" --file "$NEW_DISK" --preserve-data
else
  virt-clone --original "$SRC" --name "$NEW" --file "$NEW_DISK" --preserve-data
fi

# Ensure SELinux context (Fedora)
command -v restorecon >/dev/null 2>&1 && restorecon -Rv "$(dirname "$NEW_DISK")" >/dev/null 2>&1 || true

echo "Linked clone '$NEW' created at $NEW_DISK"
