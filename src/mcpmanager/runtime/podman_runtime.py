"""Podman runtime implementation."""

import asyncio
import json
import logging
import subprocess
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from .base import BaseRuntime, RuntimeType, RuntimeInfo, ContainerSpec, RuntimeError
from mcpmanager.core.models import ContainerInfo, ContainerState, PortMapping

logger = logging.getLogger(__name__)


class PodmanRuntime(BaseRuntime):
    """Podman runtime implementation using CLI."""

    def __init__(self):
        """Initialize Podman runtime."""
        super().__init__("podman", RuntimeType.PODMAN)
        self._podman_cmd = "podman"

    async def initialize(self) -> None:
        """Initialize Podman runtime."""
        if self._initialized:
            return

        try:
            # Check if podman is available
            result = await self._run_command(["podman", "--version"])
            if result["returncode"] != 0:
                raise RuntimeError("Podman command failed")
            
            # Test connection
            await self._run_command(["podman", "info", "--format", "json"])
            self._initialized = True
            logger.info("Podman runtime initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Podman runtime: {e}")
            raise RuntimeError(f"Podman is not available: {e}")

    async def cleanup(self) -> None:
        """Cleanup Podman runtime."""
        self._initialized = False
        logger.info("Podman runtime cleaned up")

    async def _run_command(self, cmd: List[str], input_data: Optional[str] = None) -> Dict[str, Any]:
        """Run a command asynchronously."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if input_data else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate(
                input=input_data.encode() if input_data else None
            )
            
            return {
                "returncode": process.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace")
            }
        except Exception as e:
            logger.error(f"Command failed: {' '.join(cmd)}: {e}")
            raise RuntimeError(f"Command execution failed: {e}")

    async def is_available(self) -> bool:
        """Check if Podman is available."""
        try:
            result = await self._run_command(["podman", "--version"])
            return result["returncode"] == 0
        except Exception:
            return False

    async def get_runtime_info(self) -> RuntimeInfo:
        """Get Podman runtime information."""
        try:
            if not self._initialized:
                await self.initialize()
            
            # Get version
            version_result = await self._run_command(["podman", "--version"])
            version = "unknown"
            if version_result["returncode"] == 0:
                version_line = version_result["stdout"].strip()
                if "version" in version_line.lower():
                    version = version_line.split()[-1]
            
            # Get info
            info_result = await self._run_command(["podman", "info", "--format", "json"])
            info_data = {}
            if info_result["returncode"] == 0:
                try:
                    info_data = json.loads(info_result["stdout"])
                except json.JSONDecodeError:
                    pass
            
            return RuntimeInfo(
                name="Podman",
                type=RuntimeType.PODMAN,
                version=version,
                available=True,
                status="running",
                capabilities=self.get_capabilities(),
                config={
                    "version": version,
                    "host": info_data.get("host", {}),
                    "store": info_data.get("store", {}),
                    "registries": info_data.get("registries", {}),
                }
            )
        except Exception as e:
            return RuntimeInfo(
                name="Podman",
                type=RuntimeType.PODMAN,
                version="unknown",
                available=False,
                status="error",
                capabilities=[],
                config={"error": str(e)}
            )

    def _spec_to_podman_args(self, spec: ContainerSpec) -> List[str]:
        """Convert ContainerSpec to Podman run arguments."""
        args = ["podman", "run", "--detach", "--name", spec.name]
        
        # Add labels
        if spec.labels:
            for key, value in spec.labels.items():
                args.extend(["--label", f"{key}={value}"])
        
        # Add environment variables
        if spec.environment:
            for key, value in spec.environment.items():
                args.extend(["--env", f"{key}={value}"])
        
        # Add port bindings
        if spec.port_bindings:
            for container_port, host_port in spec.port_bindings.items():
                args.extend(["--publish", f"{host_port}:{container_port}"])
        
        # Add volumes
        if spec.volumes:
            for source, config in spec.volumes.items():
                target = config["bind"]
                mode = config.get("mode", "rw")
                args.extend(["--volume", f"{source}:{target}:{mode}"])
        
        # Add network mode
        if spec.network_mode:
            args.extend(["--network", spec.network_mode])
        
        # Security options
        args.extend(["--security-opt", "no-new-privileges:true"])
        args.extend(["--cap-drop", "ALL"])
        
        # Apply permission profile
        if spec.permission_profile:
            args.extend(self._apply_permission_profile_args(spec.permission_profile))
        
        # Add restart policy
        if spec.restart_policy:
            policy = spec.restart_policy.get("Name", "no")
            if policy != "no":
                args.extend(["--restart", policy])
        
        # Add resource constraints
        if spec.resources:
            if "memory" in spec.resources:
                args.extend(["--memory", str(spec.resources["memory"])])
            if "cpu_shares" in spec.resources:
                args.extend(["--cpu-shares", str(spec.resources["cpu_shares"])])
        
        # Add image
        args.append(spec.image)
        
        # Add command
        if spec.command:
            args.extend(spec.command)
        
        return args

    def _apply_permission_profile_args(self, profile) -> List[str]:
        """Apply permission profile to Podman arguments."""
        args = []
        
        # Add read-only volumes
        for read_path in profile.read:
            if ":" in read_path:
                source, target = read_path.split(":", 1)
            else:
                source = target = read_path
            args.extend(["--volume", f"{source}:{target}:ro"])
        
        # Add read-write volumes
        for write_path in profile.write:
            if ":" in write_path:
                source, target = write_path.split(":", 1)
            else:
                source = target = write_path
            args.extend(["--volume", f"{source}:{target}:rw"])
        
        # Configure network based on profile
        if profile.network:
            outbound = profile.network.get("outbound")
            if outbound and not outbound.insecure_allow_all:
                if not (outbound.allow_transport or outbound.allow_host or outbound.allow_port):
                    args.extend(["--network", "none"])
        
        return args

    async def create_container(self, spec: ContainerSpec) -> str:
        """Create and start a container."""
        if not self._initialized:
            await self.initialize()

        try:
            args = self._spec_to_podman_args(spec)
            result = await self._run_command(args)
            
            if result["returncode"] != 0:
                raise RuntimeError(f"Failed to create container: {result['stderr']}")
            
            container_id = result["stdout"].strip()
            logger.info(f"Container {spec.name} created with ID: {container_id[:12]}")
            return container_id
            
        except Exception as e:
            logger.error(f"Failed to create container {spec.name}: {e}")
            raise RuntimeError(f"Failed to create container: {e}")

    async def start_container(self, container_id: str) -> None:
        """Start a container (Podman containers are started when created)."""
        # In Podman, containers are started when created with --detach
        # But we can check if it's running
        running = await self.is_container_running(container_id)
        if not running:
            try:
                result = await self._run_command(["podman", "start", container_id])
                if result["returncode"] != 0:
                    raise RuntimeError(f"Failed to start container: {result['stderr']}")
                logger.info(f"Container {container_id[:12]} started")
            except Exception as e:
                logger.error(f"Failed to start container {container_id}: {e}")
                raise RuntimeError(f"Failed to start container: {e}")

    async def stop_container(self, container_id: str, timeout: int = 30) -> None:
        """Stop a container."""
        try:
            result = await self._run_command([
                "podman", "stop", "--time", str(timeout), container_id
            ])
            if result["returncode"] != 0 and "no such container" not in result["stderr"].lower():
                raise RuntimeError(f"Failed to stop container: {result['stderr']}")
            logger.info(f"Container {container_id[:12]} stopped")
        except Exception as e:
            logger.error(f"Failed to stop container {container_id}: {e}")
            raise RuntimeError(f"Failed to stop container: {e}")

    async def remove_container(self, container_id: str, force: bool = True) -> None:
        """Remove a container."""
        try:
            args = ["podman", "rm"]
            if force:
                args.append("--force")
            args.append(container_id)
            
            result = await self._run_command(args)
            if result["returncode"] != 0 and "no such container" not in result["stderr"].lower():
                raise RuntimeError(f"Failed to remove container: {result['stderr']}")
            logger.info(f"Container {container_id[:12]} removed")
        except Exception as e:
            logger.error(f"Failed to remove container {container_id}: {e}")
            raise RuntimeError(f"Failed to remove container: {e}")

    async def list_containers(
        self, all: bool = False, filters: Optional[Dict[str, Any]] = None
    ) -> List[ContainerInfo]:
        """List containers."""
        try:
            args = ["podman", "ps", "--format", "json"]
            if all:
                args.append("--all")
            
            # Add filters
            if filters:
                for key, value in filters.items():
                    args.extend(["--filter", f"{key}={value}"])
            
            result = await self._run_command(args)
            if result["returncode"] != 0:
                raise RuntimeError(f"Failed to list containers: {result['stderr']}")
            
            containers_data = []
            if result["stdout"].strip():
                try:
                    containers_data = json.loads(result["stdout"])
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse containers JSON: {e}")
                    return []
            
            if not isinstance(containers_data, list):
                containers_data = [containers_data] if containers_data else []
            
            result_containers = []
            for container in containers_data:
                # Parse creation time
                created_str = container.get("CreatedAt", "")
                try:
                    # Podman time format: "2023-12-07 10:30:45 +0000 UTC"
                    created = datetime.strptime(created_str.split(" +")[0], "%Y-%m-%d %H:%M:%S")
                except (ValueError, AttributeError):
                    created = datetime.now()
                
                # Map Podman state to our enum
                state_str = container.get("State", "").lower()
                if state_str == "running":
                    state = ContainerState.RUNNING
                elif state_str in ["exited", "stopped"]:
                    state = ContainerState.EXITED
                elif state_str == "created":
                    state = ContainerState.CREATED
                elif state_str == "paused":
                    state = ContainerState.PAUSED
                else:
                    state = ContainerState.STOPPED
                
                # Parse ports
                ports = []
                ports_str = container.get("Ports", "")
                if ports_str:
                    # Parse port format: "0.0.0.0:8080->80/tcp"
                    for port_mapping in ports_str.split(", "):
                        if "->" in port_mapping:
                            host_part, container_part = port_mapping.split("->")
                            try:
                                host_port = int(host_part.split(":")[-1])
                                container_port = int(container_part.split("/")[0])
                                protocol = container_part.split("/")[1] if "/" in container_part else "tcp"
                                ports.append(PortMapping(
                                    container_port=container_port,
                                    host_port=host_port,
                                    protocol=protocol
                                ))
                            except (ValueError, IndexError):
                                continue
                
                container_info = ContainerInfo(
                    id=container.get("Id", ""),
                    name=container.get("Names", [""])[0] if isinstance(container.get("Names"), list) else container.get("Names", ""),
                    image=container.get("Image", ""),
                    status=container.get("Status", ""),
                    state=state,
                    created=created,
                    labels=container.get("Labels", {}),
                    ports=ports,
                )
                result_containers.append(container_info)
            
            return result_containers

        except Exception as e:
            logger.error(f"Failed to list containers: {e}")
            raise RuntimeError(f"Failed to list containers: {e}")

    async def get_container_info(self, container_id: str) -> ContainerInfo:
        """Get container information."""
        try:
            result = await self._run_command([
                "podman", "inspect", "--format", "json", container_id
            ])
            if result["returncode"] != 0:
                raise RuntimeError(f"Container {container_id} not found")
            
            inspect_data = json.loads(result["stdout"])
            if isinstance(inspect_data, list):
                inspect_data = inspect_data[0]
            
            # Parse creation time
            created_str = inspect_data.get("Created", "")
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                created = datetime.now()
            
            # Map state
            state_data = inspect_data.get("State", {})
            status = state_data.get("Status", "").lower()
            if status == "running":
                state = ContainerState.RUNNING
            elif status in ["exited", "stopped"]:
                state = ContainerState.EXITED
            elif status == "created":
                state = ContainerState.CREATED
            elif status == "paused":
                state = ContainerState.PAUSED
            else:
                state = ContainerState.STOPPED
            
            # Parse ports
            ports = []
            network_settings = inspect_data.get("NetworkSettings", {})
            port_bindings = network_settings.get("Ports", {})
            for container_port, host_bindings in port_bindings.items():
                if host_bindings:
                    for binding in host_bindings:
                        ports.append(PortMapping(
                            container_port=int(container_port.split("/")[0]),
                            host_port=int(binding.get("HostPort", 0)),
                            protocol=container_port.split("/")[1] if "/" in container_port else "tcp"
                        ))
            
            return ContainerInfo(
                id=inspect_data.get("Id", ""),
                name=inspect_data.get("Name", "").lstrip("/"),
                image=inspect_data.get("Image", ""),
                status=inspect_data.get("State", {}).get("Status", ""),
                state=state,
                created=created,
                labels=inspect_data.get("Config", {}).get("Labels", {}),
                ports=ports,
            )

        except Exception as e:
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
            args = ["podman", "logs"]
            if follow:
                args.append("--follow")
            if tail:
                args.extend(["--tail", str(tail)])
            if since:
                args.extend(["--since", since])
            args.append(container_id)
            
            result = await self._run_command(args)
            if result["returncode"] != 0:
                raise RuntimeError(f"Failed to get logs: {result['stderr']}")
            
            return result["stdout"]

        except Exception as e:
            logger.error(f"Failed to get container logs: {e}")
            raise RuntimeError(f"Failed to get container logs: {e}")

    async def is_container_running(self, container_id: str) -> bool:
        """Check if container is running."""
        try:
            result = await self._run_command([
                "podman", "inspect", "--format", "{{.State.Status}}", container_id
            ])
            if result["returncode"] != 0:
                return False
            return result["stdout"].strip().lower() == "running"
        except Exception:
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
            args = ["podman", "exec"]
            if workdir:
                args.extend(["--workdir", workdir])
            if user:
                args.extend(["--user", user])
            args.append(container_id)
            
            if isinstance(command, list):
                args.extend(command)
            else:
                args.extend(command.split())
            
            result = await self._run_command(args)
            output = result["stdout"] + result["stderr"]
            return result["returncode"], output

        except Exception as e:
            logger.error(f"Failed to execute command in container: {e}")
            raise RuntimeError(f"Failed to execute command: {e}")

    async def pull_image(self, image: str, tag: str = "latest") -> None:
        """Pull an image."""
        try:
            full_image = f"{image}:{tag}" if ":" not in image else image
            result = await self._run_command(["podman", "pull", full_image])
            if result["returncode"] != 0:
                raise RuntimeError(f"Failed to pull image: {result['stderr']}")
            logger.info(f"Pulled image: {full_image}")
        except Exception as e:
            logger.error(f"Failed to pull image {image}: {e}")
            raise RuntimeError(f"Failed to pull image: {e}")

    async def image_exists(self, image: str) -> bool:
        """Check if image exists."""
        try:
            result = await self._run_command(["podman", "image", "exists", image])
            return result["returncode"] == 0
        except Exception:
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
            args = ["podman", "build", "--tag", tag, "--file", dockerfile]
            
            if build_args:
                for key, value in build_args.items():
                    args.extend(["--build-arg", f"{key}={value}"])
            
            args.append(path)
            
            result = await self._run_command(args)
            if result["returncode"] != 0:
                raise RuntimeError(f"Failed to build image: {result['stderr']}")
            
            logger.info(f"Built image: {tag}")
            return tag  # Podman doesn't return image ID easily from CLI

        except Exception as e:
            logger.error(f"Failed to build image {tag}: {e}")
            raise RuntimeError(f"Failed to build image: {e}")