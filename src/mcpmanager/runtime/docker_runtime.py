"""Docker runtime implementation."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

import docker
from docker.errors import DockerException, NotFound

from .base import BaseRuntime, RuntimeType, RuntimeInfo, ContainerSpec, RuntimeError
from mcpmanager.core.models import ContainerInfo, ContainerState, PortMapping

logger = logging.getLogger(__name__)


class DockerRuntime(BaseRuntime):
    """Docker runtime implementation."""

    def __init__(self):
        """Initialize Docker runtime."""
        super().__init__("docker", RuntimeType.DOCKER)
        self._client: Optional[docker.DockerClient] = None

    async def initialize(self) -> None:
        """Initialize Docker runtime."""
        if self._initialized:
            return

        try:
            self._client = docker.from_env()
            await self._run_in_executor(self._client.ping)
            self._initialized = True
            logger.info("Docker runtime initialized successfully")
        except DockerException as e:
            logger.error(f"Failed to initialize Docker runtime: {e}")
            raise RuntimeError(f"Docker is not available: {e}")

    async def cleanup(self) -> None:
        """Cleanup Docker runtime."""
        if self._client:
            try:
                await self._run_in_executor(self._client.close)
            except Exception as e:
                logger.warning(f"Error closing Docker client: {e}")
        
        self._initialized = False
        logger.info("Docker runtime cleaned up")

    async def _run_in_executor(self, func, *args, **kwargs):
        """Run synchronous function in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)

    async def is_available(self) -> bool:
        """Check if Docker is available."""
        try:
            if not self._client:
                self._client = docker.from_env()
            await self._run_in_executor(self._client.ping)
            return True
        except Exception:
            return False

    async def get_runtime_info(self) -> RuntimeInfo:
        """Get Docker runtime information."""
        try:
            if not self._initialized:
                await self.initialize()
            
            version_info = await self._run_in_executor(self._client.version)
            info = await self._run_in_executor(self._client.info)
            
            return RuntimeInfo(
                name="Docker",
                type=RuntimeType.DOCKER,
                version=version_info.get("Version", "unknown"),
                available=True,
                status="running",
                capabilities=self.get_capabilities(),
                config={
                    "server_version": version_info.get("Version"),
                    "api_version": version_info.get("ApiVersion"),
                    "platform": version_info.get("Platform", {}).get("Name"),
                    "containers": info.get("Containers", 0),
                    "images": info.get("Images", 0),
                    "architecture": version_info.get("Arch"),
                }
            )
        except Exception as e:
            return RuntimeInfo(
                name="Docker",
                type=RuntimeType.DOCKER,
                version="unknown",
                available=False,
                status="error",
                capabilities=[],
                config={"error": str(e)}
            )

    def _spec_to_docker_config(self, spec: ContainerSpec) -> Dict[str, Any]:
        """Convert ContainerSpec to Docker configuration."""
        config = {
            "image": spec.image,
            "name": spec.name,
            "detach": True,
            "labels": spec.labels or {},
            "environment": spec.environment or {},
        }

        if spec.command:
            config["command"] = spec.command

        if spec.port_bindings:
            config["ports"] = spec.port_bindings

        if spec.volumes:
            config["volumes"] = spec.volumes

        if spec.permission_profile:
            config.update(self._apply_permission_profile(spec.permission_profile))

        config["network_mode"] = spec.network_mode

        # Security defaults
        config["security_opt"] = ["no-new-privileges:true"]
        config["cap_drop"] = ["ALL"]

        if spec.restart_policy:
            config["restart_policy"] = spec.restart_policy

        if spec.resources:
            if "memory" in spec.resources:
                config["mem_limit"] = spec.resources["memory"]
            if "cpu_shares" in spec.resources:
                config["cpu_shares"] = spec.resources["cpu_shares"]

        return config

    def _apply_permission_profile(self, profile) -> Dict[str, Any]:
        """Apply permission profile to container config."""
        config = {}

        # Configure volumes
        volumes = {}
        for read_path in profile.read:
            if ":" in read_path:
                source, target = read_path.split(":", 1)
            else:
                source = target = read_path
            volumes[source] = {"bind": target, "mode": "ro"}

        for write_path in profile.write:
            if ":" in write_path:
                source, target = write_path.split(":", 1)
            else:
                source = target = write_path
            volumes[source] = {"bind": target, "mode": "rw"}

        if volumes:
            config["volumes"] = volumes

        # Configure network
        if profile.network:
            outbound = profile.network.get("outbound")
            if outbound:
                if outbound.insecure_allow_all:
                    config["network_mode"] = "bridge"
                elif (
                    outbound.allow_transport
                    or outbound.allow_host
                    or outbound.allow_port
                ):
                    config["network_mode"] = "bridge"
                else:
                    config["network_mode"] = "none"

        return config

    async def create_container(self, spec: ContainerSpec) -> str:
        """Create a container."""
        if not self._initialized:
            await self.initialize()

        try:
            config = self._spec_to_docker_config(spec)
            container = await self._run_in_executor(
                self._client.containers.create, **config
            )
            logger.info(f"Container {spec.name} created with ID: {container.short_id}")
            return container.id
        except DockerException as e:
            logger.error(f"Failed to create container {spec.name}: {e}")
            raise RuntimeError(f"Failed to create container: {e}")

    async def start_container(self, container_id: str) -> None:
        """Start a container."""
        try:
            container = self._client.containers.get(container_id)
            await self._run_in_executor(container.start)
            logger.info(f"Container {container_id[:12]} started")
        except DockerException as e:
            logger.error(f"Failed to start container {container_id}: {e}")
            raise RuntimeError(f"Failed to start container: {e}")

    async def stop_container(self, container_id: str, timeout: int = 30) -> None:
        """Stop a container."""
        try:
            container = self._client.containers.get(container_id)
            await self._run_in_executor(container.stop, timeout=timeout)
            logger.info(f"Container {container_id[:12]} stopped")
        except NotFound:
            logger.warning(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to stop container {container_id}: {e}")
            raise RuntimeError(f"Failed to stop container: {e}")

    async def remove_container(self, container_id: str, force: bool = True) -> None:
        """Remove a container."""
        try:
            container = self._client.containers.get(container_id)
            await self._run_in_executor(container.remove, force=force)
            logger.info(f"Container {container_id[:12]} removed")
        except NotFound:
            logger.warning(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to remove container {container_id}: {e}")
            raise RuntimeError(f"Failed to remove container: {e}")

    async def list_containers(
        self, all: bool = False, filters: Optional[Dict[str, Any]] = None
    ) -> List[ContainerInfo]:
        """List containers."""
        try:
            containers = await self._run_in_executor(
                self._client.containers.list, all=all, filters=filters
            )

            result = []
            for container in containers:
                # Get port mappings
                ports = []
                for port_info in container.ports.values():
                    if port_info:
                        for binding in port_info:
                            ports.append(
                                PortMapping(
                                    container_port=int(binding.get("HostPort", 0)),
                                    host_port=int(binding.get("HostPort", 0)),
                                    protocol="tcp",
                                )
                            )

                # Parse creation time
                created_str = container.attrs.get("Created", "")
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    created = datetime.now()

                # Map Docker state
                docker_state = container.status.lower()
                if docker_state == "running":
                    state = ContainerState.RUNNING
                elif docker_state == "exited":
                    state = ContainerState.EXITED
                elif docker_state == "created":
                    state = ContainerState.CREATED
                elif docker_state == "paused":
                    state = ContainerState.PAUSED
                elif docker_state == "restarting":
                    state = ContainerState.RESTARTING
                else:
                    state = ContainerState.STOPPED

                container_info = ContainerInfo(
                    id=container.id,
                    name=container.name,
                    image=container.image.tags[0] if container.image.tags else "unknown",
                    status=container.status,
                    state=state,
                    created=created,
                    labels=container.labels,
                    ports=ports,
                )
                result.append(container_info)

            return result

        except DockerException as e:
            logger.error(f"Failed to list containers: {e}")
            raise RuntimeError(f"Failed to list containers: {e}")

    async def get_container_info(self, container_id: str) -> ContainerInfo:
        """Get container information."""
        try:
            container = self._client.containers.get(container_id)
            await self._run_in_executor(container.reload)

            # Get port mappings
            ports = []
            port_bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {})
            for container_port, host_bindings in port_bindings.items():
                if host_bindings:
                    for binding in host_bindings:
                        ports.append(
                            PortMapping(
                                container_port=int(container_port.split("/")[0]),
                                host_port=int(binding.get("HostPort", 0)),
                                protocol=container_port.split("/")[1] if "/" in container_port else "tcp",
                            )
                        )

            # Parse creation time
            created_str = container.attrs.get("Created", "")
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                created = datetime.now()

            # Map Docker state
            docker_state = container.status.lower()
            if docker_state == "running":
                state = ContainerState.RUNNING
            elif docker_state == "exited":
                state = ContainerState.EXITED
            elif docker_state == "created":
                state = ContainerState.CREATED
            elif docker_state == "paused":
                state = ContainerState.PAUSED
            elif docker_state == "restarting":
                state = ContainerState.RESTARTING
            else:
                state = ContainerState.STOPPED

            return ContainerInfo(
                id=container.id,
                name=container.name,
                image=container.image.tags[0] if container.image.tags else "unknown",
                status=container.status,
                state=state,
                created=created,
                labels=container.labels,
                ports=ports,
            )

        except NotFound:
            raise RuntimeError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to get container info: {e}")
            raise RuntimeError(f"Failed to get container info: {e}")

    async def get_container_logs(
        self,
        container_id: str,
        follow: bool = False,
        tail: int = 100,
        since: Optional[str] = None,
    ) -> str:
        """Get container logs."""
        try:
            container = self._client.containers.get(container_id)
            logs = await self._run_in_executor(
                container.logs,
                follow=follow,
                tail=tail,
                since=since,
                stdout=True,
                stderr=True,
            )

            if isinstance(logs, bytes):
                return logs.decode("utf-8", errors="replace")
            elif hasattr(logs, "__iter__"):
                return "\n".join(log.decode("utf-8", errors="replace") for log in logs)
            else:
                return str(logs)

        except NotFound:
            raise RuntimeError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to get container logs: {e}")
            raise RuntimeError(f"Failed to get container logs: {e}")

    async def is_container_running(self, container_id: str) -> bool:
        """Check if container is running."""
        try:
            container = self._client.containers.get(container_id)
            await self._run_in_executor(container.reload)
            return container.status.lower() == "running"
        except NotFound:
            return False
        except DockerException as e:
            logger.error(f"Failed to check container status: {e}")
            return False

    async def exec_in_container(
        self,
        container_id: str,
        command: Union[str, List[str]],
        workdir: Optional[str] = None,
        user: Optional[str] = None,
    ) -> tuple[int, str]:
        """Execute command in container."""
        try:
            container = self._client.containers.get(container_id)
            exec_result = await self._run_in_executor(
                container.exec_run,
                command,
                workdir=workdir,
                user=user,
                demux=True,
            )

            exit_code = exec_result.exit_code
            output = ""

            if exec_result.output:
                stdout, stderr = exec_result.output
                if stdout:
                    output += stdout.decode("utf-8", errors="replace")
                if stderr:
                    output += stderr.decode("utf-8", errors="replace")

            return exit_code, output

        except NotFound:
            raise RuntimeError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to execute command in container: {e}")
            raise RuntimeError(f"Failed to execute command: {e}")

    async def pull_image(self, image: str, tag: str = "latest") -> None:
        """Pull an image."""
        try:
            full_image = f"{image}:{tag}" if ":" not in image else image
            await self._run_in_executor(self._client.images.pull, full_image)
            logger.info(f"Pulled image: {full_image}")
        except DockerException as e:
            logger.error(f"Failed to pull image {image}: {e}")
            raise RuntimeError(f"Failed to pull image: {e}")

    async def image_exists(self, image: str) -> bool:
        """Check if image exists."""
        try:
            await self._run_in_executor(self._client.images.get, image)
            return True
        except NotFound:
            return False
        except DockerException as e:
            logger.error(f"Failed to check image existence: {e}")
            return False

    async def build_image(
        self,
        path: str,
        tag: str,
        dockerfile: str = "Dockerfile",
        build_args: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build an image."""
        try:
            image, logs = await self._run_in_executor(
                self._client.images.build,
                path=path,
                tag=tag,
                dockerfile=dockerfile,
                buildargs=build_args,
                rm=True,
            )

            # Log build output
            for log in logs:
                if "stream" in log:
                    logger.debug(log["stream"].strip())

            logger.info(f"Built image: {tag}")
            return image.id

        except DockerException as e:
            logger.error(f"Failed to build image {tag}: {e}")
            raise RuntimeError(f"Failed to build image: {e}")

    async def get_container_stats(self, container_id: str) -> Dict[str, Any]:
        """Get container statistics."""
        try:
            container = self._client.containers.get(container_id)
            stats = await self._run_in_executor(container.stats, stream=False)
            return stats
        except NotFound:
            raise RuntimeError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to get container stats: {e}")
            raise RuntimeError(f"Failed to get container stats: {e}")

    async def inspect_container(self, container_id: str) -> Dict[str, Any]:
        """Inspect container."""
        try:
            container = self._client.containers.get(container_id)
            await self._run_in_executor(container.reload)
            return container.attrs
        except NotFound:
            raise RuntimeError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to inspect container: {e}")
            raise RuntimeError(f"Failed to inspect container: {e}")

    async def pause_container(self, container_id: str) -> None:
        """Pause a container."""
        try:
            container = self._client.containers.get(container_id)
            await self._run_in_executor(container.pause)
            logger.info(f"Container {container_id[:12]} paused")
        except DockerException as e:
            logger.error(f"Failed to pause container: {e}")
            raise RuntimeError(f"Failed to pause container: {e}")

    async def unpause_container(self, container_id: str) -> None:
        """Unpause a container."""
        try:
            container = self._client.containers.get(container_id)
            await self._run_in_executor(container.unpause)
            logger.info(f"Container {container_id[:12]} unpaused")
        except DockerException as e:
            logger.error(f"Failed to unpause container: {e}")
            raise RuntimeError(f"Failed to unpause container: {e}")