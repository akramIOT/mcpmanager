"""Docker client for container management."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
import json

import docker
from docker.errors import DockerException, NotFound, APIError

from mcpmanager.core.models import (
    ContainerInfo,
    ContainerState,
    PortMapping,
    PermissionProfile,
)

logger = logging.getLogger(__name__)


class DockerClient:
    """Docker client for managing containers."""

    def __init__(self):
        """Initialize Docker client."""
        self._client: Optional[docker.DockerClient] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the Docker client."""
        if self._initialized:
            return

        try:
            # Create Docker client
            self._client = docker.from_env()
            
            # Test connection
            await self._run_in_executor(self._client.ping)
            
            self._initialized = True
            logger.info("Docker client initialized successfully")
            
        except DockerException as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            raise RuntimeError(f"Docker is not available: {e}")

    async def _run_in_executor(self, func, *args, **kwargs):
        """Run a synchronous function in an executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)

    async def create_container(
        self,
        image: str,
        name: str,
        command: Optional[List[str]] = None,
        environment: Optional[Dict[str, str]] = None,
        labels: Optional[Dict[str, str]] = None,
        port_bindings: Optional[Dict[str, Union[int, str]]] = None,
        volumes: Optional[Dict[str, Dict[str, str]]] = None,
        permission_profile: Optional[PermissionProfile] = None,
        network_mode: str = "bridge",
        **kwargs: Any,
    ) -> str:
        """Create a container."""
        if not self._initialized:
            await self.initialize()

        try:
            # Prepare container configuration
            container_config = {
                "image": image,
                "name": name,
                "detach": True,
                "labels": labels or {},
                "environment": environment or {},
            }

            if command:
                container_config["command"] = command

            # Configure ports
            if port_bindings:
                container_config["ports"] = port_bindings

            # Configure volumes
            if volumes:
                container_config["volumes"] = volumes

            # Apply permission profile
            if permission_profile:
                container_config.update(self._apply_permission_profile(permission_profile))

            # Set network mode
            container_config["network_mode"] = network_mode

            # Add security options
            container_config["security_opt"] = ["no-new-privileges:true"]
            
            # Drop all capabilities by default
            container_config["cap_drop"] = ["ALL"]

            # Create container
            container = await self._run_in_executor(
                self._client.containers.create, **container_config
            )

            logger.info(f"Container {name} created with ID: {container.short_id}")
            return container.id

        except DockerException as e:
            logger.error(f"Failed to create container {name}: {e}")
            raise

    def _apply_permission_profile(self, profile: PermissionProfile) -> Dict[str, Any]:
        """Apply permission profile to container configuration."""
        config = {}

        # Configure read-only mounts
        volumes = {}
        for read_path in profile.read:
            # Parse mount format: source:target or just path
            if ":" in read_path:
                source, target = read_path.split(":", 1)
            else:
                source = target = read_path
            
            volumes[source] = {"bind": target, "mode": "ro"}

        # Configure read-write mounts
        for write_path in profile.write:
            if ":" in write_path:
                source, target = write_path.split(":", 1)
            else:
                source = target = write_path
            
            volumes[source] = {"bind": target, "mode": "rw"}

        if volumes:
            config["volumes"] = volumes

        # Configure network access
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
                    # TODO: Implement more granular network controls
                else:
                    config["network_mode"] = "none"

        return config

    async def start_container(self, container_id: str) -> None:
        """Start a container."""
        try:
            container = self._client.containers.get(container_id)
            await self._run_in_executor(container.start)
            logger.info(f"Container {container_id[:12]} started")
        except DockerException as e:
            logger.error(f"Failed to start container {container_id}: {e}")
            raise

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
            raise

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
            raise

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

                # Map Docker state to our ContainerState enum
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
            raise

    async def get_container_info(self, container_id: str) -> ContainerInfo:
        """Get detailed information about a container."""
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
            raise ValueError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to get container info: {e}")
            raise

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

            # Get logs
            logs = await self._run_in_executor(
                container.logs,
                follow=follow,
                tail=tail,
                since=since,
                stdout=True,
                stderr=True,
            )

            # Decode bytes to string
            if isinstance(logs, bytes):
                return logs.decode("utf-8", errors="replace")
            elif hasattr(logs, "__iter__"):
                # Generator for follow mode
                return "\n".join(log.decode("utf-8", errors="replace") for log in logs)
            else:
                return str(logs)

        except NotFound:
            raise ValueError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to get container logs: {e}")
            raise

    async def is_container_running(self, container_id: str) -> bool:
        """Check if a container is running."""
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
        """Execute a command in a container."""
        try:
            container = self._client.containers.get(container_id)

            # Create exec instance
            exec_result = await self._run_in_executor(
                container.exec_run,
                command,
                workdir=workdir,
                user=user,
                demux=True,
            )

            exit_code = exec_result.exit_code
            output = ""

            # Combine stdout and stderr
            if exec_result.output:
                stdout, stderr = exec_result.output
                if stdout:
                    output += stdout.decode("utf-8", errors="replace")
                if stderr:
                    output += stderr.decode("utf-8", errors="replace")

            return exit_code, output

        except NotFound:
            raise ValueError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to execute command in container: {e}")
            raise

    async def pull_image(self, image: str, tag: str = "latest") -> None:
        """Pull a Docker image."""
        try:
            full_image = f"{image}:{tag}" if ":" not in image else image
            await self._run_in_executor(self._client.images.pull, full_image)
            logger.info(f"Pulled image: {full_image}")
        except DockerException as e:
            logger.error(f"Failed to pull image {image}: {e}")
            raise

    async def image_exists(self, image: str) -> bool:
        """Check if an image exists locally."""
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
        """Build a Docker image."""
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
            raise

    async def get_container_stats(self, container_id: str) -> Dict[str, Any]:
        """Get container statistics."""
        try:
            container = self._client.containers.get(container_id)
            stats = await self._run_in_executor(container.stats, stream=False)
            return stats
        except NotFound:
            raise ValueError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to get container stats: {e}")
            raise

    async def inspect_container(self, container_id: str) -> Dict[str, Any]:
        """Inspect container and return detailed information."""
        try:
            container = self._client.containers.get(container_id)
            await self._run_in_executor(container.reload)
            return container.attrs
        except NotFound:
            raise ValueError(f"Container {container_id} not found")
        except DockerException as e:
            logger.error(f"Failed to inspect container: {e}")
            raise

    async def cleanup(self) -> None:
        """Cleanup Docker client resources."""
        if self._client:
            try:
                await self._run_in_executor(self._client.close)
            except Exception as e:
                logger.warning(f"Error closing Docker client: {e}")
        
        self._initialized = False
        logger.info("Docker client cleaned up")