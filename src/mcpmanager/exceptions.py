"""Custom exceptions for MCPManager."""


class MCPManagerError(Exception):
    """Base exception for MCPManager."""
    pass


class DockerNotAvailableError(MCPManagerError):
    """Docker is not available or accessible."""
    pass


class ConfigurationError(MCPManagerError):
    """Configuration is invalid or missing."""
    pass


class SecretsError(MCPManagerError):
    """Secrets management error."""
    pass


class RegistryError(MCPManagerError):
    """Registry operation error."""
    pass


class TransportError(MCPManagerError):
    """Transport layer error."""
    pass


class AuthenticationError(MCPManagerError):
    """Authentication failed."""
    pass


class AuthorizationError(MCPManagerError):
    """Authorization failed."""
    pass


class DiscoveryError(MCPManagerError):
    """Client discovery error."""
    pass