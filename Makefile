.PHONY: help install install-user uninstall uninstall-user reinstall test clean

help:
	@echo "cod-nowcast-ons - Installation and Management"
	@echo ""
	@echo "Available targets:"
	@echo "  make install        - Install system-wide (requires sudo)"
	@echo "  make install-user   - Install for current user only"
	@echo "  make reinstall      - Force reinstall system-wide"
	@echo "  make uninstall      - Uninstall system installation"
	@echo "  make uninstall-user - Uninstall user installation"
	@echo "  make clean          - Clean build artifacts and cache"
	@echo "  make test           - Run tests (if available)"

install:
	@echo "Installing cod-nowcast-ons system-wide..."
	sudo ./setup.sh

install-user:
	@echo "Installing cod-nowcast-ons for current user..."
	./setup.sh --user

reinstall:
	@echo "Reinstalling cod-nowcast-ons..."
	sudo ./setup.sh --force

uninstall:
	@echo "Uninstalling cod-nowcast-ons (system)..."
	sudo ./setup.sh --uninstall

uninstall-user:
	@echo "Uninstalling cod-nowcast-ons (user)..."
	./setup.sh --user --uninstall

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf build/ dist/ *.egg-info
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean complete."

test:
	@echo "Running tests..."
	@echo "No tests configured yet."
