NAME := vmm-linked-clone
VERSION := 1.0.0
RELEASE := 1
DIST := $(shell rpm --eval '%{?dist}' 2>/dev/null || echo "")

# RPM build directories
RPMBUILD_DIR := $(HOME)/rpmbuild
SOURCES_DIR := $(RPMBUILD_DIR)/SOURCES
SPECS_DIR := $(RPMBUILD_DIR)/SPECS
BUILD_DIR := $(RPMBUILD_DIR)/BUILD
RPMS_DIR := $(RPMBUILD_DIR)/RPMS
SRPMS_DIR := $(RPMBUILD_DIR)/SRPMS

# Source files
SOURCE_TARBALL := $(NAME)-$(VERSION).tar.gz

.PHONY: all clean build prep rpm srpm install-deps

all: rpm

prep:
	@echo "Preparing RPM build environment..."
	@mkdir -p $(SOURCES_DIR) $(SPECS_DIR) $(BUILD_DIR) $(RPMS_DIR) $(SRPMS_DIR)
	@echo "Creating source tarball..."
	@tar -czf $(SOURCES_DIR)/$(SOURCE_TARBALL) \
		--transform="s,^,$(NAME)-$(VERSION)/," \
		manager.py \
		vmm_linked_clone.sh \
		virsh_api.py \
		requirements.txt \
		vmm-linked-clone-api.service \
		README.md
	@echo "Copying spec file..."
	@cp vmm-linked-clone.spec $(SPECS_DIR)/
	@echo "Copying systemd service file..."
	@cp vmm-linked-clone-api.service $(SOURCES_DIR)/$(NAME)-$(VERSION)/ 2>/dev/null || true

rpm: prep
	@echo "Building RPM..."
	@rpmbuild -ba $(SPECS_DIR)/vmm-linked-clone.spec \
		--define "_topdir $(RPMBUILD_DIR)" \
		--define "version $(VERSION)" \
		--define "release $(RELEASE)"
	@echo ""
	@echo "RPM built successfully!"
	@echo "RPM location: $(RPMS_DIR)/noarch/$(NAME)-$(VERSION)-$(RELEASE)$(DIST).noarch.rpm"
	@echo "SRPM location: $(SRPMS_DIR)/$(NAME)-$(VERSION)-$(RELEASE)$(DIST).src.rpm"

srpm: prep
	@echo "Building source RPM..."
	@rpmbuild -bs $(SPECS_DIR)/vmm-linked-clone.spec \
		--define "_topdir $(RPMBUILD_DIR)" \
		--define "version $(VERSION)" \
		--define "release $(RELEASE)"
	@echo ""
	@echo "SRPM built successfully!"
	@echo "SRPM location: $(SRPMS_DIR)/$(NAME)-$(VERSION)-$(RELEASE)$(DIST).src.rpm"

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf $(SOURCES_DIR)/$(SOURCE_TARBALL)
	@rm -rf $(SOURCES_DIR)/$(NAME)-$(VERSION)
	@rm -rf $(BUILD_DIR)/$(NAME)-$(VERSION)
	@rm -rf $(RPMS_DIR)/noarch/$(NAME)-*
	@rm -rf $(SRPMS_DIR)/$(NAME)-*
	@echo "Clean complete."

install-deps:
	@echo "Installing build dependencies..."
	@sudo dnf install -y rpm-build rpmdevtools python3-fastapi python3-uvicorn python3-pydantic || \
	 sudo yum install -y rpm-build rpmdevtools python3-fastapi python3-uvicorn python3-pydantic || \
	 echo "Please install: rpm-build, rpmdevtools, python3-fastapi, python3-uvicorn, python3-pydantic"

help:
	@echo "Available targets:"
	@echo "  all          - Build RPM (default)"
	@echo "  rpm          - Build binary RPM"
	@echo "  srpm         - Build source RPM"
	@echo "  prep         - Prepare build environment"
	@echo "  clean        - Clean build artifacts"
	@echo "  install-deps - Install build dependencies"
	@echo "  help         - Show this help message"

