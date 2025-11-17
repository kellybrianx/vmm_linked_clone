#!/usr/bin/env python3
"""
FastAPI script for managing VMs via virsh commands.
Provides REST API endpoints for common lab management tasks.
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="vmm-lab-manager",
    description="Managing VMs so you don't have to pretend you enjoy virsh.",
    version="1.0.0"
)


class VMInfo(BaseModel):
    """VM information model"""
    name: str
    state: str
    id: Optional[int] = None
    uuid: Optional[str] = None


class VMStatus(BaseModel):
    """VM status response model"""
    name: str
    state: str
    id: Optional[int] = None
    uuid: Optional[str] = None
    max_memory: Optional[str] = None
    memory: Optional[str] = None
    vcpu: Optional[int] = None
    cpu_time: Optional[str] = None


class OperationResponse(BaseModel):
    """Generic operation response model"""
    success: bool
    message: str
    vm_name: Optional[str] = None


class LinkedCloneRequest(BaseModel):
    """Request model for creating a linked clone"""
    new_vm_name: str = Field(..., example="")
    disk_target: Optional[str] = Field(None, example="")
    connection_uri: Optional[str] = Field(None, example="")


class LinkedCloneResponse(BaseModel):
    """Response model for linked clone creation"""
    success: bool
    message: str
    source_vm: str
    new_vm_name: str
    disk_path: Optional[str] = None


class VMInterface(BaseModel):
    """VM network interface information"""
    name: str
    mac_address: Optional[str] = None
    protocol: Optional[str] = None
    address: Optional[str] = None


class VMIPResponse(BaseModel):
    """Response model for VM IP address"""
    vm_name: str
    interfaces: List[VMInterface]


class VMWithIP(BaseModel):
    """VM information with IP addresses"""
    name: str
    state: str
    id: Optional[int] = None
    uuid: Optional[str] = None
    interfaces: List[VMInterface] = []


class VMsWithIPsResponse(BaseModel):
    """Response model for listing VMs with IP addresses"""
    count: int
    vms: List[VMWithIP]


class VMDisk(BaseModel):
    """VM disk information"""
    target: str
    source: Optional[str] = None


class VMDisksResponse(BaseModel):
    """Response model for VM disk locations"""
    vm_name: str
    disks: List[VMDisk]


def run_virsh_command(
    command: List[str],
    connection_uri: Optional[str] = None,
    timeout: int = 30,
    use_sudo: bool = False
) -> tuple[str, int]:
    """
    Execute a virsh command and return stdout and return code.
    
    Args:
        command: List of command arguments (e.g., ['list', '--all'])
        connection_uri: Optional libvirt connection URI
        timeout: Command timeout in seconds
        use_sudo: Whether to run the command with sudo
    
    Returns:
        Tuple of (stdout, return_code)
    """
    cmd = ['sudo', 'virsh'] if use_sudo else ['virsh']
    if connection_uri:
        cmd.extend(['-c', connection_uri])
    cmd.extend(command)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        # For error cases, combine stdout and stderr for better error messages
        # For success cases, stdout should be clean for parsing
        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr.strip():
            # Include stderr in error output
            output = f"{output}\n{result.stderr.strip()}" if output else result.stderr.strip()
        return output, result.returncode
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail=f"Command timed out after {timeout} seconds"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error executing virsh command: {str(e)}"
        )


def parse_domifaddr_output(output: str) -> List[VMInterface]:
    """
    Parse 'virsh domifaddr' output into VMInterface objects.
    
    Args:
        output: Output from 'virsh domifaddr <vm_name>'
    
    Returns:
        List of VMInterface objects
    """
    interfaces = []
    lines = output.split('\n')
    
    # Skip header lines (usually 2 lines: title and separator)
    for line in lines[2:]:
        if not line.strip():
            continue
        
        # Split by whitespace, but handle multiple spaces
        parts = line.split()
        if len(parts) < 2:
            continue
        
        # Format: Name MAC Protocol Address
        # Example: vnet0 52:54:00:12:34:56 ipv4 192.168.122.100/24
        name = parts[0] if len(parts) > 0 else ""
        mac = parts[1] if len(parts) > 1 else None
        protocol = parts[2] if len(parts) > 2 else None
        address = parts[3] if len(parts) > 3 else None
        
        if name:
            interfaces.append(VMInterface(
                name=name,
                mac_address=mac,
                protocol=protocol,
                address=address
            ))
    
    return interfaces


def get_vm_interfaces_via_guest_agent(
    vm_name: str,
    connection_uri: Optional[str] = None
) -> List[VMInterface]:
    """
    Get VM network interfaces with IP addresses using QEMU guest agent.
    
    This is a fallback method when 'virsh domifaddr' doesn't return results.
    The guest agent provides more reliable IP address information.
    
    Args:
        vm_name: Name of the VM
        connection_uri: Optional libvirt connection URI
    
    Returns:
        List of VMInterface objects with IP addresses
    """
    interfaces = []
    
    # Build the qemu-agent-command
    cmd = ['virsh']
    if connection_uri:
        cmd.extend(['-c', connection_uri])
    cmd.extend(['qemu-agent-command', vm_name, '{"execute":"guest-network-get-interfaces"}'])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        
        if result.returncode != 0:
            return interfaces
        
        # Parse JSON response
        data = json.loads(result.stdout)
        
        if 'return' in data and isinstance(data['return'], list):
            for iface in data['return']:
                # Skip loopback interface
                if iface.get('name') == 'lo':
                    continue
                
                # Get MAC address
                mac = iface.get('hardware-address')
                
                # Get IP addresses
                ip_addresses = iface.get('ip-addresses', [])
                for ip_info in ip_addresses:
                    ip_type = ip_info.get('ip-address-type', '')
                    ip_addr = ip_info.get('ip-address', '')
                    prefix = ip_info.get('prefix', '')
                    
                    # Format address with prefix (e.g., 192.168.1.201/24)
                    if ip_addr and prefix:
                        formatted_addr = f"{ip_addr}/{prefix}"
                    else:
                        formatted_addr = ip_addr
                    
                    # Map guest interface name to host vnet name if possible
                    # We'll use the guest interface name, but could map via MAC
                    interface_name = iface.get('name', 'unknown')
                    
                    interfaces.append(VMInterface(
                        name=interface_name,
                        mac_address=mac,
                        protocol=ip_type,
                        address=formatted_addr
                    ))
    except (json.JSONDecodeError, KeyError, Exception):
        # If parsing fails, return empty list
        pass
    
    return interfaces


def parse_vm_list(output: str) -> List[VMInfo]:
    """
    Parse 'virsh list --all' output into VMInfo objects.
    
    Args:
        output: Output from 'virsh list --all'
    
    Returns:
        List of VMInfo objects
    """
    vms = []
    lines = output.split('\n')
    
    # Skip header lines (usually 2 lines)
    for line in lines[2:]:
        if not line.strip():
            continue
        
        parts = line.split()
        if len(parts) < 2:
            continue
        
        vm_id = parts[0] if parts[0].isdigit() else None
        name = parts[1] if len(parts) > 1 else ""
        state = parts[2] if len(parts) > 2 else "unknown"
        
        if name:
            vms.append(VMInfo(
                name=name,
                state=state,
                id=int(vm_id) if vm_id else None
            ))
    
    return vms


def parse_domblklist_output(output: str) -> List[VMDisk]:
    """
    Parse 'virsh domblklist' output into VMDisk objects.
    
    Args:
        output: Output from 'virsh domblklist <vm_name>'
    
    Returns:
        List of VMDisk objects
    """
    disks = []
    lines = output.split('\n')
    
    # Skip header lines (usually 2 lines: title and separator)
    for line in lines[2:]:
        if not line.strip():
            continue
        
        # Split by whitespace, but handle multiple spaces
        parts = line.split()
        if len(parts) < 1:
            continue
        
        # Format: Target Source
        # Example: vda /path/to/disk.qcow2
        # Example: hda - (for empty CD-ROM)
        target = parts[0] if len(parts) > 0 else ""
        source = parts[1] if len(parts) > 1 and parts[1] != '-' else None
        
        if target:
            disks.append(VMDisk(
                target=target,
                source=source
            ))
    
    return disks


def find_linked_clone_script() -> str:
    """
    Find the vmm_linked_clone.sh script.
    Checks current directory, script directory, and /usr/local/bin.
    
    Returns:
        Path to the script
    
    Raises:
        HTTPException: If script is not found
    """
    # Possible locations
    script_name = "vmm_linked_clone.sh"
    possible_paths = [
        # Same directory as this script
        Path(__file__).parent / script_name,
        # Current working directory
        Path.cwd() / script_name,
        # Standard installation location
        Path("/usr/local/bin") / script_name,
        # Absolute path if in same directory
        Path(os.path.dirname(os.path.abspath(__file__))) / script_name,
    ]
    
    for path in possible_paths:
        if path.exists() and path.is_file() and os.access(path, os.X_OK):
            return str(path)
    
    raise HTTPException(
        status_code=500,
        detail=f"Linked clone script not found. Searched: {[str(p) for p in possible_paths]}"
    )


@app.get("/", tags=["General"])
async def root():
    """API root endpoint"""
    return {
        "message": "Virsh Lab Manager API",
        "version": "1.0.0",
        "endpoints": {
            "list_vms": "/api/v1/vms",
            "list_vms_with_ips": "/api/v1/vms/ips",
            "vm_status": "/api/v1/vms/{vm_name}/status",
            "power_on": "/api/v1/vms/{vm_name}/start",
            "power_off": "/api/v1/vms/{vm_name}/shutdown",
            "force_off": "/api/v1/vms/{vm_name}/destroy",
            "reboot": "/api/v1/vms/{vm_name}/reboot",
            "pause": "/api/v1/vms/{vm_name}/pause",
            "resume": "/api/v1/vms/{vm_name}/resume",
            "linked_clone": "/api/v1/vms/{vm_name}/linked-clone",
            "delete": "/api/v1/vms/{vm_name}/delete",
            "ip_address": "/api/v1/vms/{vm_name}/ip",
            "disks": "/api/v1/vms/{vm_name}/disks"
        }
    }


@app.get("/api/v1/vms", tags=["VM Management"])
async def list_vms(
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI"),
    state: Optional[str] = Query(None, description="Filter by state (running, shut, etc.)")
):
    """
    List all virtual machines.
    
    Returns a list of all VMs with their current state.
    """
    stdout, returncode = run_virsh_command(['list', '--all'], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list VMs: {stdout}"
        )
    
    vms = parse_vm_list(stdout)
    
    # Filter by state if requested
    if state:
        vms = [vm for vm in vms if vm.state.lower() == state.lower()]
    
    return {
        "count": len(vms),
        "vms": [vm.dict() for vm in vms]
    }


@app.get("/api/v1/vms/ips", tags=["VM Management"], response_model=VMsWithIPsResponse)
async def list_vms_with_ips(
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI"),
    state: Optional[str] = Query(None, description="Filter by state (running, shut, etc.)")
):
    """
    List all virtual machines with their IP addresses.
    
    Returns a list of all VMs with their current state and network interface information.
    VMs that are not running will have empty interfaces lists.
    """
    # Get all VMs
    stdout, returncode = run_virsh_command(['list', '--all'], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list VMs: {stdout}"
        )
    
    vms = parse_vm_list(stdout)
    
    # Filter by state if requested
    if state:
        vms = [vm for vm in vms if vm.state.lower() == state.lower()]
    
    # Get IP addresses for each VM
    vms_with_ips = []
    for vm in vms:
        interfaces = []
        
        # Only try to get IP addresses if VM is running
        # Check if state indicates running (case-insensitive)
        if vm.state.lower() in ['running', 'idle', 'paused']:
            try:
                stdout, returncode = run_virsh_command(
                    ['domifaddr', vm.name],
                    connection_uri,
                    use_sudo=True
                )
                
                if returncode == 0:
                    interfaces = parse_domifaddr_output(stdout)
                
                # If no interfaces found via domifaddr, try guest agent as fallback
                if not interfaces:
                    try:
                        interfaces = get_vm_interfaces_via_guest_agent(vm.name, connection_uri)
                    except Exception:
                        # If guest agent also fails, continue with empty interfaces
                        pass
            except HTTPException:
                # If getting IP fails, try guest agent as fallback
                try:
                    interfaces = get_vm_interfaces_via_guest_agent(vm.name, connection_uri)
                except Exception:
                    pass
            except Exception:
                # Any other error, try guest agent as fallback
                try:
                    interfaces = get_vm_interfaces_via_guest_agent(vm.name, connection_uri)
                except Exception:
                    pass
        
        # Get UUID if available
        uuid = None
        try:
            stdout, returncode = run_virsh_command(['domuuid', vm.name], connection_uri)
            if returncode == 0:
                uuid = stdout.strip()
        except Exception:
            pass
        
        vms_with_ips.append(VMWithIP(
            name=vm.name,
            state=vm.state,
            id=vm.id,
            uuid=uuid,
            interfaces=interfaces
        ))
    
    return {
        "count": len(vms_with_ips),
        "vms": [vm.dict() for vm in vms_with_ips]
    }


@app.get("/api/v1/vms/{vm_name}/status", tags=["VM Management"])
async def get_vm_status(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Get detailed status information for a specific VM.
    """
    stdout, returncode = run_virsh_command(['dominfo', vm_name], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=404,
            detail=f"VM '{vm_name}' not found or error: {stdout}"
        )
    
    # Parse dominfo output
    info = {}
    for line in stdout.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower().replace(' ', '_')
            value = value.strip()
            info[key] = value
    
    # Helper function to safely parse integer values
    def safe_int(value: Optional[str]) -> Optional[int]:
        """Safely convert string to int, handling '-', '-1', and empty values"""
        if not value or value in ('-', '-1', ''):
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    # Extract key fields
    status = VMStatus(
        name=info.get('name', vm_name),
        state=info.get('state', 'unknown'),
        id=safe_int(info.get('id')),
        uuid=info.get('uuid'),
        max_memory=info.get('max_memory'),
        memory=info.get('used_memory'),
        vcpu=safe_int(info.get('cpu(s)')),
        cpu_time=info.get('cpu_time')
    )
    
    return status.dict()


@app.post("/api/v1/vms/{vm_name}/start", tags=["VM Management"])
async def power_on(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Power on (start) a virtual machine.
    """
    stdout, returncode = run_virsh_command(['start', vm_name], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start VM '{vm_name}': {stdout}"
        )
    
    return OperationResponse(
        success=True,
        message=f"VM '{vm_name}' started successfully",
        vm_name=vm_name
    ).dict()


@app.post("/api/v1/vms/{vm_name}/shutdown", tags=["VM Management"])
async def power_off(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Power off (graceful shutdown) a virtual machine.
    """
    stdout, returncode = run_virsh_command(['shutdown', vm_name], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to shutdown VM '{vm_name}': {stdout}"
        )
    
    return OperationResponse(
        success=True,
        message=f"VM '{vm_name}' shutdown initiated",
        vm_name=vm_name
    ).dict()


@app.post("/api/v1/vms/{vm_name}/destroy", tags=["VM Management"])
async def force_off(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Force power off (destroy) a virtual machine.
    WARNING: This is equivalent to pulling the power plug.
    """
    stdout, returncode = run_virsh_command(['destroy', vm_name], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to destroy VM '{vm_name}': {stdout}"
        )
    
    return OperationResponse(
        success=True,
        message=f"VM '{vm_name}' forcefully stopped",
        vm_name=vm_name
    ).dict()


@app.post("/api/v1/vms/{vm_name}/reboot", tags=["VM Management"])
async def reboot(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Reboot a virtual machine (graceful restart).
    """
    stdout, returncode = run_virsh_command(['reboot', vm_name], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reboot VM '{vm_name}': {stdout}"
        )
    
    return OperationResponse(
        success=True,
        message=f"VM '{vm_name}' reboot initiated",
        vm_name=vm_name
    ).dict()


@app.post("/api/v1/vms/{vm_name}/pause", tags=["VM Management"])
async def pause(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Pause (suspend) a virtual machine.
    """
    stdout, returncode = run_virsh_command(['suspend', vm_name], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to pause VM '{vm_name}': {stdout}"
        )
    
    return OperationResponse(
        success=True,
        message=f"VM '{vm_name}' paused",
        vm_name=vm_name
    ).dict()


@app.post("/api/v1/vms/{vm_name}/resume", tags=["VM Management"])
async def resume(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Resume a paused virtual machine.
    """
    stdout, returncode = run_virsh_command(['resume', vm_name], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resume VM '{vm_name}': {stdout}"
        )
    
    return OperationResponse(
        success=True,
        message=f"VM '{vm_name}' resumed",
        vm_name=vm_name
    ).dict()


@app.get("/api/v1/vms/{vm_name}/console", tags=["VM Management"])
async def get_console_info(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Get console information for a VM.
    """
    stdout, returncode = run_virsh_command(['domdisplay', vm_name], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=404,
            detail=f"Failed to get console info for VM '{vm_name}': {stdout}"
        )
    
    return {
        "vm_name": vm_name,
        "console": stdout.strip()
    }


@app.post("/api/v1/vms/{vm_name}/linked-clone", tags=["VM Management"])
async def create_linked_clone(
    vm_name: str,
    request: LinkedCloneRequest = Body(...)
):
    """
    Create a linked clone of a virtual machine.
    
    This endpoint uses the vmm_linked_clone.sh script to create a space-efficient
    linked clone that shares the base disk image with the source VM.
    
    Args:
        vm_name: Name of the source VM to clone
        request: LinkedCloneRequest containing:
            - new_vm_name: Name for the new linked clone VM
            - disk_target: Optional target directory for the new disk (defaults to source disk directory)
            - connection_uri: Optional libvirt connection URI
    
    Returns:
        LinkedCloneResponse with operation details
    """
    # Find the linked clone script
    script_path = find_linked_clone_script()
    
    # Build command arguments
    # Script signature: vmm_linked_clone.sh <SOURCE_VM> <NEW_VM_NAME> [<DISK_TARGET>] [<CONNECTION_URI>]
    cmd = [script_path, vm_name, request.new_vm_name]
    
    # Add optional disk_target if provided (including empty string)
    # Empty string means use source disk directory, None means omit the argument
    if request.disk_target is not None:
        cmd.append(request.disk_target)
    
    # Add optional connection_uri if provided
    # If connection_uri is provided but disk_target is None, we need to add empty string for disk_target
    if request.connection_uri:
        if request.disk_target is None:
            cmd.append("")  # Empty disk_target to maintain positional order
        cmd.append(request.connection_uri)
    
    try:
        # Run the script with extended timeout (cloning can take time)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            check=False
        )
        
        if result.returncode != 0:
            # Build comprehensive error message
            error_parts = []
            
            # Add exit code with explanation
            if result.returncode == 141:
                error_parts.append("Exit code 141 (SIGPIPE - process terminated due to broken pipe)")
                error_parts.append("This usually indicates:")
                error_parts.append("  - A command in the script tried to write to a closed pipe")
                error_parts.append("  - Disk space issues or permission problems")
                error_parts.append("  - The script was interrupted")
            else:
                error_parts.append(f"Exit code {result.returncode}")
            
            # Add stderr if available
            if result.stderr.strip():
                error_parts.append(f"\nError output:\n{result.stderr.strip()}")
            
            # Add stdout if available (might contain useful info even on error)
            if result.stdout.strip():
                error_parts.append(f"\nOutput:\n{result.stdout.strip()}")
            
            error_msg = "\n".join(error_parts)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create linked clone: {error_msg}"
            )
        
        # Parse output to extract disk path if available
        disk_path = None
        output_lines = result.stdout.split('\n')
        for line in output_lines:
            if 'created at' in line.lower() or '.qcow2' in line:
                # Try to extract disk path
                parts = line.split()
                for part in parts:
                    if part.endswith('.qcow2'):
                        disk_path = part
                        break
        
        return LinkedCloneResponse(
            success=True,
            message=f"Linked clone '{request.new_vm_name}' created successfully from '{vm_name}'",
            source_vm=vm_name,
            new_vm_name=request.new_vm_name,
            disk_path=disk_path
        ).dict()
        
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="Linked clone operation timed out after 5 minutes"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error creating linked clone: {str(e)}"
        )


@app.get("/api/v1/vms/{vm_name}/ip", tags=["VM Management"])
async def get_vm_ip(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Get IP address(es) for a virtual machine's network interfaces.
    
    This endpoint uses 'sudo virsh domifaddr' to retrieve IP addresses
    assigned to the VM's network interfaces.
    
    Args:
        vm_name: Name of the VM
        connection_uri: Optional libvirt connection URI
    
    Returns:
        VMIPResponse with interface information including IP addresses
    """
    stdout, returncode = run_virsh_command(
        ['domifaddr', vm_name],
        connection_uri,
        use_sudo=True
    )
    
    if returncode != 0:
        # Check if VM doesn't exist
        if 'not found' in stdout.lower() or 'no domain' in stdout.lower():
            raise HTTPException(
                status_code=404,
                detail=f"VM '{vm_name}' not found: {stdout}"
            )
        # Check if VM is not running (domifaddr requires running VM)
        if 'not running' in stdout.lower() or 'shut off' in stdout.lower():
            raise HTTPException(
                status_code=400,
                detail=f"VM '{vm_name}' is not running. IP addresses are only available for running VMs."
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get IP address for VM '{vm_name}': {stdout}"
        )
    
    # Parse the output
    interfaces = parse_domifaddr_output(stdout)
    
    # If no interfaces found via domifaddr, try guest agent as fallback
    if not interfaces:
        try:
            interfaces = get_vm_interfaces_via_guest_agent(vm_name, connection_uri)
        except Exception:
            # If guest agent also fails, continue with empty list
            pass
    
    # If still no interfaces found, return empty list
    if not interfaces:
        # Check if output indicates no addresses
        if 'no ip address' in stdout.lower() or 'no interface' in stdout.lower():
            return VMIPResponse(
                vm_name=vm_name,
                interfaces=[]
            ).dict()
    
    return VMIPResponse(
        vm_name=vm_name,
        interfaces=interfaces
    ).dict()


@app.get("/api/v1/vms/{vm_name}/disks", tags=["VM Management"], response_model=VMDisksResponse)
async def get_vm_disks(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Get disk locations (qcow2 files) for a virtual machine.
    
    This endpoint uses 'virsh domblklist' to retrieve the disk block devices
    and their source paths for the VM.
    
    Args:
        vm_name: Name of the VM
        connection_uri: Optional libvirt connection URI
    
    Returns:
        VMDisksResponse with disk information including qcow2 file paths
    """
    stdout, returncode = run_virsh_command(
        ['domblklist', vm_name],
        connection_uri
    )
    
    if returncode != 0:
        # Check if VM doesn't exist
        if 'not found' in stdout.lower() or 'no domain' in stdout.lower():
            raise HTTPException(
                status_code=404,
                detail=f"VM '{vm_name}' not found: {stdout}"
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get disk information for VM '{vm_name}': {stdout}"
        )
    
    # Parse the output
    disks = parse_domblklist_output(stdout)
    
    return VMDisksResponse(
        vm_name=vm_name,
        disks=disks
    ).dict()


@app.delete("/api/v1/vms/{vm_name}/delete", tags=["VM Management"])
async def delete_vm(
    vm_name: str,
    connection_uri: Optional[str] = Query(None, description="Libvirt connection URI")
):
    """
    Delete a virtual machine and all its storage.
    
    This endpoint permanently removes a VM and all associated storage files.
    WARNING: This operation is irreversible and will delete all disk images.
    
    The operation:
    1. First destroys the VM if it's running (force stop)
    2. Then undefines the VM and removes all storage using 'virsh undefine --remove-all-storage'
    
    Args:
        vm_name: Name of the VM to delete
        connection_uri: Optional libvirt connection URI
    
    Returns:
        OperationResponse with deletion status
    """
    # First, check if VM exists and get its state
    stdout, returncode = run_virsh_command(['dominfo', vm_name], connection_uri)
    
    if returncode != 0:
        raise HTTPException(
            status_code=404,
            detail=f"VM '{vm_name}' not found: {stdout}"
        )
    
    # Check if VM is running - if so, destroy it first
    # Parse the state from dominfo output
    vm_state = None
    for line in stdout.split('\n'):
        if 'State:' in line:
            vm_state = line.split(':', 1)[1].strip().lower()
            break
    
    # If VM is running, destroy it first
    if vm_state and 'running' in vm_state:
        destroy_stdout, destroy_returncode = run_virsh_command(['destroy', vm_name], connection_uri)
        if destroy_returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to stop running VM '{vm_name}': {destroy_stdout}"
            )
    
    # Now undefine the VM and remove all storage
    stdout, returncode = run_virsh_command(
        ['undefine', '--domain', vm_name, '--remove-all-storage'],
        connection_uri,
        timeout=60  # Longer timeout for storage deletion
    )
    
    if returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete VM '{vm_name}' and its storage: {stdout}"
        )
    
    return OperationResponse(
        success=True,
        message=f"VM '{vm_name}' and all its storage have been permanently deleted",
        vm_name=vm_name
    ).dict()


if __name__ == "__main__":
    import uvicorn
    import os
    # Allow port to be overridden via environment variable, default to 9393
    port = int(os.getenv("VIRSH_API_PORT", "9393"))
    uvicorn.run(app, host="0.0.0.0", port=port)

