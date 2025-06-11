"""Base runtime interface and types."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime

from mcpmanager.exceptions import MCPManagerError
from mcpmanager.core.models import ContainerInfo, PermissionProfile


class RuntimeError(MCPManagerError):
    """Runtime-specific error."""
    pass


class RuntimeType(str, Enum):
    """Supported runtime types."""
    DOCKER = "docker"
    PODMAN = "podman"
    KUBERNETES = "kubernetes"


@dataclass
class RuntimeInfo:
    """Runtime information."""
    name: str
    type: RuntimeType
    version: str
    available: bool
    status: str
    capabilities: List[str]
    config: Dict[str, Any]


@dataclass  
class ContainerSpec:
    """Container specification for runtime-agnostic operations."""
    name: str
    image: str
    command: Optional[List[str]] = None
    environment: Optional[Dict[str, str]] = None
    labels: Optional[Dict[str, str]] = None
    port_bindings: Optional[Dict[str, Union[int, str]]] = None
    volumes: Optional[Dict[str, Dict[str, str]]] = None
    permission_profile: Optional[PermissionProfile] = None
    network_mode: str = "bridge"
    restart_policy: Optional[Dict[str, Any]] = None
    resources: Optional[Dict[str, Any]] = None
    runtime_config: Optional[Dict[str, Any]] = None


class BaseRuntime(ABC):
    """Base class for container runtimes."""

    def __init__(self, name: str, runtime_type: RuntimeType):
        """Initialize runtime."""
        self.name = name
        self.runtime_type = runtime_type
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the runtime."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup runtime resources."""
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if runtime is available."""
        pass

    @abstractmethod
    async def get_runtime_info(self) -> RuntimeInfo:
        """Get runtime information."""
        pass

    @abstractmethod
    async def create_container(self, spec: ContainerSpec) -> str:
        """Create a container and return its ID."""
        pass

    @abstractmethod
    async def start_container(self, container_id: str) -> None:
        """Start a container."""
        pass

    @abstractmethod
    async def stop_container(self, container_id: str, timeout: int = 30) -> None:
        """Stop a container."""
        pass

    @abstractmethod
    async def remove_container(self, container_id: str, force: bool = True) -> None:
        """Remove a container."""
        pass

    @abstractmethod
    async def list_containers(
        self, all: bool = False, filters: Optional[Dict[str, Any]] = None
    ) -> List[ContainerInfo]:
        """List containers."""
        pass

    @abstractmethod
    async def get_container_info(self, container_id: str) -> ContainerInfo:
        """Get container information."""
        pass

    @abstractmethod
    async def get_container_logs(
        self,
        container_id: str,
        follow: bool = False,
        tail: int = 100,
        since: Optional[str] = None,
    ) -> str:
        """Get container logs."""
        pass

    @abstractmethod
    async def is_container_running(self, container_id: str) -> bool:
        """Check if container is running."""
        pass

    @abstractmethod
    async def exec_in_container(
        self,
        container_id: str,
        command: Union[str, List[str]],
        workdir: Optional[str] = None,
        user: Optional[str] = None,
    ) -> tuple[int, str]:
        """Execute command in container."""
        pass

    @abstractmethod
    async def pull_image(self, image: str, tag: str = "latest") -> None:
        """Pull an image."""
        pass

    @abstractmethod
    async def image_exists(self, image: str) -> bool:
        """Check if image exists."""
        pass

    @abstractmethod
    async def build_image(
        self,
        path: str,
        tag: str,
        dockerfile: str = "Dockerfile",
        build_args: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build an image."""
        pass

    # Optional methods for advanced features
    async def get_container_stats(self, container_id: str) -> Dict[str, Any]:
        """Get container statistics."""
        raise NotImplementedError(f"{self.runtime_type} doesn't support container stats")

    async def inspect_container(self, container_id: str) -> Dict[str, Any]:
        """Inspect container."""
        raise NotImplementedError(f"{self.runtime_type} doesn't support container inspection")

    async def restart_container(self, container_id: str, timeout: int = 30) -> None:
        """Restart a container."""
        await self.stop_container(container_id, timeout)
        await self.start_container(container_id)

    async def pause_container(self, container_id: str) -> None:
        """Pause a container."""
        raise NotImplementedError(f"{self.runtime_type} doesn't support pause")

    async def unpause_container(self, container_id: str) -> None:
        """Unpause a container."""
        raise NotImplementedError(f"{self.runtime_type} doesn't support unpause")

    def get_capabilities(self) -> List[str]:
        """Get runtime capabilities."""
        base_capabilities = [
            "create_container",
            "start_container", 
            "stop_container",
            "remove_container",
            "list_containers",
            "get_container_info",
            "get_container_logs",
            "exec_in_container",
            "pull_image",
            "build_image",
        ]
        
        # Check for optional capabilities
        optional_capabilities = []
        
        try:
            # Test if stats are supported
            self.__class__.get_container_stats
            if self.__class__.get_container_stats != BaseRuntime.get_container_stats:
                optional_capabilities.append("container_stats")
        except:
            pass
            
        try:
            # Test if pause is supported
            self.__class__.pause_container
            if self.__class__.pause_container != BaseRuntime.pause_container:
                optional_capabilities.append("pause_container")
        except:
            pass

        return base_capabilities + optional_capabilities