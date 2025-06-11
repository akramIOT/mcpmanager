"""Main MCP server manager."""

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from mcpmanager.core.models import (
    MCPServerConfig,
    MCPServerInstance,
    ContainerInfo,
    ContainerState,
    TransportType,
)
from mcpmanager.container.docker_client import DockerClient
from mcpmanager.runtime.manager import RuntimeManager
from mcpmanager.runtime.base import ContainerSpec
from mcpmanager.transport.factory import TransportFactory
from mcpmanager.secrets.manager import SecretsManager
from mcpmanager.config.manager import ConfigManager
from mcpmanager.core.registry import MCPRegistry
from mcpmanager.core.protocol_schemes import get_protocol_processor
from mcpmanager.inspector import MCPInspector
from mcpmanager.verification import ImageVerifier
from mcpmanager.permissions import PermissionManager

# Optional telemetry imports
try:
    from mcpmanager.telemetry import TelemetryManager, MetricsCollector, TracingManager
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False
    TelemetryManager = None
    MetricsCollector = None
    TracingManager = None

logger = logging.getLogger(__name__)


class MCPManager:
    """Main MCP server manager."""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        docker_client: Optional[DockerClient] = None,
        secrets_manager: Optional[SecretsManager] = None,
        registry: Optional[MCPRegistry] = None,
        runtime_manager: Optional[RuntimeManager] = None,
        image_verifier: Optional[ImageVerifier] = None,
        permission_manager: Optional[PermissionManager] = None,
        telemetry_manager: Optional[TelemetryManager] = None,
    ):
        """Initialize the MCP manager."""
        self.config_manager = config_manager or ConfigManager()
        self.docker_client = docker_client or DockerClient()  # Keep for backward compatibility
        self.runtime_manager = runtime_manager or RuntimeManager()
        self.secrets_manager = secrets_manager or SecretsManager(self.config_manager)
        self.registry = registry or MCPRegistry()
        self.transport_factory = TransportFactory()
        self.protocol_processor = get_protocol_processor()
        self.inspector = MCPInspector(self.docker_client, self)
        self.image_verifier = image_verifier or ImageVerifier()
        self.permission_manager = permission_manager or PermissionManager(self.config_manager.config_dir / "permissions")
        
        # Initialize telemetry (if available)
        if TELEMETRY_AVAILABLE and TelemetryManager:
            config = self.config_manager._config_data.telemetry if self.config_manager._config_data else None
            self.telemetry_manager = telemetry_manager or TelemetryManager(config)
            self.metrics_collector = MetricsCollector(self.telemetry_manager) if self.telemetry_manager.is_enabled() else None
            self.tracing_manager = TracingManager(self.telemetry_manager) if self.telemetry_manager.is_enabled() else None
        else:
            self.telemetry_manager = None
            self.metrics_collector = None
            self.tracing_manager = None
        
        self._running_servers: Dict[str, MCPServerInstance] = {}

    async def initialize(self) -> None:
        """Initialize the manager."""
        # Initialize telemetry first (if available)
        if self.telemetry_manager:
            await self.telemetry_manager.initialize()
        
        await self.docker_client.initialize()  # Keep for backward compatibility
        await self.runtime_manager.initialize()
        await self.secrets_manager.initialize()
        await self.registry.initialize()

    async def run_server(
        self,
        server_name: str,
        config: Optional[MCPServerConfig] = None,
        secrets: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> MCPServerInstance:
        """Run an MCP server."""
        transport_type = kwargs.get('transport', 'stdio')
        
        # Use telemetry context managers if available
        span_ctx = (self.tracing_manager.trace_server_lifecycle("start", server_name) 
                   if self.tracing_manager else contextlib.nullcontext())
        metrics_ctx = (self.metrics_collector.time_server_start(server_name, transport_type)
                      if self.metrics_collector else contextlib.nullcontext())
        
        with span_ctx, metrics_ctx:
            if server_name in self._running_servers:
                raise ValueError(f"Server {server_name} is already running")

            # Handle protocol schemes
            if self.protocol_processor.is_protocol_scheme(server_name):
                logger.info(f"Processing protocol scheme: {server_name}")
                image_tag = await self.protocol_processor.build_image_from_scheme(
                    server_name, self.docker_client
                )
                
                # Create config for protocol scheme
                config = MCPServerConfig(
                    name=f"scheme-{server_name.split('://', 1)[0]}-{hash(server_name) % 10000}",
                    image=image_tag,
                    transport=kwargs.get('transport', TransportType.STDIO),
                    port=kwargs.get('port'),
                    target_port=kwargs.get('target_port'),
                    environment=kwargs.get('environment', {}),
                    command=kwargs.get('command', []),
                )
                server_name = config.name

            # Get server config from registry if not provided
            elif config is None:
                config = await self.registry.get_server_config(server_name)

            # Process secrets
            env_vars = config.environment.copy()
            if secrets:
                for secret_name, target_env in secrets.items():
                    secret_value = await self.secrets_manager.get_secret(secret_name)
                    env_vars[target_env] = secret_value

            # Process secret references from config
            for secret_ref in config.secrets:
                secret_value = await self.secrets_manager.get_secret(secret_ref.name)
                env_vars[secret_ref.target] = secret_value

            # Verify image if verification is enabled
            verification_config = self.config_manager.get_verification_config()
            if verification_config and verification_config.get("enabled", False):
                logger.info(f"Verifying image: {config.image}")
                verification_result = await self.image_verifier.verify_image(
                    config.image, verification_config
                )
                
                if not verification_result.verified:
                    error_msg = f"Image verification failed for {config.image}: {verification_result.policy_violations}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                
                logger.info(f"Image verification passed for {config.image}")

            # Process permission profile
            runtime_config = {}
            if config.permission_profile:
                # Check if it's an advanced permission profile name
                advanced_profile = await self.permission_manager.get_profile(config.permission_profile)
                if advanced_profile:
                    # Validate the profile
                    warnings = await self.permission_manager.validate_profile(advanced_profile)
                    if warnings:
                        for warning in warnings:
                            logger.warning(f"Permission profile warning: {warning}")
                    
                    # Convert to runtime configuration
                    runtime_config = self.permission_manager.get_runtime_config(advanced_profile)
                    logger.info(f"Using advanced permission profile: {config.permission_profile}")
                else:
                    logger.warning(f"Advanced permission profile not found: {config.permission_profile}")

            # Create container spec
            container_name = f"mcpm-{server_name}"
            container_spec = ContainerSpec(
                name=container_name,
                image=config.image,
                command=config.command,
                environment=env_vars,
                labels={
                    "mcpmanager": "true",
                    "mcpmanager.server": server_name,
                    "mcpmanager.transport": config.transport.value,
                    "mcpmanager.permission_profile": config.permission_profile or "default",
                },
                port_bindings={f"{config.port}/tcp": config.port} if config.port else {},
                permission_profile=config.permission_profile,
                runtime_config=runtime_config,
            )

            # Create and start container using runtime manager
            container_id = await self.runtime_manager.create_container(container_spec)
            await self.runtime_manager.start_container(container_id)

            # Create transport
            transport = await self.transport_factory.create_transport(
                transport_type=config.transport,
                container_id=container_id,
                port=config.port,
                target_port=config.target_port,
            )

            # Start transport
            await transport.start()

            # Create server instance
            instance = MCPServerInstance(
                name=server_name,
                container_id=container_id,
                config=config,
                url=transport.get_url() if hasattr(transport, "get_url") else None,
                created_at=datetime.now(),
                status=ContainerState.RUNNING,
            )

            self._running_servers[server_name] = instance
            logger.info(f"MCP server {server_name} started successfully")

            # Record telemetry
            if self.metrics_collector:
                runtime = getattr(self.runtime_manager, 'current_runtime', 'unknown')
                self.metrics_collector.record_server_created(server_name, config.transport.value, runtime)
                self.metrics_collector.record_container_created(config.image, runtime)

            return instance

    async def stop_server(self, server_name: str) -> None:
        """Stop an MCP server."""
        metrics_ctx = (self.metrics_collector.time_server_stop(server_name)
                      if self.metrics_collector else contextlib.nullcontext())
        
        with metrics_ctx:
            if server_name not in self._running_servers:
                raise ValueError(f"Server {server_name} is not running")

            instance = self._running_servers[server_name]

            # Stop container
            await self.runtime_manager.stop_container(instance.container_id)

            # Remove from running servers
            del self._running_servers[server_name]
            logger.info(f"MCP server {server_name} stopped successfully")
            
            # Record telemetry
            if self.metrics_collector:
                runtime = getattr(self.runtime_manager, 'current_runtime', 'unknown')
                self.metrics_collector.record_server_stopped(server_name, instance.config.transport.value, runtime)

    async def remove_server(self, server_name: str, force: bool = False) -> None:
        """Remove an MCP server."""
        if server_name in self._running_servers:
            if not force:
                raise ValueError(
                    f"Server {server_name} is running. Use force=True to stop and remove"
                )
            await self.stop_server(server_name)

        # Find and remove container
        containers = await self.runtime_manager.list_containers(all=True)
        for container in containers:
            if container.labels.get("mcpmanager.server") == server_name:
                await self.runtime_manager.remove_container(container.id)
                logger.info(f"MCP server {server_name} removed successfully")
                return

        logger.warning(f"No container found for server {server_name}")

    async def restart_server(self, server_name: str) -> MCPServerInstance:
        """Restart an MCP server."""
        if server_name not in self._running_servers:
            raise ValueError(f"Server {server_name} is not running")

        instance = self._running_servers[server_name]
        config = instance.config

        # Stop the server
        await self.stop_server(server_name)

        # Start it again
        return await self.run_server(server_name, config)

    async def list_servers(self, all: bool = False) -> List[MCPServerInstance]:
        """List MCP servers."""
        if not all:
            return list(self._running_servers.values())

        # Get all containers with mcpmanager label
        containers = await self.runtime_manager.list_containers(all=True)
        instances = []

        for container in containers:
            if container.labels.get("mcpmanager") == "true":
                server_name = container.labels.get("mcpmanager.server", "unknown")
                
                # Try to get config from registry
                try:
                    config = await self.registry.get_server_config(server_name)
                except Exception:
                    # Create minimal config if not found
                    config = MCPServerConfig(
                        name=server_name,
                        image=container.image,
                    )

                instance = MCPServerInstance(
                    name=server_name,
                    container_id=container.id,
                    config=config,
                    created_at=container.created,
                    status=ContainerState(container.state.lower()),
                )
                instances.append(instance)

        return instances

    async def get_server_logs(
        self, server_name: str, follow: bool = False, tail: int = 100
    ) -> str:
        """Get logs for an MCP server."""
        if server_name not in self._running_servers:
            # Try to find container by name
            containers = await self.runtime_manager.list_containers(all=True)
            container_id = None
            for container in containers:
                if container.labels.get("mcpmanager.server") == server_name:
                    container_id = container.id
                    break
            
            if not container_id:
                raise ValueError(f"Server {server_name} not found")
        else:
            container_id = self._running_servers[server_name].container_id

        return await self.runtime_manager.get_container_logs(
            container_id, follow=follow, tail=tail
        )

    async def get_server_status(self, server_name: str) -> Optional[MCPServerInstance]:
        """Get status of an MCP server."""
        if server_name in self._running_servers:
            instance = self._running_servers[server_name]
            # Update status from container
            container_info = await self.runtime_manager.get_container_info(
                instance.container_id
            )
            instance.status = ContainerState(container_info.state.lower())
            return instance

        # Check if container exists but not in running servers
        containers = await self.runtime_manager.list_containers(all=True)
        for container in containers:
            if container.labels.get("mcpmanager.server") == server_name:
                try:
                    config = await self.registry.get_server_config(server_name)
                except Exception:
                    config = MCPServerConfig(name=server_name, image=container.image)

                return MCPServerInstance(
                    name=server_name,
                    container_id=container.id,
                    config=config,
                    created_at=container.created,
                    status=ContainerState(container.state.lower()),
                )

        return None

    async def search_servers(self, query: str) -> List[MCPServerConfig]:
        """Search for servers in the registry."""
        return await self.registry.search_servers(query)

    async def verify_image(self, image: str, verification_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Verify an image using the configured verification system."""
        if not verification_config:
            verification_config = self.config_manager.get_verification_config()
        
        result = await self.image_verifier.verify_image(image, verification_config)
        return result.to_dict()

    async def get_image_vulnerabilities(self, image: str) -> Dict[str, Any]:
        """Get vulnerability information for an image."""
        return await self.image_verifier.get_image_vulnerabilities(image)

    # Permission management methods
    async def create_permission_profile(
        self, 
        name: str, 
        template: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new permission profile."""
        if template:
            profile = await self.permission_manager.create_profile_from_template(
                template, name, overrides
            )
        else:
            from mcpmanager.permissions.profiles import AdvancedPermissionProfile
            profile_data = {"name": name}
            if overrides:
                profile_data.update(overrides)
            profile = AdvancedPermissionProfile(**profile_data)
        
        await self.permission_manager.save_profile(profile)
        return profile.model_dump()

    async def get_permission_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a permission profile by name."""
        profile = await self.permission_manager.get_profile(name)
        return profile.model_dump() if profile else None

    async def list_permission_profiles(self) -> List[str]:
        """List all available permission profiles."""
        return await self.permission_manager.list_profiles()

    async def delete_permission_profile(self, name: str) -> bool:
        """Delete a permission profile."""
        return await self.permission_manager.delete_profile(name)

    async def validate_permission_profile(self, name: str) -> List[str]:
        """Validate a permission profile and return warnings."""
        profile = await self.permission_manager.get_profile(name)
        if not profile:
            return [f"Profile not found: {name}"]
        return await self.permission_manager.validate_profile(profile)

    async def get_permission_recommendations(self, use_case: str) -> List[str]:
        """Get permission profile recommendations for a use case."""
        return await self.permission_manager.get_profile_recommendations(use_case)

    async def cleanup(self) -> None:
        """Cleanup resources."""
        # Stop all running servers
        for server_name in list(self._running_servers.keys()):
            try:
                await self.stop_server(server_name)
            except Exception as e:
                logger.error(f"Error stopping server {server_name}: {e}")

        # Cleanup docker client and runtime manager
        if self.docker_client:
            await self.docker_client.cleanup()
        if self.runtime_manager:
            await self.runtime_manager.cleanup()
        
        # Shutdown telemetry
        if self.telemetry_manager:
            await self.telemetry_manager.shutdown()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.cleanup()