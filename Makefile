.PHONY: help install install-user uninstall uninstall-user reinstall test test-unit test-integration test-cov test-s3 lint format clean

help:
	@echo "cod-nowcast-ons - Installation and Management"
	@echo ""
	@echo "Available targets:"
	@echo "  make install        - Install system-wide (requires sudo)"
	@echo "  make install-user   - Install for current user only"
	@echo "  make reinstall      - Force reinstall system-wide"
	@echo "  make uninstall      - Uninstall system installation"
	@echo "  make uninstall-user - Uninstall user installation"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run all tests"
	@echo "  make test-unit      - Run unit tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo "  make test-cov       - Run tests with coverage report"
	@echo "  make test-s3        - Run S3-specific tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Run linter (ruff)"
	@echo "  make format         - Format code with ruff"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean          - Clean build artifacts and cache"

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
	@rm -rf .pytest_cache .coverage htmlcov/ .ruff_cache
	@echo "Clean complete."

test:
	@echo "Running all tests..."
	@.venv/bin/pytest -v

test-unit:
	@echo "Running unit tests..."
	@.venv/bin/pytest tests/unit/ -v

test-integration:
	@echo "Running integration tests..."
	@.venv/bin/pytest tests/integration/ -v -m "not slow and not plotting"

test-cov:
	@echo "Running tests with coverage..."
	@.venv/bin/pytest --cov=app --cov-report=html --cov-report=term -v
	@echo "Coverage report generated in htmlcov/"

test-s3:
	@echo "Running S3-specific tests..."
	@.venv/bin/pytest -m s3 -v

lint:
	@echo "Running linter..."
	@.venv/bin/ruff check app/ tests/

format:
	@echo "Formatting code..."
	@.venv/bin/ruff format app/ tests/
