"""Runtime manager for coordinating multiple container runtimes."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union

from .base import BaseRuntime, RuntimeType, RuntimeInfo, ContainerSpec, RuntimeError
from .docker_runtime import DockerRuntime
from .podman_runtime import PodmanRuntime
from .kubernetes_runtime import KubernetesRuntime
from mcpmanager.core.models import ContainerInfo

logger = logging.getLogger(__name__)


class RuntimeManager:
    """Manager for multiple container runtimes."""

    def __init__(self, preferred_runtime: Optional[RuntimeType] = None):
        """Initialize runtime manager."""
        self.preferred_runtime = preferred_runtime
        self._runtimes: Dict[RuntimeType, BaseRuntime] = {}
        self._initialized = False
        self._active_runtime: Optional[BaseRuntime] = None

    async def initialize(self) -> None:
        """Initialize all available runtimes."""
        if self._initialized:
            return

        # Initialize all runtime types
        runtime_classes = {
            RuntimeType.DOCKER: DockerRuntime,
            RuntimeType.PODMAN: PodmanRuntime,
            RuntimeType.KUBERNETES: lambda: KubernetesRuntime(),
        }

        for runtime_type, runtime_class in runtime_classes.items():
            try:
                runtime = runtime_class()
                if await runtime.is_available():
                    await runtime.initialize()
                    self._runtimes[runtime_type] = runtime
                    logger.info(f"Initialized {runtime_type.value} runtime")
                else:
                    logger.debug(f"{runtime_type.value} runtime not available")
            except Exception as e:
                logger.warning(f"Failed to initialize {runtime_type.value} runtime: {e}")

        if not self._runtimes:
            raise RuntimeError("No container runtimes available")

        # Set active runtime
        await self._select_active_runtime()
        self._initialized = True
        logger.info(f"Runtime manager initialized with {len(self._runtimes)} runtimes")

    async def _select_active_runtime(self) -> None:
        """Select the active runtime based on preferences and availability."""
        if self.preferred_runtime and self.preferred_runtime in self._runtimes:
            self._active_runtime = self._runtimes[self.preferred_runtime]
            logger.info(f"Using preferred runtime: {self.preferred_runtime.value}")
            return

        # Priority order: Docker > Podman > Kubernetes
        priority_order = [RuntimeType.DOCKER, RuntimeType.PODMAN, RuntimeType.KUBERNETES]
        
        for runtime_type in priority_order:
            if runtime_type in self._runtimes:
                self._active_runtime = self._runtimes[runtime_type]
                logger.info(f"Selected runtime: {runtime_type.value}")
                return

        raise RuntimeError("No suitable runtime found")

    async def cleanup(self) -> None:
        """Cleanup all runtimes."""
        for runtime in self._runtimes.values():
            try:
                await runtime.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up runtime {runtime.runtime_type}: {e}")
        
        self._runtimes.clear()
        self._active_runtime = None
        self._initialized = False
        logger.info("Runtime manager cleaned up")

    def get_active_runtime(self) -> BaseRuntime:
        """Get the currently active runtime."""
        if not self._active_runtime:
            raise RuntimeError("No active runtime available")
        return self._active_runtime

    def get_runtime(self, runtime_type: RuntimeType) -> Optional[BaseRuntime]:
        """Get a specific runtime by type."""
        return self._runtimes.get(runtime_type)

    def get_available_runtimes(self) -> List[RuntimeType]:
        """Get list of available runtime types."""
        return list(self._runtimes.keys())

    async def get_runtime_info(self, runtime_type: Optional[RuntimeType] = None) -> Union[RuntimeInfo, List[RuntimeInfo]]:
        """Get runtime information."""
        if runtime_type:
            runtime = self._runtimes.get(runtime_type)
            if not runtime:
                raise RuntimeError(f"Runtime {runtime_type.value} not available")
            return await runtime.get_runtime_info()
        else:
            # Return info for all runtimes
            info_list = []
            for runtime in self._runtimes.values():
                try:
                    info = await runtime.get_runtime_info()
                    info_list.append(info)
                except Exception as e:
                    logger.warning(f"Failed to get info for {runtime.runtime_type}: {e}")
            return info_list

    async def switch_runtime(self, runtime_type: RuntimeType) -> None:
        """Switch to a different runtime."""
        if runtime_type not in self._runtimes:
            raise RuntimeError(f"Runtime {runtime_type.value} not available")
        
        self._active_runtime = self._runtimes[runtime_type]
        logger.info(f"Switched to runtime: {runtime_type.value}")

    async def auto_select_runtime(self, spec: ContainerSpec) -> RuntimeType:
        """Automatically select the best runtime for a container spec."""
        # Simple heuristics for runtime selection
        
        # If Kubernetes features are needed
        if (spec.resources and 
            ("cpu_limit" in spec.resources or "memory_limit" in spec.resources) and
            RuntimeType.KUBERNETES in self._runtimes):
            return RuntimeType.KUBERNETES
        
        # If rootless execution is preferred and Podman is available
        if (spec.permission_profile and 
            not spec.permission_profile.network and
            RuntimeType.PODMAN in self._runtimes):
            return RuntimeType.PODMAN
        
        # Default to Docker if available
        if RuntimeType.DOCKER in self._runtimes:
            return RuntimeType.DOCKER
        
        # Fallback to first available
        return list(self._runtimes.keys())[0]

    # Delegate container operations to active runtime
    async def create_container(self, spec: ContainerSpec, runtime_type: Optional[RuntimeType] = None) -> str:
        """Create a container using specified or active runtime."""
        if runtime_type:
            runtime = self._runtimes.get(runtime_type)
            if not runtime:
                raise RuntimeError(f"Runtime {runtime_type.value} not available")
        else:
            # Auto-select runtime based on spec
            selected_type = await self.auto_select_runtime(spec)
            runtime = self._runtimes[selected_type]
        
        return await runtime.create_container(spec)

    async def start_container(self, container_id: str, runtime_type: Optional[RuntimeType] = None) -> None:
        """Start a container."""
        runtime = self._get_runtime_for_operation(runtime_type)
        await runtime.start_container(container_id)

    async def stop_container(self, container_id: str, timeout: int = 30, runtime_type: Optional[RuntimeType] = None) -> None:
        """Stop a container."""
        runtime = self._get_runtime_for_operation(runtime_type)
        await runtime.stop_container(container_id, timeout)

    async def remove_container(self, container_id: str, force: bool = True, runtime_type: Optional[RuntimeType] = None) -> None:
        """Remove a container."""
        runtime = self._get_runtime_for_operation(runtime_type)
        await runtime.remove_container(container_id, force)

    async def list_containers(
        self, 
        all: bool = False, 
        filters: Optional[Dict[str, Any]] = None,
        runtime_type: Optional[RuntimeType] = None
    ) -> List[ContainerInfo]:
        """List containers from specified or all runtimes."""
        if runtime_type:
            runtime = self._runtimes.get(runtime_type)
            if not runtime:
                return []
            return await runtime.list_containers(all, filters)
        else:
            # List from all runtimes
            all_containers = []
            for runtime in self._runtimes.values():
                try:
                    containers = await runtime.list_containers(all, filters)
                    # Add runtime type to labels for identification
                    for container in containers:
                        container.labels["mcpmanager.runtime"] = runtime.runtime_type.value
                    all_containers.extend(containers)
                except Exception as e:
                    logger.warning(f"Failed to list containers from {runtime.runtime_type}: {e}")
            return all_containers

    async def get_container_info(self, container_id: str, runtime_type: Optional[RuntimeType] = None) -> ContainerInfo:
        """Get container information."""
        if runtime_type:
            runtime = self._runtimes.get(runtime_type)
            if not runtime:
                raise RuntimeError(f"Runtime {runtime_type.value} not available")
            return await runtime.get_container_info(container_id)
        else:
            # Try all runtimes to find the container
            for runtime in self._runtimes.values():
                try:
                    return await runtime.get_container_info(container_id)
                except RuntimeError:
                    continue
            raise RuntimeError(f"Container {container_id} not found in any runtime")

    async def get_container_logs(
        self,
        container_id: str,
        follow: bool = False,
        tail: int = 100,
        since: Optional[str] = None,
        runtime_type: Optional[RuntimeType] = None
    ) -> str:
        """Get container logs."""
        runtime = await self._find_container_runtime(container_id, runtime_type)
        return await runtime.get_container_logs(container_id, follow, tail, since)

    async def is_container_running(self, container_id: str, runtime_type: Optional[RuntimeType] = None) -> bool:
        """Check if container is running."""
        try:
            runtime = await self._find_container_runtime(container_id, runtime_type)
            return await runtime.is_container_running(container_id)
        except RuntimeError:
            return False

    async def exec_in_container(
        self,
        container_id: str,
        command: Union[str, List[str]],
        workdir: Optional[str] = None,
        user: Optional[str] = None,
        runtime_type: Optional[RuntimeType] = None
    ) -> tuple[int, str]:
        """Execute command in container."""
        runtime = await self._find_container_runtime(container_id, runtime_type)
        return await runtime.exec_in_container(container_id, command, workdir, user)

    async def pull_image(self, image: str, tag: str = "latest", runtime_type: Optional[RuntimeType] = None) -> None:
        """Pull an image."""
        runtime = self._get_runtime_for_operation(runtime_type)
        await runtime.pull_image(image, tag)

    async def image_exists(self, image: str, runtime_type: Optional[RuntimeType] = None) -> bool:
        """Check if image exists."""
        runtime = self._get_runtime_for_operation(runtime_type)
        return await runtime.image_exists(image)

    async def build_image(
        self,
        path: str,
        tag: str,
        dockerfile: str = "Dockerfile",
        build_args: Optional[Dict[str, str]] = None,
        runtime_type: Optional[RuntimeType] = None
    ) -> str:
        """Build an image."""
        runtime = self._get_runtime_for_operation(runtime_type)
        return await runtime.build_image(path, tag, dockerfile, build_args)

    # Advanced operations (if supported by runtime)
    async def get_container_stats(self, container_id: str, runtime_type: Optional[RuntimeType] = None) -> Dict[str, Any]:
        """Get container statistics."""
        runtime = await self._find_container_runtime(container_id, runtime_type)
        return await runtime.get_container_stats(container_id)

    async def inspect_container(self, container_id: str, runtime_type: Optional[RuntimeType] = None) -> Dict[str, Any]:
        """Inspect container."""
        runtime = await self._find_container_runtime(container_id, runtime_type)
        return await runtime.inspect_container(container_id)

    def _get_runtime_for_operation(self, runtime_type: Optional[RuntimeType]) -> BaseRuntime:
        """Get runtime for operation."""
        if runtime_type:
            runtime = self._runtimes.get(runtime_type)
            if not runtime:
                raise RuntimeError(f"Runtime {runtime_type.value} not available")
            return runtime
        else:
            return self.get_active_runtime()

    async def _find_container_runtime(self, container_id: str, runtime_type: Optional[RuntimeType]) -> BaseRuntime:
        """Find which runtime manages a container."""
        if runtime_type:
            runtime = self._runtimes.get(runtime_type)
            if not runtime:
                raise RuntimeError(f"Runtime {runtime_type.value} not available")
            return runtime
        else:
            # Try to find container in all runtimes
            for runtime in self._runtimes.values():
                try:
                    await runtime.get_container_info(container_id)
                    return runtime
                except RuntimeError:
                    continue
            raise RuntimeError(f"Container {container_id} not found in any runtime")

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all runtimes."""
        health_status = {
            "overall": "healthy",
            "runtimes": {},
            "active_runtime": self._active_runtime.runtime_type.value if self._active_runtime else None
        }

        for runtime_type, runtime in self._runtimes.items():
            try:
                available = await runtime.is_available()
                info = await runtime.get_runtime_info()
                health_status["runtimes"][runtime_type.value] = {
                    "available": available,
                    "status": info.status,
                    "version": info.version
                }
            except Exception as e:
                health_status["runtimes"][runtime_type.value] = {
                    "available": False,
                    "status": "error",
                    "error": str(e)
                }
                health_status["overall"] = "degraded"

        if not self._runtimes:
            health_status["overall"] = "unhealthy"

        return health_status

    def get_runtime_capabilities(self, runtime_type: Optional[RuntimeType] = None) -> Dict[str, List[str]]:
        """Get capabilities for specified or all runtimes."""
        if runtime_type:
            runtime = self._runtimes.get(runtime_type)
            if not runtime:
                return {}
            return {runtime_type.value: runtime.get_capabilities()}
        else:
            capabilities = {}
            for runtime_type, runtime in self._runtimes.items():
                capabilities[runtime_type.value] = runtime.get_capabilities()
            return capabilities