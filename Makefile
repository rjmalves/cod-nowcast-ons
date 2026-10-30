.PHONY: help install install-user uninstall uninstall-user reinstall test test-unit test-integration test-cov test-s3 lint format typecheck image smoke gate clean

IMAGE ?= cod-nowcast-ons:local
IMAGE_SOURCE ?= https://github.com/rjmalves/cod-nowcast-ons
IMPORT_CHAIN := import cv2, pysteps; from pysteps import motion

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
	@echo "  make lint           - Run ruff check and ruff format --check"
	@echo "  make format         - Format code with ruff"
	@echo "  make typecheck      - Run mypy (strict, from pyproject.toml)"
	@echo "  make gate           - Scan the commits since main for internal identifiers"
	@echo ""
	@echo "Container image:"
	@echo "  make image          - Build the image as $(IMAGE)"
	@echo "  make smoke          - Run the CI image checks and fixture nowcast on $(IMAGE)"
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
	@uv run --no-sync pytest -v

test-unit:
	@echo "Running unit tests..."
	@uv run --no-sync pytest tests/unit/ -v

test-integration:
	@echo "Running integration tests..."
	@uv run --no-sync pytest tests/integration/ -v -m "not slow and not plotting"

test-cov:
	@echo "Running tests with coverage..."
	@uv run --no-sync pytest --cov=app --cov-report=html --cov-report=term -v
	@echo "Coverage report generated in htmlcov/"

test-s3:
	@echo "Running S3-specific tests..."
	@uv run --no-sync pytest -m s3 -v

lint:
	@echo "Running linter..."
	@uv run --no-sync ruff check .
	@uv run --no-sync ruff format --check .

format:
	@echo "Formatting code..."
	@uv run --no-sync ruff format .

typecheck:
	@echo "Running mypy..."
	@uv run --no-sync mypy

image:
	@echo "Building $(IMAGE)..."
	docker buildx build --load \
		--secret id=nwp_core_token,env=NWP_CORE_READ_TOKEN \
		--build-arg IMAGE_SOURCE=$(IMAGE_SOURCE) \
		-t $(IMAGE) .

smoke:
	@echo "Checking $(IMAGE)..."
	python3 ci/check_image.py $(IMAGE) --imports "$(IMPORT_CHAIN)"
	ci/fixture-nowcast.sh $(IMAGE)

gate:
	@echo "Scanning the commits since main for internal identifiers..."
	python3 ci/gate/run_gate.py --provision
	NWP_GATE_BASE_SHA=$$(git merge-base main HEAD) NWP_GATE_HEAD_SHA=$$(git rev-parse HEAD) \
		python3 ci/gate/run_gate.py --mode diff
