"""MCPManager - Secure MCP Server Management with Dynamic Discovery."""

__version__ = "0.1.0"
__author__ = "MCPManager Contributors"
__license__ = "Apache-2.0"

from mcpmanager.core.manager import MCPManager
from mcpmanager.core.discovery import MCPDiscovery
from mcpmanager.core.registry import MCPRegistry
from mcpmanager.exceptions import (
    MCPManagerError,
    DockerNotAvailableError,
    ConfigurationError,
    SecretsError,
    RegistryError,
    TransportError,
    AuthenticationError,
    AuthorizationError,
    DiscoveryError,
)

__all__ = [
    "MCPManager",
    "MCPDiscovery", 
    "MCPRegistry",
    "MCPManagerError",
    "DockerNotAvailableError",
    "ConfigurationError",
    "SecretsError",
    "RegistryError",
    "TransportError",
    "AuthenticationError",
    "AuthorizationError",
    "DiscoveryError",
]