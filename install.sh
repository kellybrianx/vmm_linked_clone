#!/usr/bin/env bash
#
# Installation script for virt-manager linked clone extension
# This script installs the modified manager.py and vmm_linked_clone.sh
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Installation paths
VMM_MANAGER_DIR="/usr/share/virt-manager/virtManager"
VMM_MANAGER_FILE="${VMM_MANAGER_DIR}/manager.py"
VMM_MANAGER_BACKUP="${VMM_MANAGER_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
SCRIPT_TARGET="/usr/local/bin/vmm_linked_clone.sh"

# Source files
SOURCE_MANAGER="${SCRIPT_DIR}/manager.py"
SOURCE_SCRIPT="${SCRIPT_DIR}/vmm_linked_clone.sh"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: This script must be run as root (use sudo)${NC}" >&2
   exit 1
fi

echo "=========================================="
echo "Virt-Manager Linked Clone Extension"
echo "Installation Script"
echo "=========================================="
echo ""

# Check if source files exist
if [[ ! -f "${SOURCE_MANAGER}" ]]; then
    echo -e "${RED}Error: manager.py not found in ${SCRIPT_DIR}${NC}" >&2
    exit 1
fi

if [[ ! -f "${SOURCE_SCRIPT}" ]]; then
    echo -e "${RED}Error: vmm_linked_clone.sh not found in ${SCRIPT_DIR}${NC}" >&2
    exit 1
fi

# Check if virt-manager is installed
if [[ ! -d "${VMM_MANAGER_DIR}" ]]; then
    echo -e "${RED}Error: virt-manager not found at ${VMM_MANAGER_DIR}${NC}" >&2
    echo "Please install virt-manager first:" >&2
    echo "  Fedora/RHEL: sudo dnf install virt-manager" >&2
    echo "  Ubuntu/Debian: sudo apt-get install virt-manager" >&2
    exit 1
fi

if [[ ! -f "${VMM_MANAGER_FILE}" ]]; then
    echo -e "${RED}Error: ${VMM_MANAGER_FILE} not found${NC}" >&2
    exit 1
fi

# Check if backup already exists
if [[ -f "${VMM_MANAGER_BACKUP}" ]]; then
    echo -e "${YELLOW}Warning: Backup file already exists: ${VMM_MANAGER_BACKUP}${NC}"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Installation steps:"
echo "  1. Backup original manager.py"
echo "  2. Install modified manager.py"
echo "  3. Install vmm_linked_clone.sh"
echo ""

# Step 1: Backup original manager.py
echo -e "${GREEN}[1/3]${NC} Backing up original manager.py..."
if [[ -f "${VMM_MANAGER_FILE}" ]]; then
    cp "${VMM_MANAGER_FILE}" "${VMM_MANAGER_BACKUP}"
    echo "  Backup created: ${VMM_MANAGER_BACKUP}"
else
    echo -e "${RED}Error: Original manager.py not found${NC}" >&2
    exit 1
fi

# Step 2: Install modified manager.py
echo -e "${GREEN}[2/3]${NC} Installing modified manager.py..."
cp "${SOURCE_MANAGER}" "${VMM_MANAGER_FILE}"
chmod 644 "${VMM_MANAGER_FILE}"
echo "  Installed to: ${VMM_MANAGER_FILE}"

# Step 3: Install shell script
echo -e "${GREEN}[3/3]${NC} Installing vmm_linked_clone.sh..."
# Create /usr/local/bin if it doesn't exist
mkdir -p "$(dirname "${SCRIPT_TARGET}")"
cp "${SOURCE_SCRIPT}" "${SCRIPT_TARGET}"
chmod 755 "${SCRIPT_TARGET}"
echo "  Installed to: ${SCRIPT_TARGET}"

# Verify installation
echo ""
echo "Verifying installation..."

if [[ -f "${VMM_MANAGER_FILE}" ]] && [[ -f "${SCRIPT_TARGET}" ]]; then
    echo -e "${GREEN}✓ Installation successful!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Close virt-manager if it's currently running"
    echo "  2. Restart virt-manager to load the changes"
    echo "  3. Right-click on a VM and select 'Create Linked Clone…'"
    echo ""
    echo "Backup location: ${VMM_MANAGER_BACKUP}"
    echo ""
    echo "To uninstall, restore the backup:"
    echo "  sudo mv ${VMM_MANAGER_BACKUP} ${VMM_MANAGER_FILE}"
    echo "  sudo rm ${SCRIPT_TARGET}"
else
    echo -e "${RED}✗ Installation verification failed${NC}" >&2
    exit 1
fi

