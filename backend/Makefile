.PHONY: help install install-dev run run-dev docker-build docker-run docker-stop docker-push clean clean-pyc clean-logs test lint format check

# Variables
PYTHON := python3
VENV := venv
VENV_BIN := $(VENV)/bin
PIP := $(VENV_BIN)/pip
PYTHON_VENV := $(VENV_BIN)/python
PORT := 8080
DOCKER_IMAGE := engineer-alpha-api
DOCKER_TAG := latest
GCP_PROJECT_ID := $(shell gcloud config get-value project 2>/dev/null || echo "")
GCP_REGION := us-central1

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(GREEN)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

# Setup and Installation
install: ## Create virtual environment and install dependencies
	@echo "$(GREEN)Creating virtual environment...$(NC)"
	$(PYTHON) -m venv $(VENV)
	@echo "$(GREEN)Installing dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "$(GREEN)Installation complete!$(NC)"

install-dev: install ## Install with development dependencies
	@echo "$(GREEN)Installing development dependencies...$(NC)"
	$(PIP) install black flake8 mypy pytest pytest-cov
	@echo "$(GREEN)Development dependencies installed!$(NC)"

# Running the application
run: ## Run the application locally (requires venv)
	@if [ ! -d "$(VENV)" ]; then \
		echo "$(RED)Virtual environment not found. Run 'make install' first.$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Starting FastAPI server on port $(PORT)...$(NC)"
	$(VENV_BIN)/uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload

run-dev: ## Run with development settings (auto-reload)
	@if [ ! -d "$(VENV)" ]; then \
		echo "$(RED)Virtual environment not found. Run 'make install' first.$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Starting FastAPI server in development mode...$(NC)"
	$(VENV_BIN)/uvicorn app.main:app --host 0.0.0.0 --port $(PORT) --reload --log-level debug

# Docker operations
docker-build: ## Build Docker image
	@echo "$(GREEN)Building Docker image: $(DOCKER_IMAGE):$(DOCKER_TAG)$(NC)"
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .
	@echo "$(GREEN)Docker image built successfully!$(NC)"

docker-run: ## Run Docker container locally
	@echo "$(GREEN)Running Docker container on port $(PORT)...$(NC)"
	docker run -d --name $(DOCKER_IMAGE) -p $(PORT):8080 --env PORT=8080 $(DOCKER_IMAGE):$(DOCKER_TAG)
	@echo "$(GREEN)Container started. Access API at http://localhost:$(PORT)$(NC)"

docker-run-interactive: ## Run Docker container interactively
	@echo "$(GREEN)Running Docker container interactively...$(NC)"
	docker run -it --rm -p $(PORT):8080 --env PORT=8080 $(DOCKER_IMAGE):$(DOCKER_TAG)

docker-stop: ## Stop and remove Docker container
	@echo "$(YELLOW)Stopping Docker container...$(NC)"
	-docker stop $(DOCKER_IMAGE) 2>/dev/null
	-docker rm $(DOCKER_IMAGE) 2>/dev/null
	@echo "$(GREEN)Container stopped and removed.$(NC)"

docker-push: ## Build and push Docker image to GCP Container Registry
	@if [ -z "$(GCP_PROJECT_ID)" ]; then \
		echo "$(RED)GCP project ID not found. Set it with: gcloud config set project PROJECT_ID$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Building and pushing to gcr.io/$(GCP_PROJECT_ID)/$(DOCKER_IMAGE)...$(NC)"
	docker build -t gcr.io/$(GCP_PROJECT_ID)/$(DOCKER_IMAGE):$(DOCKER_TAG) .
	docker push gcr.io/$(GCP_PROJECT_ID)/$(DOCKER_IMAGE):$(DOCKER_TAG)
	@echo "$(GREEN)Image pushed successfully!$(NC)"

docker-deploy: docker-push ## Deploy to Cloud Run
	@if [ -z "$(GCP_PROJECT_ID)" ]; then \
		echo "$(RED)GCP project ID not found. Set it with: gcloud config set project PROJECT_ID$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Deploying to Cloud Run...$(NC)"
	gcloud run deploy engineer-alpha-api \
		--image gcr.io/$(GCP_PROJECT_ID)/$(DOCKER_IMAGE):$(DOCKER_TAG) \
		--region $(GCP_REGION) \
		--platform managed \
		--allow-unauthenticated \
		--memory 2Gi \
		--cpu 2 \
		--timeout 60s \
		--min-instances 0 \
		--max-instances 10
	@echo "$(GREEN)Deployment complete!$(NC)"

# Testing and Quality
test: ## Run tests (if pytest is installed)
	@if [ ! -d "$(VENV)" ]; then \
		echo "$(RED)Virtual environment not found. Run 'make install-dev' first.$(NC)"; \
		exit 1; \
	fi
	@if ! $(PIP) show pytest > /dev/null 2>&1; then \
		echo "$(YELLOW)pytest not installed. Run 'make install-dev' first.$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Running tests...$(NC)"
	$(VENV_BIN)/pytest -v

lint: ## Run linter (if flake8 is installed)
	@if [ ! -d "$(VENV)" ]; then \
		echo "$(RED)Virtual environment not found. Run 'make install-dev' first.$(NC)"; \
		exit 1; \
	fi
	@if ! $(PIP) show flake8 > /dev/null 2>&1; then \
		echo "$(YELLOW)flake8 not installed. Run 'make install-dev' first.$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Running linter...$(NC)"
	$(VENV_BIN)/flake8 app --max-line-length=120 --exclude=__pycache__,venv

format: ## Format code with black (if black is installed)
	@if [ ! -d "$(VENV)" ]; then \
		echo "$(RED)Virtual environment not found. Run 'make install-dev' first.$(NC)"; \
		exit 1; \
	fi
	@if ! $(PIP) show black > /dev/null 2>&1; then \
		echo "$(YELLOW)black not installed. Run 'make install-dev' first.$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Formatting code...$(NC)"
	$(VENV_BIN)/black app --line-length=120

check: lint ## Run all checks (lint, format check)
	@echo "$(GREEN)Running all checks...$(NC)"

# Cleanup
clean: clean-pyc clean-logs ## Remove all generated files
	@echo "$(GREEN)Cleanup complete!$(NC)"

clean-pyc: ## Remove Python cache files
	@echo "$(YELLOW)Removing Python cache files...$(NC)"
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name "*.pyd" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	@echo "$(GREEN)Python cache files removed.$(NC)"

clean-logs: ## Remove log files
	@echo "$(YELLOW)Removing log files...$(NC)"
	rm -f app/logs/*.log 2>/dev/null || true
	rm -f logs/*.log 2>/dev/null || true
	@echo "$(GREEN)Log files removed.$(NC)"

clean-venv: ## Remove virtual environment
	@echo "$(YELLOW)Removing virtual environment...$(NC)"
	rm -rf $(VENV)
	@echo "$(GREEN)Virtual environment removed.$(NC)"

clean-docker: ## Remove Docker image and containers
	@echo "$(YELLOW)Removing Docker containers and images...$(NC)"
	-docker stop $(DOCKER_IMAGE) 2>/dev/null || true
	-docker rm $(DOCKER_IMAGE) 2>/dev/null || true
	-docker rmi $(DOCKER_IMAGE):$(DOCKER_TAG) 2>/dev/null || true
	@echo "$(GREEN)Docker cleanup complete.$(NC)"

# Development helpers
shell: ## Open Python shell with app context
	@if [ ! -d "$(VENV)" ]; then \
		echo "$(RED)Virtual environment not found. Run 'make install' first.$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Starting Python shell...$(NC)"
	$(PYTHON_VENV) -i -c "from app.main import app; import IPython; IPython.embed()" || $(PYTHON_VENV)

requirements: ## Update requirements.txt from installed packages
	@if [ ! -d "$(VENV)" ]; then \
		echo "$(RED)Virtual environment not found. Run 'make install' first.$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Generating requirements.txt...$(NC)"
	$(PIP) freeze > requirements.txt
	@echo "$(GREEN)Requirements updated!$(NC)"

# Default target
.DEFAULT_GOAL := help
