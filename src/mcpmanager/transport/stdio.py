"""STDIO transport implementation."""

import asyncio
import logging
from typing import Optional
import docker

from mcpmanager.transport.base import BaseTransport

logger = logging.getLogger(__name__)


class StdioTransport(BaseTransport):
    """STDIO transport for MCP communication."""

    def __init__(self, container_id: str, **kwargs):
        """Initialize STDIO transport."""
        super().__init__(container_id)
        self._docker_client: Optional[docker.DockerClient] = None
        self._container: Optional[docker.models.containers.Container] = None
        self._stdin_writer: Optional[asyncio.StreamWriter] = None
        self._stdout_reader: Optional[asyncio.StreamReader] = None
        self._stderr_reader: Optional[asyncio.StreamReader] = None

    async def start(self) -> None:
        """Start STDIO transport."""
        await super().start()
        
        try:
            # Get Docker client
            self._docker_client = docker.from_env()
            self._container = self._docker_client.containers.get(self.container_id)
            
            # Attach to container for stdio communication
            attach_result = self._container.attach(
                stdout=True,
                stderr=True,
                stdin=True,
                stream=True,
            )
            
            # Create async streams from the socket
            # Note: This is a simplified implementation
            # In production, you'd want proper async handling
            self._attach_socket = attach_result
            
            logger.info(f"STDIO transport started for container {self.container_id[:12]}")
            
        except Exception as e:
            logger.error(f"Failed to start STDIO transport: {e}")
            raise

    async def stop(self) -> None:
        """Stop STDIO transport."""
        try:
            if self._attach_socket:
                self._attach_socket.close()
            
            if self._stdin_writer:
                self._stdin_writer.close()
                await self._stdin_writer.wait_closed()
            
        except Exception as e:
            logger.warning(f"Error stopping STDIO transport: {e}")
        
        await super().stop()

    async def send_message(self, message: str) -> None:
        """Send a message to the container via stdin."""
        if not self.running or not self._attach_socket:
            raise RuntimeError("Transport not running")
        
        try:
            # Send message to container stdin
            self._attach_socket._sock.send(message.encode() + b"\n")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise

    async def receive_message(self) -> Optional[str]:
        """Receive a message from the container."""
        if not self.running or not self._attach_socket:
            return None
        
        try:
            # Read from container stdout/stderr
            # This is a simplified implementation
            data = self._attach_socket._sock.recv(4096)
            if data:
                return data.decode("utf-8", errors="replace").strip()
            return None
        except Exception as e:
            logger.error(f"Failed to receive message: {e}")
            return None

    async def proxy_request(self, request_data: bytes) -> bytes:
        """Proxy an MCP request through the container."""
        if not self.running:
            raise RuntimeError("Transport not running")
        
        try:
            # Send request
            await self.send_message(request_data.decode())
            
            # Wait for response
            response = await self.receive_message()
            if response:
                return response.encode()
            else:
                raise RuntimeError("No response received")
                
        except Exception as e:
            logger.error(f"Failed to proxy request: {e}")
            raise

    def get_url(self) -> str:
        """Get the transport URL."""
        # STDIO doesn't have a URL, but we can return a placeholder
        return f"stdio://{self.container_id[:12]}"

    async def health_check(self) -> bool:
        """Check if the transport is healthy."""
        try:
            if not self.running or not self._container:
                return False
            
            # Reload container status
            self._container.reload()
            return self._container.status == "running"
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False