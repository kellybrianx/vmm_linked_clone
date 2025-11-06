%define name vmm-linked-clone
%define version 1.0.0
%define release 1%{?dist}
%define summary Virsh Lab Manager - FastAPI API and virt-manager linked clone extension
%define license GPLv2+

Name:           %{name}
Version:        %{version}
Release:        %{release}
Summary:        %{summary}
License:        %{license}
Group:          Applications/System
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3-fastapi >= 0.104.0
Requires:       python3-uvicorn >= 0.24.0
Requires:       python3-pydantic >= 2.0.0
Requires:       virt-manager
Requires:       libvirt
Requires:       qemu-img
Requires:       virt-clone
Requires:       systemd

%description
Virsh Lab Manager provides:
- FastAPI REST API for managing virtual machines via virsh commands
- Linked clone functionality for virt-manager
- Systemd service for the API server

%prep
%setup -q

%build
# No build step needed for Python scripts

%install
# Install virt-manager manager.py extension
mkdir -p %{buildroot}%{_datadir}/virt-manager/virtManager
install -m 644 manager.py %{buildroot}%{_datadir}/virt-manager/virtManager/manager.py

# Install linked clone script
mkdir -p %{buildroot}%{_bindir}
install -m 755 vmm_linked_clone.sh %{buildroot}%{_bindir}/vmm_linked_clone.sh

# Install FastAPI script
install -m 755 virsh_api.py %{buildroot}%{_bindir}/virsh_api.py

# Install requirements file (for reference)
mkdir -p %{buildroot}%{_datadir}/%{name}
install -m 644 requirements.txt %{buildroot}%{_datadir}/%{name}/requirements.txt

# Install systemd service file
mkdir -p %{buildroot}%{_unitdir}
install -m 644 vmm-linked-clone-api.service %{buildroot}%{_unitdir}/%{name}-api.service

%pre
# Backup original manager.py if it exists and hasn't been backed up
if [ -f %{_datadir}/virt-manager/virtManager/manager.py ] && [ ! -f %{_datadir}/virt-manager/virtManager/manager.py.backup ]; then
    cp %{_datadir}/virt-manager/virtManager/manager.py %{_datadir}/virt-manager/virtManager/manager.py.backup
fi

%post
# Enable and start the systemd service
systemctl daemon-reload
systemctl enable %{name}-api.service
systemctl start %{name}-api.service || true

%preun
# Stop and disable the service before removal
if [ $1 -eq 0 ]; then
    systemctl stop %{name}-api.service || true
    systemctl disable %{name}-api.service || true
fi

%postun
# Reload systemd after removal
systemctl daemon-reload

%files
%defattr(-,root,root,-)
%{_datadir}/virt-manager/virtManager/manager.py
%{_bindir}/vmm_linked_clone.sh
%{_bindir}/virsh_api.py
%{_datadir}/%{name}/requirements.txt
%{_unitdir}/%{name}-api.service

%changelog
* Wed Jan 01 2025 Build System <build@example.com> - 1.0.0-1
- Initial RPM package
- Includes virt-manager linked clone extension
- Includes FastAPI virsh management API
- Includes systemd service for API server

