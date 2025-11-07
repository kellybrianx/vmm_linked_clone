# Installing QEMU Guest Agent

The QEMU guest agent is required for `virsh domifaddr` to retrieve IP addresses from VMs. The VM configuration already has the guest agent channel configured, but the agent service needs to be installed and running inside the guest VM.

## Installation Steps

### For Fedora/RHEL/CentOS (inside the guest VM)

1. **Install the qemu-guest-agent package:**
   ```bash
   sudo dnf install qemu-guest-agent
   # Or for older systems:
   sudo yum install qemu-guest-agent
   ```

2. **Start and enable the service:**
   ```bash
   sudo systemctl start qemu-guest-agent
   sudo systemctl enable qemu-guest-agent
   ```

3. **Verify it's running:**
   ```bash
   sudo systemctl status qemu-guest-agent
   ```

### For Debian/Ubuntu (inside the guest VM)

1. **Install the qemu-guest-agent package:**
   ```bash
   sudo apt-get update
   sudo apt-get install qemu-guest-agent
   ```

2. **Start and enable the service:**
   ```bash
   sudo systemctl start qemu-guest-agent
   sudo systemctl enable qemu-guest-agent
   ```

3. **Verify it's running:**
   ```bash
   sudo systemctl status qemu-guest-agent
   ```

### For openSUSE/SLES (inside the guest VM)

1. **Install the qemu-guest-agent package:**
   ```bash
   sudo zypper install qemu-guest-agent
   ```

2. **Start and enable the service:**
   ```bash
   sudo systemctl start qemu-guest-agent
   sudo systemctl enable qemu-guest-agent
   ```

3. **Verify it's running:**
   ```bash
   sudo systemctl status qemu-guest-agent
   ```

## Verification from Host

After installing and starting the guest agent inside the VM, verify from the host:

```bash
# Check if guest agent is connected
sudo virsh qemu-agent-command jonathanJumpbox '{"execute":"guest-ping"}' 2>&1

# Should return: {"return":{}}

# Try to get IP addresses
sudo virsh domifaddr jonathanJumpbox

# Should now show IP addresses if the VM has network connectivity
```

## Troubleshooting

### Guest agent still shows as disconnected

1. **Check if the channel is properly configured:**
   ```bash
   sudo virsh dumpxml jonathanJumpbox | grep -A 3 "qemu.guest_agent"
   ```
   Should show a channel with `type='unix'` and `name='org.qemu.guest_agent.0'`

2. **Restart the VM** (if the channel was added after VM creation):
   ```bash
   sudo virsh shutdown jonathanJumpbox
   sudo virsh start jonathanJumpbox
   ```

3. **Check guest agent logs inside the VM:**
   ```bash
   # Inside the guest VM:
   sudo journalctl -u qemu-guest-agent -n 50
   ```

### IP addresses still not showing

1. **Ensure the VM has network connectivity** - the guest agent can only report IPs that are actually assigned
2. **Wait a few seconds** after starting the guest agent for it to connect
3. **Check if the VM has IP addresses assigned:**
   ```bash
   # Inside the guest VM:
   ip addr show
   # or
   ifconfig
   ```

## Adding Guest Agent Channel to Existing VMs

If a VM doesn't have the guest agent channel configured, you can add it:

1. **Edit the VM configuration:**
   ```bash
   sudo virsh edit jonathanJumpbox
   ```

2. **Add this XML inside the `<devices>` section:**
   ```xml
   <channel type='unix'>
     <source mode='bind' path='/var/lib/libvirt/qemu/channel/target/domain-jonathanJumpbox/org.qemu.guest_agent.0'/>
     <target type='virtio' name='org.qemu.guest_agent.0'/>
     <address type='virtio-serial' controller='0' bus='0' port='1'/>
   </channel>
   ```

3. **Restart the VM:**
   ```bash
   sudo virsh shutdown jonathanJumpbox
   sudo virsh start jonathanJumpbox
   ```

## Notes

- The guest agent channel is already configured for `jonathanJumpbox` (shows as disconnected)
- You only need to install and start the `qemu-guest-agent` service inside the VM
- The agent must be running inside the guest for `virsh domifaddr` to work
- IP addresses will only appear if the VM has active network interfaces with assigned IPs

