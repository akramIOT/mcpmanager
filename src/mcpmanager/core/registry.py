"""MCP server registry management."""

import logging
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import httpx
from mcpmanager.core.models import MCPServerConfig, MCPRegistry as MCPRegistryModel

logger = logging.getLogger(__name__)


class MCPRegistry:
    """MCP server registry manager."""

    def __init__(self, registry_url: Optional[str] = None):
        """Initialize the registry."""
        self.registry_url = registry_url
        self._registry_data: Optional[MCPRegistryModel] = None
        self._cache_path = Path.home() / ".mcpmanager" / "registry_cache.json"
        self._default_registry = self._get_default_registry()

    def _get_default_registry(self) -> MCPRegistryModel:
        """Get the default embedded registry."""
        # Default MCP servers similar to Toolhive's registry
        default_servers = {
            "fetch": MCPServerConfig(
                name="fetch",
                image="mcp/fetch-server:latest",
                description="Fetch website content and extract information",
                tags=["web", "scraping", "content"],
                command=["mcp-fetch-server"],
            ),
            "github": MCPServerConfig(
                name="github",
                image="mcp/github-server:latest",
                description="GitHub repository management and search",
                tags=["github", "git", "repositories"],
                command=["mcp-github-server"],
                secrets=[{"name": "github_token", "target": "GITHUB_TOKEN"}],
            ),
            "filesystem": MCPServerConfig(
                name="filesystem",
                image="mcp/filesystem-server:latest",
                description="Local filesystem operations",
                tags=["filesystem", "files", "local"],
                command=["mcp-filesystem-server"],
                permission_profile={
                    "read": ["/workspace", "/tmp"],
                    "write": ["/tmp"],
                },
            ),
            "brave-search": MCPServerConfig(
                name="brave-search",
                image="mcp/brave-search-server:latest",
                description="Web search using Brave Search API",
                tags=["search", "web", "brave"],
                command=["mcp-brave-search-server"],
                secrets=[{"name": "brave_api_key", "target": "BRAVE_API_KEY"}],
            ),
            "sqlite": MCPServerConfig(
                name="sqlite",
                image="mcp/sqlite-server:latest",
                description="SQLite database operations",
                tags=["database", "sqlite", "sql"],
                command=["mcp-sqlite-server"],
                permission_profile={
                    "read": ["/data"],
                    "write": ["/data"],
                },
            ),
        }

        return MCPRegistryModel(
            version="1.0",
            servers=default_servers,
            last_updated=datetime.now(),
        )

    async def initialize(self) -> None:
        """Initialize the registry."""
        await self._load_registry()

    async def _load_registry(self) -> None:
        """Load registry data."""
        if self.registry_url:
            # Load from remote URL
            try:
                await self._load_remote_registry()
            except Exception as e:
                logger.warning(f"Failed to load remote registry: {e}")
                await self._load_cached_registry()
        else:
            # Use default registry
            self._registry_data = self._default_registry

    async def _load_remote_registry(self) -> None:
        """Load registry from remote URL."""
        async with httpx.AsyncClient() as client:
            response = await client.get(self.registry_url)
            response.raise_for_status()
            
            registry_dict = response.json()
            self._registry_data = MCPRegistryModel(**registry_dict)
            
            # Cache the registry
            await self._save_cache()

    async def _load_cached_registry(self) -> None:
        """Load registry from cache."""
        if self._cache_path.exists():
            try:
                with open(self._cache_path, 'r', encoding='utf-8') as f:
                    registry_dict = json.load(f)
                self._registry_data = MCPRegistryModel(**registry_dict)
                logger.info("Loaded registry from cache")
            except Exception as e:
                logger.warning(f"Failed to load cached registry: {e}")
                self._registry_data = self._default_registry
        else:
            self._registry_data = self._default_registry

    async def _save_cache(self) -> None:
        """Save registry to cache."""
        if self._registry_data:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to dict for JSON serialization
            registry_dict = self._registry_data.model_dump()
            
            with open(self._cache_path, 'w', encoding='utf-8') as f:
                json.dump(registry_dict, f, indent=2, default=str)

    async def get_server_config(self, server_name: str) -> MCPServerConfig:
        """Get configuration for a specific server."""
        if not self._registry_data:
            await self._load_registry()

        if server_name not in self._registry_data.servers:
            raise ValueError(f"Server {server_name} not found in registry")

        return self._registry_data.servers[server_name]

    async def list_servers(self) -> List[MCPServerConfig]:
        """List all available servers."""
        if not self._registry_data:
            await self._load_registry()

        return list(self._registry_data.servers.values())

    async def search_servers(self, query: str) -> List[MCPServerConfig]:
        """Search for servers by name, description, or tags."""
        if not self._registry_data:
            await self._load_registry()

        query_lower = query.lower()
        matching_servers = []

        for server in self._registry_data.servers.values():
            # Search in name
            if query_lower in server.name.lower():
                matching_servers.append(server)
                continue

            # Search in description
            if server.description and query_lower in server.description.lower():
                matching_servers.append(server)
                continue

            # Search in tags
            if any(query_lower in tag.lower() for tag in server.tags):
                matching_servers.append(server)
                continue

        return matching_servers

    async def get_server_info(self, server_name: str) -> Dict[str, Any]:
        """Get detailed information about a server."""
        config = await self.get_server_config(server_name)
        
        return {
            "name": config.name,
            "description": config.description,
            "image": config.image,
            "version": config.version,
            "tags": config.tags,
            "transport": config.transport.value,
            "port": config.port,
            "command": config.command,
            "environment": config.environment,
            "secrets_required": [s.name for s in config.secrets],
            "permission_profile": config.permission_profile,
            "verification": config.verification,
        }

    async def refresh_registry(self) -> bool:
        """Refresh the registry from remote source."""
        if not self.registry_url:
            logger.info("No remote registry URL configured")
            return False

        try:
            await self._load_remote_registry()
            logger.info("Registry refreshed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to refresh registry: {e}")
            return False

    async def add_custom_server(self, config: MCPServerConfig) -> None:
        """Add a custom server to the registry."""
        if not self._registry_data:
            await self._load_registry()

        self._registry_data.servers[config.name] = config
        self._registry_data.last_updated = datetime.now()
        
        # Save to cache
        await self._save_cache()
        logger.info(f"Added custom server {config.name} to registry")

    async def remove_custom_server(self, server_name: str) -> bool:
        """Remove a custom server from the registry."""
        if not self._registry_data:
            await self._load_registry()

        if server_name in self._registry_data.servers:
            del self._registry_data.servers[server_name]
            self._registry_data.last_updated = datetime.now()
            
            # Save to cache
            await self._save_cache()
            logger.info(f"Removed custom server {server_name} from registry")
            return True

        return False

    def is_server_available(self, server_name: str) -> bool:
        """Check if a server is available in the registry."""
        if not self._registry_data:
            return False
        return server_name in self._registry_data.servers

    def get_registry_info(self) -> Dict[str, Any]:
        """Get registry information."""
        if not self._registry_data:
            return {"version": "unknown", "server_count": 0, "last_updated": None}

        return {
            "version": self._registry_data.version,
            "server_count": len(self._registry_data.servers),
            "last_updated": self._registry_data.last_updated,
            "registry_url": self.registry_url,
            "cache_path": str(self._cache_path),
        }

    async def validate_server_config(self, config: MCPServerConfig) -> List[str]:
        """Validate a server configuration."""
        errors = []

        # Basic validation
        if not config.name:
            errors.append("Server name is required")

        if not config.image:
            errors.append("Server image is required")

        # Validate transport
        if config.transport not in ["stdio", "sse"]:
            errors.append(f"Invalid transport type: {config.transport}")

        # Validate port if SSE transport
        if config.transport == "sse" and not config.port:
            errors.append("Port is required for SSE transport")

        # Validate command
        if not config.command:
            errors.append("Command is required")

        return errors