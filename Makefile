.PHONY: help install install-dev test lint format type-check build clean docker-build docker-run

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install the package
	pip install -e .

install-dev: ## Install development dependencies
	pip install -e ".[dev]"
	pre-commit install

test: ## Run tests
	pytest

test-cov: ## Run tests with coverage
	pytest --cov=mcpmanager --cov-report=html --cov-report=term

lint: ## Run linting
	flake8 src/
	black --check src/
	isort --check-only src/

format: ## Format code
	black src/
	isort src/

type-check: ## Run type checking
	mypy src/mcpmanager

build: ## Build the package
	python -m build

clean: ## Clean build artifacts
	rm -rf build/ dist/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-build: ## Build Docker image
	docker build -t mcpmanager:latest .

docker-run: ## Run Docker container
	docker run -p 8000:8000 -v /var/run/docker.sock:/var/run/docker.sock mcpmanager:latest

docker-compose-up: ## Start with docker-compose
	docker-compose -f examples/docker-compose.yml up

docker-compose-down: ## Stop docker-compose
	docker-compose -f examples/docker-compose.yml down

docs: ## Generate documentation
	@echo "Documentation can be generated with Sphinx or MkDocs"
	@echo "Visit http://localhost:8000/docs for API documentation when running the server"

release: ## Create a release (requires version bump)
	@echo "1. Update version in pyproject.toml"
	@echo "2. Create git tag: git tag v<version>"
	@echo "3. Push tag: git push origin v<version>"
	@echo "4. Build and upload: make build && twine upload dist/*"