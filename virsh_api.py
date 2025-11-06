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
from pydantic import BaseModel

app = FastAPI(
    title="Virsh Lab Manager API",
    description="REST API for managing virtual machines via virsh commands",
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
    new_vm_name: str
    disk_target: Optional[str] = None
    connection_uri: Optional[str] = None


class LinkedCloneResponse(BaseModel):
    """Response model for linked clone creation"""
    success: bool
    message: str
    source_vm: str
    new_vm_name: str
    disk_path: Optional[str] = None


def run_virsh_command(
    command: List[str],
    connection_uri: Optional[str] = None,
    timeout: int = 30
) -> tuple[str, int]:
    """
    Execute a virsh command and return stdout and return code.
    
    Args:
        command: List of command arguments (e.g., ['list', '--all'])
        connection_uri: Optional libvirt connection URI
        timeout: Command timeout in seconds
    
    Returns:
        Tuple of (stdout, return_code)
    """
    cmd = ['virsh']
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
        return result.stdout.strip(), result.returncode
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
            "vm_status": "/api/v1/vms/{vm_name}/status",
            "power_on": "/api/v1/vms/{vm_name}/start",
            "power_off": "/api/v1/vms/{vm_name}/shutdown",
            "force_off": "/api/v1/vms/{vm_name}/destroy",
            "reboot": "/api/v1/vms/{vm_name}/reboot",
            "pause": "/api/v1/vms/{vm_name}/pause",
            "resume": "/api/v1/vms/{vm_name}/resume",
            "linked_clone": "/api/v1/vms/{vm_name}/linked-clone"
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
    
    # Extract key fields
    status = VMStatus(
        name=info.get('name', vm_name),
        state=info.get('state', 'unknown'),
        id=int(info['id']) if info.get('id', '-1') != '-1' else None,
        uuid=info.get('uuid'),
        max_memory=info.get('max_memory'),
        memory=info.get('used_memory'),
        vcpu=int(info['cpu(s)']) if info.get('cpu(s)') else None,
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
    
    # Add optional disk_target if provided
    if request.disk_target:
        cmd.append(request.disk_target)
    
    # Add optional connection_uri if provided
    # If connection_uri is provided but disk_target is not, we need to add empty string for disk_target
    if request.connection_uri:
        if not request.disk_target:
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
            error_msg = result.stderr.strip() or result.stdout.strip() or f"Exit code {result.returncode}"
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


if __name__ == "__main__":
    import uvicorn
    import os
    # Allow port to be overridden via environment variable, default to 9393
    port = int(os.getenv("VIRSH_API_PORT", "9393"))
    uvicorn.run(app, host="0.0.0.0", port=port)

