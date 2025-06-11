"""Transport factory for creating transport instances."""

import logging
from typing import Optional

from mcpmanager.core.models import TransportType
from mcpmanager.transport.base import BaseTransport
from mcpmanager.transport.stdio import StdioTransport
from mcpmanager.transport.sse import SSETransport
from mcpmanager.transport.proxy import HTTPProxy, TransparentProxy

logger = logging.getLogger(__name__)


class TransportFactory:
    """Factory for creating transport instances."""

    async def create_transport(
        self,
        transport_type: TransportType,
        container_id: str,
        port: Optional[int] = None,
        target_port: Optional[int] = None,
        host: str = "localhost",
        **kwargs,
    ):
        """Create a transport instance based on type."""
        if transport_type == TransportType.STDIO:
            return StdioTransport(container_id=container_id, **kwargs)
        elif transport_type == TransportType.SSE:
            if not port:
                raise ValueError("Port is required for SSE transport")
            return SSETransport(
                container_id=container_id,
                port=port,
                target_port=target_port,
                host=host,
                **kwargs,
            )
        elif transport_type == TransportType.PROXY:
            if not port:
                raise ValueError("Port is required for proxy transport")
            return HTTPProxy(
                container_id=container_id,
                port=port,
                target_port=target_port,
                host=host,
                **kwargs,
            )
        elif transport_type == TransportType.TRANSPARENT:
            proxy = TransparentProxy(container_id=container_id)
            config = {
                "port": port,
                "target_port": target_port,
                "host": host,
                **kwargs,
            }
            await proxy.start(config)
            return proxy
        else:
            raise ValueError(f"Unsupported transport type: {transport_type}")