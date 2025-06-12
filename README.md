# MCPManager - Secured MCP Server Deployment  and MCP Server  Discovery with  right Security Posture Management

MCPManager is a comprehensive, production-ready platform for deploying, managing, and securing MCP (Model Context Protocol) servers with advanced features including multi-runtime support, observability, and enterprise-grade security.

PyPi Reference:  https://pypi.org/project/mcp-deployment/

##  Key Features

### Core Management
- **Dynamic MCP Server Discovery**: Automatically discover and configure MCP servers from registries
- **Multi-Runtime Support**: Deploy to Docker, Podman, and Kubernetes environments
- **Container-based Isolation**: Run MCP servers in secure, isolated containers
- **Protocol Scheme Support**: Direct execution of `uvx://`, `npx://`, and `go://` schemes
- **Transport Protocols**: Support for stdio, SSE, HTTP proxy, and transparent proxy protocols

### Security & Permissions
- **Advanced Permission Profiles**: Fine-grained security controls with built-in templates
- **Image Verification**: Sigstore-based container image verification
- **CA Certificate Management**: Complete certificate lifecycle management
- **Secrets Management**: Secure handling of API keys and credentials with multiple backends
- **Security Policies**: Enterprise-grade security policies with Cedar language support

### Operations & Observability
- **OpenTelemetry Integration**: Comprehensive telemetry with metrics, tracing, and logging
- **Inspector/Debugging**: Real-time debugging and introspection capabilities
- **Health Monitoring**: Built-in health checks and monitoring
- **Audit Logging**: Complete audit trail of all operations

### Enterprise Features
- **Kubernetes Operator**: Deploy and manage MCP servers in Kubernetes with CRDs
- **Registry Management**: Curated MCP server registry with verification
- **Client Auto-configuration**: Seamless integration with VS Code, Cursor, and other clients
- **RESTful API**: Complete REST API for automation and integration

##  Installation

### Basic Installation
```bash
pip install mcp-deployment
```

### With Optional Features
```bash
# With Kubernetes support
pip install mcp-deployment[kubernetes]

# With telemetry support
pip install mcp-deployment[telemetry]

# With authentication support
pip install mcp-deployment[auth]

# Full installation
pip install mcp-deployment[kubernetes,telemetry,auth]
```

##  Quick Start

### Basic Usage
```bash
# Enable client auto-discovery
mcpm config auto-discovery enable

# Run an MCP server from registry
mcpm run fetch

# Run with protocol scheme
mcpm run "uvx://mcp-fetch"

# List running servers
mcpm list

# Stop a server
mcpm stop fetch

# View server logs
mcpm logs fetch
```

### Advanced Configuration
```bash
# Set up secrets
mcpm secret set GITHUB_TOKEN

# Create custom permission profile
mcpm permission create my-profile --template restricted

# Run with custom permissions
mcpm run github --permission-profile my-profile

# Set up observability
mcpm config telemetry enable --endpoint http://jaeger:14268/api/traces
```

##  Architecture

MCPManager provides a comprehensive platform for MCP server management:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Client Apps   │    │   MCPManager     │    │  MCP Servers    │
│  (VS Code,      │◄──►│   (API/Proxy)    │◄──►│  (Containerized)│
│   Cursor, etc.) │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │  Runtime Layer   │
                       │ (Docker/K8s/Pod) │
                       └──────────────────┘
```

##  Comprehensive CLI Reference

### Server Management
```bash
# Run servers
mcpm run <server_name>                    # Run from registry
mcpm run <image>                          # Run custom image
mcpm run "uvx://package-name"             # Run Python package
mcpm run "npx://package-name"             # Run Node.js package
mcpm run "go://module@version"            # Run Go module

# Server lifecycle
mcpm stop <server_name>                   # Stop server
mcpm restart <server_name>                # Restart server
mcpm rm <server_name>                     # Remove server
mcpm list                                 # List all servers
mcpm list --running                       # List running servers

# Server inspection
mcpm logs <server_name>                   # View logs
mcpm logs <server_name> --follow          # Follow logs
mcpm inspect <server_name>                # Detailed inspection
mcpm status <server_name>                 # Server status
```

### Configuration Management
```bash
# Client auto-discovery
mcpm config auto-discovery enable         # Enable auto-discovery
mcpm config auto-discovery disable        # Disable auto-discovery
mcpm config auto-discovery status         # Check status

# Registry management
mcpm config registry set <url>            # Set registry URL
mcpm config registry get                  # Get current registry
mcpm config registry list                 # List registry entries

# Certificate management
mcpm config ca-cert set <path>            # Set CA certificate
mcpm config ca-cert get                   # Get CA certificate info
mcpm config ca-cert unset                 # Remove CA certificate
```

### Secrets Management
```bash
# Secret operations
mcpm secret set <name> [value]            # Set secret (prompts if no value)
mcpm secret get <name>                    # Get secret
mcpm secret list                          # List secrets
mcpm secret delete <name>                 # Delete secret

# Secret providers
mcpm secret provider 1password            # Use 1Password
mcpm secret provider encrypted            # Use encrypted storage
mcpm secret provider none                 # No encryption

# Keyring management
mcpm secret reset-keyring                 # Reset keyring
```

### Permission Management
```bash
# Permission profiles
mcpm permission list                      # List profiles
mcpm permission create <name>             # Create profile
mcpm permission create <name> --template <template>  # From template
mcpm permission delete <name>             # Delete profile
mcpm permission validate <name>           # Validate profile

# Available templates: minimal, restricted, standard, privileged
```

### Registry Operations
```bash
# Registry browsing
mcpm registry list                        # List available servers
mcpm registry search <query>              # Search servers
mcpm registry info <server>               # Server information

# Server search
mcpm search <query>                       # Search for servers
```

### Proxy Management
```bash
# HTTP proxy
mcpm proxy start --port 8080              # Start HTTP proxy
mcpm proxy stop                           # Stop proxy
mcpm proxy status                         # Proxy status
```

### Development & Debugging
```bash
# Inspector
mcpm inspector                            # Start inspector interface
mcpm inspector --port 8081               # Custom port

# Version information
mcpm version                              # Show version
mcpm version --detailed                   # Detailed version info
```

##  Configuration

### Configuration File
MCPManager uses a YAML configuration file located at `~/.mcpmanager/config.yaml`:

```yaml
# Auto-discovery settings
auto_discovery:
  enabled: true
  registry_url: "https://registry.mcpmanager.io"

# Security settings
security:
  verify_images: true
  default_permission_profile: "restricted"
  ca_certificate_path: "/path/to/ca.pem"

# Telemetry settings
telemetry:
  enabled: true
  endpoint: "http://localhost:14268/api/traces"
  service_name: "mcpmanager"
  metrics_port: 9090

# Runtime settings
runtime:
  default: "docker"
  docker:
    socket: "/var/run/docker.sock"
  kubernetes:
    namespace: "mcpmanager"
    context: "default"

# Secrets settings
secrets:
  provider: "encrypted"  # Options: none, encrypted, 1password
  encryption_key_path: "~/.mcpmanager/secrets.key"
```

### Environment Variables
```bash
# Runtime configuration
export MCPM_RUNTIME=docker                # Default runtime
export MCPM_CONFIG_DIR=~/.mcpmanager      # Config directory

# Docker settings
export DOCKER_HOST=unix:///var/run/docker.sock

# Kubernetes settings
export KUBECONFIG=~/.kube/config
export MCPM_K8S_NAMESPACE=mcpmanager

# Telemetry settings
export MCPM_TELEMETRY_ENABLED=true
export MCPM_OTEL_ENDPOINT=http://localhost:14268/api/traces

# Registry settings
export MCPM_REGISTRY_URL=https://registry.mcpmanager.io
export MCPM_VERIFY_IMAGES=true
```

## Security Features

### Permission Profiles
MCPManager includes built-in permission profiles:

- **minimal**: Bare minimum permissions for basic functionality
- **restricted**: Limited permissions for untrusted servers
- **standard**: Balanced permissions for most use cases
- **privileged**: Extended permissions for trusted servers

### Image Verification
Automatic verification of container images using Sigstore:

```bash
# Enable image verification
mcpm config verify-images enable

# Verify specific image
mcpm verify <image>
```

### Certificate Management
Complete certificate lifecycle management:

```bash
# Certificate operations
mcpm cert import <path>                   # Import certificate
mcpm cert list                           # List certificates
mcpm cert validate <name>                 # Validate certificate
mcpm cert export <name> <path>            # Export certificate
mcpm cert remove <name>                   # Remove certificate

# Certificate search and filtering
mcpm cert search <query>                  # Search certificates
mcpm cert expiring --days 30             # Find expiring certificates
mcpm cert expired                        # Find expired certificates
```

## Observability

### OpenTelemetry Integration
MCPManager provides comprehensive observability:

- **Tracing**: Distributed tracing of all operations
- **Metrics**: Performance and operational metrics
- **Logging**: Structured logging with correlation IDs

### Metrics Available
- Server creation/destruction rates
- Request/response times
- Error rates and types
- Resource utilization
- Container lifecycle events

### Health Monitoring
```bash
# Health checks
mcpm health                               # Overall system health
mcpm health <server_name>                 # Specific server health
```

## ⚡ Protocol Schemes

MCPManager supports direct execution of protocol schemes:

### Python (uvx://)
```bash
mcpm run "uvx://mcp-fetch"                # Run Python package
mcpm run "uvx://mcp-github@latest"        # Specific version
```

### Node.js (npx://)
```bash
mcpm run "npx://@mcp/server-fetch"        # Run npm package
mcpm run "npx://@mcp/server-github@1.0.0" # Specific version
```

### Go (go://)
```bash
mcpm run "go://github.com/user/mcp-server@latest"  # Run Go module
mcpm run "go://github.com/user/mcp-server@v1.2.3"  # Specific version
```

## Kubernetes Deployment

### Using Helm Charts
```bash
# Add MCPManager Helm repository
helm repo add mcpmanager https://charts.mcpmanager.io
helm repo update

# Install MCPManager operator
helm install mcpmanager mcpmanager/mcpmanager-operator

# Install CRDs
helm install mcpmanager-crds mcpmanager/mcpmanager-crds
```

### Manual Deployment
```bash
# Apply CRDs
kubectl apply -f https://raw.githubusercontent.com/mcpmanager/mcp-deployment/main/deploy/crds/

# Deploy operator
kubectl apply -f https://raw.githubusercontent.com/mcpmanager/mcp-deployment/main/deploy/operator/
```

### MCP Server CRD Example
```yaml
apiVersion: mcpmanager.io/v1alpha1
kind: MCPServer
metadata:
  name: fetch-server
spec:
  image: mcpmanager/fetch:latest
  transport: sse
  port: 8080
  permissionProfile: restricted
  secrets:
    - name: api-key
      target: API_KEY
  resources:
    requests:
      memory: "128Mi"
      cpu: "100m"
    limits:
      memory: "256Mi"
      cpu: "200m"
```

## REST API

MCPManager provides a comprehensive REST API:

### Server Management
```bash
# List servers
GET /api/v1/servers

# Create server
POST /api/v1/servers
{
  "name": "my-server",
  "image": "mcpmanager/fetch:latest",
  "transport": "sse"
}

# Get server details
GET /api/v1/servers/{name}

# Stop server
DELETE /api/v1/servers/{name}
```

### Registry Operations
```bash
# Search registry
GET /api/v1/registry/search?q=fetch

# Get server info
GET /api/v1/registry/servers/{name}
```

### Health and Metrics
```bash
# Health check
GET /api/v1/health

# Metrics endpoint
GET /metrics
```

## Development

### Building from Source
```bash
# Clone repository
git clone https://github.com/mcpmanager/mcp-deployment.git
cd mcp-deployment

# Install in development mode
pip install -e .[dev]

# Run tests
pytest

# Run linting
black . && isort . && flake8
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Production Deployment

### System Requirements
- **CPU**: 2+ cores recommended
- **Memory**: 4GB+ RAM recommended
- **Storage**: 10GB+ for images and data
- **Network**: Outbound internet access for registries

### High Availability Setup
```yaml
# Example HA configuration
replicas: 3
persistence:
  enabled: true
  storageClass: "fast-ssd"
monitoring:
  enabled: true
  prometheus: true
  grafana: true
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
```

### Performance Tuning
```yaml
# Performance configuration
runtime:
  docker:
    concurrent_limit: 50
    timeout: 300
cache:
  enabled: true
  ttl: 3600
  max_size: 1000
telemetry:
  sampling_rate: 0.1  # 10% sampling
```

##  Examples

### Example: GitHub MCP Server
```bash
# Set up GitHub token
mcpm secret set GITHUB_TOKEN ghp_xxxxxxxxxxxx

# Run GitHub server with custom permissions
mcpm run github --permission-profile standard --transport sse

# Check server status
mcpm status github

# View logs
mcpm logs github --follow
```

### Example: Multi-Server Setup
```bash
# Run multiple servers
mcpm run fetch --transport sse --port 8080
mcpm run github --transport sse --port 8081
mcpm run memory --transport stdio

# List all running servers
mcpm list --running

# Stop all servers
mcpm stop --all
```

### Example: Custom Container
```bash
# Run custom MCP server
mcpm run my-registry.com/my-mcp-server:latest \\
  --permission-profile custom \\
  --env MY_CONFIG=value \\
  --port 8082

# With secrets
mcpm run my-server \\
  --secret API_KEY=my-api-key \\
  --secret DB_PASSWORD=my-db-password
```

## Troubleshooting

### Common Issues

#### Docker Connection Issues
```bash
# Check Docker status
docker version

# Verify permissions
sudo usermod -aG docker $USER
newgrp docker
```

#### Registry Connection Issues
```bash
# Test registry connectivity
mcpm registry list

# Check CA certificate
mcpm config ca-cert get
```

#### Permission Errors
```bash
# Validate permission profile
mcpm permission validate my-profile

# Use more permissive profile
mcpm run my-server --permission-profile standard
```

### Debug Mode
```bash
# Enable debug logging
export MCPM_LOG_LEVEL=DEBUG
mcpm run my-server

# Use inspector for real-time debugging
mcpm inspector
```

### Getting Help
```bash
# Built-in help
mcpm --help
mcpm run --help

# Check system status
mcpm health --verbose

# View configuration
mcpm config list
```

## 📝 License

MCPManager is contributed as an **Initial Open Source Project** under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

For enterprise-class features, commercial licensing, and support agreements, please contact the maintainer and author of this project:

**Akram Sheriff**

- **Email**: sheriff.akram.usa@gmail.com 
- **Enterprise Inquiries**: For commercial licensing, support contracts, and enterprise features

### Open Source vs Enterprise Features

**Open Source (Apache 2.0)**:
- Core MCP server management
- Basic security and permissions
- Docker and Podman runtime support
- Standard CLI and API functionality
- Community support

**Enterprise Features** (Commercial License Available):
- Advanced Kubernetes operator with CRDs
- Enterprise-grade security policies
- Commercial support and SLA
- Professional services and consulting
- Custom feature development

## 🤝 Community

- **GitHub**: [https://github.com/akramIOT/mcpmanager](https://github.com/akramIOT/mcpmanager)
- **Issues**: [https://github.com/akramIOT/mcpmanager/issues](https://github.com/akramIOT/mcpmanager/issues)
- **Discussions**: [https://github.com/akramIOT/mcpmanager/discussions](https://github.com/akramIOT/mcpmanager/discussions)

## 🙏 Acknowledgments

MCPManager is built on top of excellent open-source projects:
- [Model Context Protocol (MCP)](https://github.com/modelcontextprotocol)
- [Docker](https://www.docker.com/)
- [Kubernetes](https://kubernetes.io/)
- [OpenTelemetry](https://opentelemetry.io/)
- [Sigstore](https://www.sigstore.dev/)

---

**Made with ❤️ by the MCPManager team**
