#!/usr/bin/env bash

set -euo pipefail

# Default configuration
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="python3"
ENTRYPOINT_NAME="cod-nowcast-ons"  # as defined in pyproject [project.scripts]
APP_NAME="cod-nowcast-ons"

# Installation modes
SYSTEM_INSTALL_DIR="/opt/$APP_NAME"
SYSTEM_BIN_DIR="/usr/local/bin"
USER_INSTALL_DIR="$HOME/.local/$APP_NAME"
USER_BIN_DIR="$HOME/.local/bin"

# Default to system-wide installation
INSTALL_DIR="$SYSTEM_INSTALL_DIR"
BIN_DIR="$SYSTEM_BIN_DIR"
USE_SUDO=1

# Flags
FORCE=0
QUIET=0
USER_MODE=0
UNINSTALL=0

usage() {
	cat <<EOF
Usage: sudo ./setup.sh [options]

Install $APP_NAME CLI application.

Options:
	-u, --user      Install for current user only (no sudo required).
	                Installs to: $USER_INSTALL_DIR
	                Symlink to: $USER_BIN_DIR
	
	-f, --force     Force reinstallation (remove existing installation).
	-q, --quiet     Minimal output.
	--uninstall     Remove the installation.
	-h, --help      Show this help.

System Installation (default, requires sudo):
	Installation directory: $SYSTEM_INSTALL_DIR
	Symlink directory: $SYSTEM_BIN_DIR

Examples:
	sudo ./setup.sh                    # System-wide installation
	./setup.sh --user                  # User-only installation
	sudo ./setup.sh --uninstall        # Remove system installation
	./setup.sh --user --uninstall      # Remove user installation
EOF
}

log() { [ "$QUIET" -eq 1 ] || echo -e "$*"; }

error() {
	echo "Error: $*" >&2
	exit 1
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		-u|--user) USER_MODE=1; shift ;;
		-f|--force) FORCE=1; shift ;;
		-q|--quiet) QUIET=1; shift ;;
		--uninstall) UNINSTALL=1; shift ;;
		-h|--help) usage; exit 0 ;;
		*) echo "Unknown option: $1" >&2; usage; exit 1 ;;
	esac
done

# Adjust paths for user mode
if [[ $USER_MODE -eq 1 ]]; then
	INSTALL_DIR="$USER_INSTALL_DIR"
	BIN_DIR="$USER_BIN_DIR"
	USE_SUDO=0
	log "User mode: Installing to $INSTALL_DIR"
else
	log "System mode: Installing to $INSTALL_DIR (requires sudo)"
fi

	log "System mode: Installing to $INSTALL_DIR (requires sudo)"
fi

# Check if running with appropriate privileges
if [[ $USE_SUDO -eq 1 && $EUID -ne 0 ]]; then
	error "System installation requires sudo. Run: sudo ./setup.sh"
fi

# Uninstall function
uninstall() {
	log "Uninstalling $APP_NAME..."
	
	local venv_dir="$INSTALL_DIR/venv"
	local symlink="$BIN_DIR/$ENTRYPOINT_NAME"
	
	if [[ -L "$symlink" ]]; then
		rm -f "$symlink"
		log "Removed symlink: $symlink"
	fi
	
	if [[ -d "$INSTALL_DIR" ]]; then
		rm -rf "$INSTALL_DIR"
		log "Removed installation directory: $INSTALL_DIR"
	fi
	
	log "Uninstallation complete."
	exit 0
}

if [[ $UNINSTALL -eq 1 ]]; then
	uninstall
fi

# Validate Python
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
	error "$PYTHON_BIN not found in PATH."
fi

# Ensure Python version >= 3.11
PY_VERSION=$($PYTHON_BIN -c 'import sys; print("%d.%d"%sys.version_info[:2])')
MIN_MAJOR=3
MIN_MINOR=11
CUR_MAJOR=${PY_VERSION%%.*}
CUR_MINOR=${PY_VERSION#*.}
if [[ $CUR_MAJOR -lt $MIN_MAJOR || ( $CUR_MAJOR -eq $MIN_MAJOR && $CUR_MINOR -lt $MIN_MINOR ) ]]; then
	error "Python >= $MIN_MAJOR.$MIN_MINOR required (found $PY_VERSION)."
fi

VENV_DIR="$INSTALL_DIR/venv"

# Handle existing installation
if [[ -d "$INSTALL_DIR" ]]; then
	if [[ $FORCE -eq 1 ]]; then
		log "Removing existing installation (--force requested)..."
		rm -rf "$INSTALL_DIR"
	else
		error "Installation directory already exists: $INSTALL_DIR\nUse --force to reinstall or --uninstall to remove."
	fi
fi

# Create installation directory
log "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Copy application files to installation directory
log "Copying application files..."
cp -r "$PROJECT_ROOT/app" "$INSTALL_DIR/"
cp "$PROJECT_ROOT/main.py" "$INSTALL_DIR/"
cp "$PROJECT_ROOT/pyproject.toml" "$INSTALL_DIR/"
cp "$PROJECT_ROOT/README.md" "$INSTALL_DIR/" 2>/dev/null || true

if [[ -f "$PROJECT_ROOT/.env.example" ]]; then
	cp "$PROJECT_ROOT/.env.example" "$INSTALL_DIR/"
fi

# Create virtual environment in installation directory
log "Creating virtual environment in $VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"

# Activate and install
source "$VENV_DIR/bin/activate"

log "Upgrading pip, setuptools, wheel..."
python -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1

log "Installing $APP_NAME..."
cd "$INSTALL_DIR"
pip install . >/dev/null 2>&1

# Create .env if needed
if [[ ! -f "$INSTALL_DIR/.env" && -f "$INSTALL_DIR/.env.example" ]]; then
	cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
	log "Created .env file from .env.example"
fi

deactivate

# Create bin directory if it doesn't exist
mkdir -p "$BIN_DIR"

# Create symlink
SYMLINK_PATH="$BIN_DIR/$ENTRYPOINT_NAME"
if [[ -L "$SYMLINK_PATH" || -f "$SYMLINK_PATH" ]]; then
	rm -f "$SYMLINK_PATH"
fi

ln -s "$VENV_DIR/bin/$ENTRYPOINT_NAME" "$SYMLINK_PATH"
log "Created symlink: $SYMLINK_PATH -> $VENV_DIR/bin/$ENTRYPOINT_NAME"

# Set appropriate permissions
if [[ $USE_SUDO -eq 1 ]]; then
	# For system install, make it readable by all but writable only by root
	chmod -R 755 "$INSTALL_DIR"
	chmod 755 "$SYMLINK_PATH"
fi

# Check if bin directory is in PATH
case ":$PATH:" in
	*":$BIN_DIR:"*)
		log "\n✓ Installation complete!"
		log "Run '$ENTRYPOINT_NAME --help' to get started."
		;;
	*)
		log "\n✓ Installation complete!"
		log "Note: $BIN_DIR is not in your PATH."
		log "Add it by adding this line to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
		log "  export PATH=\"$BIN_DIR:\$PATH\""
		log "\nThen reload your shell or run: source ~/.bashrc"
		;;
esac

if [[ $USER_MODE -eq 1 ]]; then
	log "\nUser installation location: $INSTALL_DIR"
else
	log "\nSystem installation location: $INSTALL_DIR"
	log "To uninstall, run: sudo ./setup.sh --uninstall"
fi