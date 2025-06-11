"""Data models for MCPManager."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class TransportType(str, Enum):
    """Transport protocol types."""
    STDIO = "stdio"
    SSE = "sse"
    PROXY = "proxy"
    TRANSPARENT = "transparent"


class ContainerState(str, Enum):
    """Container states."""
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    EXITED = "exited"
    PAUSED = "paused"
    RESTARTING = "restarting"


class SecretsProvider(str, Enum):
    """Secrets provider types."""
    NONE = "none"
    ENCRYPTED = "encrypted"
    ONEPASSWORD = "1password"


class MCPClientType(str, Enum):
    """Supported MCP client types."""
    VSCODE = "vscode"
    CURSOR = "cursor"
    ROO_CODE = "roo-code"
    CLAUDE_CODE = "claude-code"
    CLINE = "cline"
    CONTINUE = "continue"


class PortMapping(BaseModel):
    """Port mapping configuration."""
    container_port: int
    host_port: int
    protocol: str = "tcp"


class Mount(BaseModel):
    """Volume mount configuration."""
    source: str
    target: str
    read_only: bool = True


class NetworkPermissions(BaseModel):
    """Network permission configuration."""
    insecure_allow_all: bool = False
    allow_transport: List[str] = Field(default_factory=list)
    allow_host: List[str] = Field(default_factory=list)
    allow_port: List[int] = Field(default_factory=list)


class PermissionProfile(BaseModel):
    """Container permission profile."""
    read: List[str] = Field(default_factory=list)
    write: List[str] = Field(default_factory=list)
    network: Optional[Dict[str, NetworkPermissions]] = None


class SecretReference(BaseModel):
    """Secret reference configuration."""
    name: str
    target: str


class OIDCConfig(BaseModel):
    """OIDC authentication configuration."""
    issuer_url: str
    client_id: str
    client_secret: Optional[str] = None
    scopes: List[str] = Field(default_factory=lambda: ["openid", "profile"])


class TelemetryConfig(BaseModel):
    """Telemetry configuration."""
    enabled: bool = False
    endpoint: Optional[str] = None
    enable_prometheus_metrics: bool = False


class MCPServerConfig(BaseModel):
    """MCP server configuration."""
    name: str
    image: str
    description: Optional[str] = None
    version: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    transport: TransportType = TransportType.STDIO
    port: Optional[int] = None
    target_port: Optional[int] = None
    command: List[str] = Field(default_factory=list)
    environment: Dict[str, str] = Field(default_factory=dict)
    secrets: List[SecretReference] = Field(default_factory=list)
    permission_profile: Optional[PermissionProfile] = None
    verification: Optional[Dict[str, Any]] = None


class ContainerInfo(BaseModel):
    """Container information."""
    id: str
    name: str
    image: str
    status: str
    state: ContainerState
    created: datetime
    labels: Dict[str, str] = Field(default_factory=dict)
    ports: List[PortMapping] = Field(default_factory=list)


class MCPServerInstance(BaseModel):
    """Running MCP server instance."""
    name: str
    container_id: str
    config: MCPServerConfig
    url: Optional[str] = None
    created_at: datetime
    status: ContainerState


class ClientConfig(BaseModel):
    """Client configuration."""
    client_type: MCPClientType
    config_path: str
    servers: Dict[str, str] = Field(default_factory=dict)


class DiscoveredClient(BaseModel):
    """Discovered MCP client."""
    client_type: MCPClientType
    installed: bool
    registered: bool
    config_path: Optional[str] = None


class VerificationConfig(BaseModel):
    """Image verification configuration."""
    enabled: bool = False
    methods: List[Dict[str, Any]] = Field(default_factory=list)
    policy: Optional[Dict[str, Any]] = None


class ConfigData(BaseModel):
    """Main configuration data."""
    auto_discovery_enabled: bool = False
    registry_url: Optional[str] = None
    ca_cert_path: Optional[str] = None
    secrets_provider: SecretsProvider = SecretsProvider.NONE
    registered_clients: List[str] = Field(default_factory=list)
    oidc: Optional[OIDCConfig] = None
    telemetry: Optional[TelemetryConfig] = None
    verification: Optional[VerificationConfig] = None


class MCPRegistry(BaseModel):
    """MCP registry data."""
    version: str = "1.0"
    servers: Dict[str, MCPServerConfig] = Field(default_factory=dict)
    last_updated: Optional[datetime] = None