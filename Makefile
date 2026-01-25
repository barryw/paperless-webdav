# Makefile for paperless-webdav

.PHONY: help install lint typecheck test build push deploy bump changelog hooks

# Default target
help:
	@echo "paperless-webdav development commands"
	@echo ""
	@echo "Development:"
	@echo "  make install     - Install dependencies"
	@echo "  make lint        - Run linters"
	@echo "  make typecheck   - Run type checker"
	@echo "  make test        - Run tests"
	@echo ""
	@echo "Build & Deploy:"
	@echo "  make build       - Build Docker image"
	@echo "  make push        - Push to GHCR"
	@echo "  make deploy      - Deploy to Kubernetes"
	@echo ""
	@echo "Versioning:"
	@echo "  make bump        - Auto-bump version based on commits"
	@echo "  make changelog   - Generate changelog"
	@echo "  make hooks       - Install git hooks"
	@echo ""
	@echo "All-in-one:"
	@echo "  make ci          - Run full CI pipeline locally"
	@echo "  make release     - Bump, build, push, deploy"

# Variables
IMAGE_NAME := ghcr.io/barryw/paperless-webdav
VERSION := $(shell grep 'version = ' pyproject.toml | head -1 | cut -d'"' -f2)
GIT_SHA := $(shell git rev-parse --short HEAD)

# Development
install:
	pip install uv
	uv sync --frozen

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

typecheck:
	uv run mypy src/

test:
	PAPERLESS_URL=http://paperless.test \
	DATABASE_URL=postgresql://test:test@localhost/test \
	ENCRYPTION_KEY=dGVzdGtleXRoYXRpczMyYnl0ZXNsb25nIQ== \
	SECRET_KEY=test-secret-key-for-sessions \
	uv run pytest --tb=short -q

ci: lint typecheck test

# Build & Deploy
build:
	docker build -t $(IMAGE_NAME):$(GIT_SHA) -t $(IMAGE_NAME):latest .

push: build
	docker push $(IMAGE_NAME):$(GIT_SHA)
	docker push $(IMAGE_NAME):latest

deploy:
	kubectl set image deployment/paperless-webdav paperless-webdav=$(IMAGE_NAME):$(GIT_SHA)
	kubectl rollout status deployment/paperless-webdav --timeout=300s

# Versioning
bump:
	cog bump --auto

changelog:
	cog changelog

hooks:
	@HOOKS_DIR=$$(git rev-parse --git-dir)/hooks && \
	mkdir -p "$$HOOKS_DIR" && \
	echo '#!/bin/sh\nset -e\ncog verify --file $$1' > "$$HOOKS_DIR/commit-msg" && \
	chmod +x "$$HOOKS_DIR/commit-msg" && \
	echo "Git hooks installed at $$HOOKS_DIR"

# All-in-one
release: ci bump build push deploy
	@echo "Release complete!"
