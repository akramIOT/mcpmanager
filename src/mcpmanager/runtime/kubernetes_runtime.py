"""Kubernetes runtime implementation."""

import asyncio
import base64
import json
import logging
import yaml
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from .base import BaseRuntime, RuntimeType, RuntimeInfo, ContainerSpec, RuntimeError
from mcpmanager.core.models import ContainerInfo, ContainerState, PortMapping

logger = logging.getLogger(__name__)


class KubernetesRuntime(BaseRuntime):
    """Kubernetes runtime implementation using kubectl."""

    def __init__(self, namespace: str = "mcpmanager"):
        """Initialize Kubernetes runtime."""
        super().__init__("kubernetes", RuntimeType.KUBERNETES)
        self.namespace = namespace
        self._kubectl_cmd = "kubectl"

    async def initialize(self) -> None:
        """Initialize Kubernetes runtime."""
        if self._initialized:
            return

        try:
            # Check if kubectl is available
            result = await self._run_command(["kubectl", "version", "--client", "--output=json"])
            if result["returncode"] != 0:
                raise RuntimeError("kubectl command failed")
            
            # Check cluster access
            result = await self._run_command(["kubectl", "cluster-info"])
            if result["returncode"] != 0:
                raise RuntimeError("Cannot access Kubernetes cluster")
            
            # Create namespace if it doesn't exist
            await self._ensure_namespace()
            
            self._initialized = True
            logger.info("Kubernetes runtime initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes runtime: {e}")
            raise RuntimeError(f"Kubernetes is not available: {e}")

    async def cleanup(self) -> None:
        """Cleanup Kubernetes runtime."""
        self._initialized = False
        logger.info("Kubernetes runtime cleaned up")

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

    async def _ensure_namespace(self) -> None:
        """Ensure the namespace exists."""
        try:
            result = await self._run_command([
                "kubectl", "get", "namespace", self.namespace
            ])
            if result["returncode"] != 0:
                # Create namespace
                namespace_yaml = {
                    "apiVersion": "v1",
                    "kind": "Namespace",
                    "metadata": {
                        "name": self.namespace,
                        "labels": {
                            "mcpmanager": "true"
                        }
                    }
                }
                await self._apply_yaml(namespace_yaml)
                logger.info(f"Created namespace: {self.namespace}")
        except Exception as e:
            logger.error(f"Failed to ensure namespace: {e}")
            raise

    async def _apply_yaml(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a YAML resource to Kubernetes."""
        yaml_content = yaml.dump(resource)
        result = await self._run_command(
            ["kubectl", "apply", "-f", "-"],
            input_data=yaml_content
        )
        if result["returncode"] != 0:
            raise RuntimeError(f"Failed to apply resource: {result['stderr']}")
        return result

    async def is_available(self) -> bool:
        """Check if Kubernetes is available."""
        try:
            result = await self._run_command(["kubectl", "cluster-info"])
            return result["returncode"] == 0
        except Exception:
            return False

    async def get_runtime_info(self) -> RuntimeInfo:
        """Get Kubernetes runtime information."""
        try:
            if not self._initialized:
                await self.initialize()
            
            # Get client version
            version_result = await self._run_command([
                "kubectl", "version", "--client", "--output=json"
            ])
            client_version = "unknown"
            if version_result["returncode"] == 0:
                try:
                    version_data = json.loads(version_result["stdout"])
                    client_version = version_data.get("clientVersion", {}).get("gitVersion", "unknown")
                except json.JSONDecodeError:
                    pass
            
            # Get cluster info
            cluster_result = await self._run_command(["kubectl", "cluster-info"])
            cluster_info = cluster_result["stdout"] if cluster_result["returncode"] == 0 else "unavailable"
            
            # Get node count
            nodes_result = await self._run_command([
                "kubectl", "get", "nodes", "--output=json"
            ])
            node_count = 0
            if nodes_result["returncode"] == 0:
                try:
                    nodes_data = json.loads(nodes_result["stdout"])
                    node_count = len(nodes_data.get("items", []))
                except json.JSONDecodeError:
                    pass
            
            return RuntimeInfo(
                name="Kubernetes",
                type=RuntimeType.KUBERNETES,
                version=client_version,
                available=True,
                status="running",
                capabilities=self.get_capabilities(),
                config={
                    "client_version": client_version,
                    "namespace": self.namespace,
                    "cluster_info": cluster_info,
                    "node_count": node_count,
                }
            )
        except Exception as e:
            return RuntimeInfo(
                name="Kubernetes",
                type=RuntimeType.KUBERNETES,
                version="unknown",
                available=False,
                status="error",
                capabilities=[],
                config={"error": str(e)}
            )

    def _spec_to_k8s_manifest(self, spec: ContainerSpec) -> Dict[str, Any]:
        """Convert ContainerSpec to Kubernetes Pod manifest."""
        # Container definition
        container = {
            "name": spec.name,
            "image": spec.image,
        }
        
        if spec.command:
            container["command"] = spec.command
        
        if spec.environment:
            container["env"] = [
                {"name": key, "value": value}
                for key, value in spec.environment.items()
            ]
        
        # Port definitions
        if spec.port_bindings:
            container["ports"] = []
            for container_port, host_port in spec.port_bindings.items():
                port_num = int(container_port.split("/")[0]) if "/" in container_port else int(container_port)
                container["ports"].append({
                    "containerPort": port_num,
                    "protocol": "TCP"
                })
        
        # Security context
        container["securityContext"] = {
            "allowPrivilegeEscalation": False,
            "runAsNonRoot": True,
            "runAsUser": 1000,
            "capabilities": {
                "drop": ["ALL"]
            },
            "readOnlyRootFilesystem": False,  # Some MCP servers need to write
        }
        
        # Resource constraints
        if spec.resources:
            container["resources"] = {}
            if "memory" in spec.resources:
                container["resources"]["limits"] = {"memory": spec.resources["memory"]}
            if "cpu_shares" in spec.resources:
                cpu_limit = f"{spec.resources['cpu_shares']}m"  # Convert to millicores
                container["resources"]["limits"] = container["resources"].get("limits", {})
                container["resources"]["limits"]["cpu"] = cpu_limit
        
        # Volume mounts
        volume_mounts = []
        if spec.permission_profile:
            for idx, read_path in enumerate(spec.permission_profile.read):
                if ":" in read_path:
                    source, target = read_path.split(":", 1)
                else:
                    source = target = read_path
                volume_mounts.append({
                    "name": f"read-volume-{idx}",
                    "mountPath": target,
                    "readOnly": True
                })
            
            for idx, write_path in enumerate(spec.permission_profile.write):
                if ":" in write_path:
                    source, target = write_path.split(":", 1)
                else:
                    source = target = write_path
                volume_mounts.append({
                    "name": f"write-volume-{idx}",
                    "mountPath": target,
                    "readOnly": False
                })
        
        if volume_mounts:
            container["volumeMounts"] = volume_mounts
        
        # Pod definition
        pod_spec = {
            "containers": [container],
            "restartPolicy": "Always",
            "securityContext": {
                "runAsNonRoot": True,
                "runAsUser": 1000,
                "fsGroup": 1000,
            }
        }
        
        # Add volumes if needed
        volumes = []
        if spec.permission_profile:
            for idx, read_path in enumerate(spec.permission_profile.read):
                source = read_path.split(":")[0] if ":" in read_path else read_path
                volumes.append({
                    "name": f"read-volume-{idx}",
                    "hostPath": {
                        "path": source,
                        "type": "DirectoryOrCreate"
                    }
                })
            
            for idx, write_path in enumerate(spec.permission_profile.write):
                source = write_path.split(":")[0] if ":" in write_path else write_path
                volumes.append({
                    "name": f"write-volume-{idx}",
                    "hostPath": {
                        "path": source,
                        "type": "DirectoryOrCreate"
                    }
                })
        
        if volumes:
            pod_spec["volumes"] = volumes
        
        # Full pod manifest
        pod_manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": spec.name,
                "namespace": self.namespace,
                "labels": {
                    "mcpmanager": "true",
                    "mcpmanager.server": spec.name,
                }
            },
            "spec": pod_spec
        }
        
        # Add user labels
        if spec.labels:
            pod_manifest["metadata"]["labels"].update(spec.labels)
        
        return pod_manifest

    async def create_container(self, spec: ContainerSpec) -> str:
        """Create a pod (container equivalent in K8s)."""
        if not self._initialized:
            await self.initialize()

        try:
            pod_manifest = self._spec_to_k8s_manifest(spec)
            await self._apply_yaml(pod_manifest)
            
            # Wait for pod to be created
            await asyncio.sleep(1)
            
            # Get pod UID as container ID
            result = await self._run_command([
                "kubectl", "get", "pod", spec.name,
                "-n", self.namespace,
                "-o", "jsonpath={.metadata.uid}"
            ])
            
            if result["returncode"] != 0:
                raise RuntimeError(f"Failed to get pod UID: {result['stderr']}")
            
            pod_uid = result["stdout"].strip()
            logger.info(f"Pod {spec.name} created with UID: {pod_uid}")
            return pod_uid
            
        except Exception as e:
            logger.error(f"Failed to create pod {spec.name}: {e}")
            raise RuntimeError(f"Failed to create pod: {e}")

    async def start_container(self, container_id: str) -> None:
        """Start a pod (pods are auto-started in K8s)."""
        # In Kubernetes, pods are automatically started when created
        # We can check if the pod is running
        pod_name = await self._get_pod_name_by_uid(container_id)
        if pod_name:
            logger.info(f"Pod {pod_name} is managed by Kubernetes scheduler")
        else:
            raise RuntimeError(f"Pod with UID {container_id} not found")

    async def stop_container(self, container_id: str, timeout: int = 30) -> None:
        """Stop a pod."""
        try:
            pod_name = await self._get_pod_name_by_uid(container_id)
            if not pod_name:
                logger.warning(f"Pod with UID {container_id} not found")
                return
            
            result = await self._run_command([
                "kubectl", "delete", "pod", pod_name,
                "-n", self.namespace,
                f"--grace-period={timeout}"
            ])
            
            if result["returncode"] != 0 and "not found" not in result["stderr"].lower():
                raise RuntimeError(f"Failed to stop pod: {result['stderr']}")
            
            logger.info(f"Pod {pod_name} stopped")
        except Exception as e:
            logger.error(f"Failed to stop pod {container_id}: {e}")
            raise RuntimeError(f"Failed to stop pod: {e}")

    async def remove_container(self, container_id: str, force: bool = True) -> None:
        """Remove a pod."""
        try:
            pod_name = await self._get_pod_name_by_uid(container_id)
            if not pod_name:
                logger.warning(f"Pod with UID {container_id} not found")
                return
            
            args = ["kubectl", "delete", "pod", pod_name, "-n", self.namespace]
            if force:
                args.append("--force")
                args.append("--grace-period=0")
            
            result = await self._run_command(args)
            if result["returncode"] != 0 and "not found" not in result["stderr"].lower():
                raise RuntimeError(f"Failed to remove pod: {result['stderr']}")
            
            logger.info(f"Pod {pod_name} removed")
        except Exception as e:
            logger.error(f"Failed to remove pod {container_id}: {e}")
            raise RuntimeError(f"Failed to remove pod: {e}")

    async def _get_pod_name_by_uid(self, uid: str) -> Optional[str]:
        """Get pod name by UID."""
        try:
            result = await self._run_command([
                "kubectl", "get", "pods", "-n", self.namespace,
                "-o", "json"
            ])
            
            if result["returncode"] != 0:
                return None
            
            pods_data = json.loads(result["stdout"])
            for pod in pods_data.get("items", []):
                if pod.get("metadata", {}).get("uid") == uid:
                    return pod.get("metadata", {}).get("name")
            
            return None
        except Exception:
            return None

    async def list_containers(
        self, all: bool = False, filters: Optional[Dict[str, Any]] = None
    ) -> List[ContainerInfo]:
        """List pods."""
        try:
            args = ["kubectl", "get", "pods", "-n", self.namespace, "-o", "json"]
            
            # Add label selector for MCP manager pods
            args.extend(["-l", "mcpmanager=true"])
            
            result = await self._run_command(args)
            if result["returncode"] != 0:
                raise RuntimeError(f"Failed to list pods: {result['stderr']}")
            
            pods_data = json.loads(result["stdout"])
            containers = []
            
            for pod in pods_data.get("items", []):
                metadata = pod.get("metadata", {})
                spec = pod.get("spec", {})
                status = pod.get("status", {})
                
                # Parse creation time
                created_str = metadata.get("creationTimestamp", "")
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    created = datetime.now()
                
                # Map pod phase to container state
                phase = status.get("phase", "").lower()
                if phase == "running":
                    state = ContainerState.RUNNING
                elif phase == "pending":
                    state = ContainerState.CREATED
                elif phase in ["succeeded", "failed"]:
                    state = ContainerState.EXITED
                else:
                    state = ContainerState.STOPPED
                
                # Get container info from pod spec
                pod_containers = spec.get("containers", [])
                if pod_containers:
                    container_spec = pod_containers[0]  # Use first container
                    image = container_spec.get("image", "")
                else:
                    image = "unknown"
                
                # Parse ports (from service or pod spec)
                ports = []
                for container_spec in pod_containers:
                    for port in container_spec.get("ports", []):
                        ports.append(PortMapping(
                            container_port=port.get("containerPort", 0),
                            host_port=port.get("hostPort", port.get("containerPort", 0)),
                            protocol=port.get("protocol", "TCP").lower()
                        ))
                
                container_info = ContainerInfo(
                    id=metadata.get("uid", ""),
                    name=metadata.get("name", ""),
                    image=image,
                    status=status.get("phase", ""),
                    state=state,
                    created=created,
                    labels=metadata.get("labels", {}),
                    ports=ports,
                )
                containers.append(container_info)
            
            return containers

        except Exception as e:
            logger.error(f"Failed to list pods: {e}")
            raise RuntimeError(f"Failed to list pods: {e}")

    async def get_container_info(self, container_id: str) -> ContainerInfo:
        """Get pod information."""
        try:
            pod_name = await self._get_pod_name_by_uid(container_id)
            if not pod_name:
                raise RuntimeError(f"Pod with UID {container_id} not found")
            
            result = await self._run_command([
                "kubectl", "get", "pod", pod_name,
                "-n", self.namespace,
                "-o", "json"
            ])
            
            if result["returncode"] != 0:
                raise RuntimeError(f"Pod {container_id} not found")
            
            pod_data = json.loads(result["stdout"])
            metadata = pod_data.get("metadata", {})
            spec = pod_data.get("spec", {})
            status = pod_data.get("status", {})
            
            # Parse creation time
            created_str = metadata.get("creationTimestamp", "")
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                created = datetime.now()
            
            # Map pod phase to container state
            phase = status.get("phase", "").lower()
            if phase == "running":
                state = ContainerState.RUNNING
            elif phase == "pending":
                state = ContainerState.CREATED
            elif phase in ["succeeded", "failed"]:
                state = ContainerState.EXITED
            else:
                state = ContainerState.STOPPED
            
            # Get container info
            pod_containers = spec.get("containers", [])
            image = pod_containers[0].get("image", "") if pod_containers else "unknown"
            
            # Parse ports
            ports = []
            for container_spec in pod_containers:
                for port in container_spec.get("ports", []):
                    ports.append(PortMapping(
                        container_port=port.get("containerPort", 0),
                        host_port=port.get("hostPort", port.get("containerPort", 0)),
                        protocol=port.get("protocol", "TCP").lower()
                    ))
            
            return ContainerInfo(
                id=metadata.get("uid", ""),
                name=metadata.get("name", ""),
                image=image,
                status=status.get("phase", ""),
                state=state,
                created=created,
                labels=metadata.get("labels", {}),
                ports=ports,
            )

        except Exception as e:
            logger.error(f"Failed to get pod info: {e}")
            raise RuntimeError(f"Failed to get pod info: {e}")

    async def get_container_logs(
        self,
        container_id: str,
        follow: bool = False,
        tail: int = 100,
        since: Optional[str] = None,
    ) -> str:
        """Get pod logs."""
        try:
            pod_name = await self._get_pod_name_by_uid(container_id)
            if not pod_name:
                raise RuntimeError(f"Pod with UID {container_id} not found")
            
            args = ["kubectl", "logs", pod_name, "-n", self.namespace]
            if follow:
                args.append("--follow")
            if tail:
                args.extend(["--tail", str(tail)])
            if since:
                args.extend(["--since", since])
            
            result = await self._run_command(args)
            if result["returncode"] != 0:
                raise RuntimeError(f"Failed to get logs: {result['stderr']}")
            
            return result["stdout"]

        except Exception as e:
            logger.error(f"Failed to get pod logs: {e}")
            raise RuntimeError(f"Failed to get pod logs: {e}")

    async def is_container_running(self, container_id: str) -> bool:
        """Check if pod is running."""
        try:
            pod_name = await self._get_pod_name_by_uid(container_id)
            if not pod_name:
                return False
            
            result = await self._run_command([
                "kubectl", "get", "pod", pod_name,
                "-n", self.namespace,
                "-o", "jsonpath={.status.phase}"
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
        """Execute command in pod."""
        try:
            pod_name = await self._get_pod_name_by_uid(container_id)
            if not pod_name:
                raise RuntimeError(f"Pod with UID {container_id} not found")
            
            args = ["kubectl", "exec", pod_name, "-n", self.namespace, "--"]
            
            if isinstance(command, list):
                args.extend(command)
            else:
                args.extend(command.split())
            
            result = await self._run_command(args)
            output = result["stdout"] + result["stderr"]
            return result["returncode"], output

        except Exception as e:
            logger.error(f"Failed to execute command in pod: {e}")
            raise RuntimeError(f"Failed to execute command: {e}")

    async def pull_image(self, image: str, tag: str = "latest") -> None:
        """Pull an image (handled by kubelet)."""
        # In Kubernetes, image pulling is handled by kubelet on nodes
        # We can create a simple pod to trigger the pull
        full_image = f"{image}:{tag}" if ":" not in image else image
        logger.info(f"Image pulling in Kubernetes is handled by kubelet: {full_image}")

    async def image_exists(self, image: str) -> bool:
        """Check if image exists (not directly supported in K8s)."""
        # In Kubernetes, we can't directly check if an image exists
        # This would need to be checked on each node
        logger.info("Image existence check not directly supported in Kubernetes")
        return True  # Assume true, let kubelet handle it

    async def build_image(
        self,
        path: str,
        tag: str,
        dockerfile: str = "Dockerfile",
        build_args: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build an image (not directly supported)."""
        # Kubernetes doesn't directly support building images
        # This would typically be done in a CI/CD pipeline
        raise RuntimeError("Image building not supported in Kubernetes runtime. Use a separate build system.")