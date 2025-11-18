#!/usr/bin/env bash
#
# Quick installer for cod-nowcast-ons
# Usage: curl -fsSL https://your-repo-url/install.sh | bash
#        Or: wget -qO- https://your-repo-url/install.sh | bash
#
# This script downloads the latest version and runs setup.sh

set -euo pipefail

REPO_URL="https://github.com/rjmalves/cod-nowcast-ons"  # Update with actual repo URL
TEMP_DIR=$(mktemp -d)
APP_NAME="cod-nowcast-ons"

cleanup() {
	rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

echo "Installing $APP_NAME..."
echo

# Check if git is available
if ! command -v git >/dev/null 2>&1; then
	echo "Error: git is required but not installed." >&2
	exit 1
fi

# Clone repository
echo "Downloading $APP_NAME..."
git clone --depth 1 "$REPO_URL" "$TEMP_DIR/$APP_NAME" >/dev/null 2>&1

cd "$TEMP_DIR/$APP_NAME"

# Determine installation mode based on privileges
if [[ $EUID -eq 0 ]]; then
	# Running as root, do system install
	./setup.sh
else
	# Not root, check if sudo is available
	if command -v sudo >/dev/null 2>&1; then
		echo "System installation requires sudo privileges."
		echo "Choose installation mode:"
		echo "  1) System-wide installation (requires sudo)"
		echo "  2) User-only installation (no sudo)"
		echo
		read -p "Enter choice [1-2]: " choice
		
		case $choice in
			1)
				sudo ./setup.sh
				;;
			2)
				./setup.sh --user
				;;
			*)
				echo "Invalid choice. Defaulting to user installation."
				./setup.sh --user
				;;
		esac
	else
		# No sudo available, force user install
		echo "Installing for current user (sudo not available)..."
		./setup.sh --user
	fi
fi

echo
echo "Installation complete!"
echo "Run '$APP_NAME --help' to get started."
