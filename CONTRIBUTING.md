# Contributing to MCPManager

Thank you for your interest in contributing to MCPManager! This document provides guidelines and information for contributors.

## Code of Conduct

This project adheres to a Code of Conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## How to Contribute

### Reporting Bugs

Before creating bug reports, please check the existing issues to avoid duplicates. When you create a bug report, include as many details as possible:

- Use a clear and descriptive title
- Describe the exact steps to reproduce the problem
- Provide specific examples and sample configurations
- Describe the expected vs actual behavior
- Include error messages, logs, and screenshots if applicable
- Note your environment (OS, Python version, Docker version)

### Suggesting Enhancements

Enhancement suggestions are welcome! Please provide:

- A clear and descriptive title
- A detailed description of the proposed functionality
- Explain why this enhancement would be useful
- Provide examples of how the feature would be used

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Install development dependencies**: `make install-dev`
3. **Make your changes** following our coding standards
4. **Add tests** for your changes
5. **Run the test suite**: `make test`
6. **Run linting and formatting**: `make lint format`
7. **Update documentation** if needed
8. **Commit your changes** with a clear commit message
9. **Push to your fork** and submit a pull request

#### Pull Request Guidelines

- Keep pull requests focused on a single feature or bug fix
- Write clear, descriptive commit messages
- Include tests for new functionality
- Update documentation as needed
- Ensure all CI checks pass
- Request review from maintainers

## Development Setup

### Prerequisites

- Python 3.8 or higher
- Docker Desktop or Docker Engine
- Git

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/mcpmanager/mcpmanager.git
   cd mcpmanager
   ```

2. **Install in development mode**
   ```bash
   make install-dev
   ```

3. **Run tests**
   ```bash
   make test
   ```

4. **Start development server**
   ```bash
   mcpm serve --host 127.0.0.1 --port 8000
   ```

### Testing

We use pytest for testing. Tests are located in the `tests/` directory.

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest tests/test_manager.py

# Run specific test
pytest tests/test_manager.py::TestMCPManager::test_run_server_success
```

### Code Style

We use several tools to maintain code quality:

- **Black** for code formatting
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking

Run all checks:
```bash
make lint format type-check
```

### Documentation

- Update README.md for significant changes
- Add docstrings to new functions and classes
- Update API documentation if adding new endpoints
- Include examples for new features

## Project Structure

```
mcpmanager/
├── src/mcpmanager/          # Main package
│   ├── core/                # Core functionality
│   ├── cli/                 # Command-line interface
│   ├── api/                 # REST API
│   ├── auth/                # Authentication & authorization
│   ├── container/           # Container management
│   ├── transport/           # Transport protocols
│   ├── config/              # Configuration management
│   └── secrets/             # Secrets management
├── tests/                   # Test suite
├── examples/                # Example configurations
└── docs/                    # Documentation
```

## Coding Standards

### Python Style

- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Write descriptive variable and function names
- Keep functions focused and small
- Use async/await for I/O operations

### Error Handling

- Use specific exception types from `mcpmanager.exceptions`
- Include helpful error messages
- Log errors appropriately
- Handle edge cases gracefully

### Testing Guidelines

- Write tests for all new functionality
- Aim for high code coverage (>90%)
- Use mocks for external dependencies
- Test both success and failure scenarios
- Include integration tests for critical paths

### Documentation

- Write clear docstrings for all public functions
- Use type hints consistently
- Include examples in docstrings when helpful
- Update README for user-facing changes

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create and push git tag: `git tag v0.1.1 && git push origin v0.1.1`
4. GitHub Actions will automatically build and publish the release

## Getting Help

- Join our Discord server (link in README)
- Open a GitHub Discussion for questions
- Check existing issues and documentation
- Reach out to maintainers

## Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md file
- Release notes
- GitHub contributors page

Thank you for contributing to MCPManager!