# Changelog

All notable changes to MCPManager will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-11

### Added
- Initial release of MCPManager
- Core MCP server management functionality
- Dynamic client discovery and auto-configuration
- Support for VS Code, Cursor, Claude Code, Cline, and Roo Code clients
- Container-based MCP server isolation using Docker
- Support for stdio and SSE transport protocols
- Authentication and authorization systems (Anonymous, Local, OIDC)
- Cedar-based authorization framework
- Secrets management with encrypted and 1Password backends
- REST API server with FastAPI
- Comprehensive CLI interface (`mcpm` command)
- Registry system with built-in MCP servers
- Permission profiles for fine-grained container security
- Configuration management with YAML/JSON support
- Docker and container management
- Transport layer abstraction
- Comprehensive error handling and logging
- Production-ready packaging and distribution

### Security
- Secure container isolation with minimal privileges
- Encrypted secrets storage with keyring integration
- CORS configuration for API security
- Docker socket security considerations
- Permission profiles for network and filesystem access

### Documentation
- Comprehensive README with usage examples
- API documentation with OpenAPI/Swagger
- Security policy and guidelines
- Contributing guidelines
- Example configurations and permission profiles

### Infrastructure
- CI/CD pipeline with GitHub Actions
- Automated testing with pytest
- Code quality tools (black, isort, flake8, mypy)
- Security scanning with safety and bandit
- Docker image building and publishing
- PyPI package publishing automation

[Unreleased]: https://github.com/mcpmanager/mcpmanager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mcpmanager/mcpmanager/releases/tag/v0.1.0