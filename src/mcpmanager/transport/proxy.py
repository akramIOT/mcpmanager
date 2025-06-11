"""HTTP proxy functionality for MCP servers."""

import asyncio
import logging
from typing import Dict, List, Optional, Any
import json

import aiohttp
from aiohttp import web, ClientSession
import httpx

from mcpmanager.transport.base import BaseTransport
from mcpmanager.exceptions import TransportError

logger = logging.getLogger(__name__)


class MCPProxyMiddleware:
    """Middleware for MCP proxy processing."""

    def __init__(self, name: str):
        """Initialize middleware."""
        self.name = name

    async def __call__(self, request: web.Request, handler):
        """Process request through middleware."""
        # Add correlation ID
        request["correlation_id"] = f"{self.name}-{id(request)}"
        
        # Log request
        logger.debug(f"[{request['correlation_id']}] {request.method} {request.path}")
        
        try:
            response = await handler(request)
            logger.debug(f"[{request['correlation_id']}] Response: {response.status}")
            return response
        except Exception as e:
            logger.error(f"[{request['correlation_id']}] Error: {e}")
            raise


class HTTPProxy(BaseTransport):
    """HTTP proxy for MCP communication with middleware support."""

    def __init__(
        self,
        container_id: str,
        port: int,
        target_port: Optional[int] = None,
        host: str = "localhost",
        middlewares: Optional[List] = None,
        **kwargs
    ):
        """Initialize HTTP proxy."""
        super().__init__(container_id)
        self.port = port
        self.target_port = target_port or port
        self.host = host
        self.middlewares = middlewares or []
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._session: Optional[ClientSession] = None

    async def start(self) -> None:
        """Start HTTP proxy."""
        await super().start()
        
        try:
            # Create aiohttp application
            self._app = web.Application()
            
            # Add middlewares
            for middleware in self.middlewares:
                if hasattr(middleware, '__call__'):
                    self._app.middlewares.append(middleware)
                else:
                    # Wrap class-based middleware
                    self._app.middlewares.append(middleware)
            
            # Add default middleware
            self._app.middlewares.append(MCPProxyMiddleware(f"proxy-{self.container_id[:12]}"))
            
            # Add routes
            self._app.router.add_route("*", "/mcp/{path:.*}", self._handle_mcp_request)
            self._app.router.add_route("*", "/{path:.*}", self._handle_proxy_request)
            
            # Setup CORS
            self._setup_cors()
            
            # Create HTTP session for upstream requests
            connector = aiohttp.TCPConnector(limit=100)
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = ClientSession(connector=connector, timeout=timeout)
            
            # Start server
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            
            self._site = web.TCPSite(self._runner, self.host, self.port)
            await self._site.start()
            
            logger.info(f"HTTP proxy started on {self.host}:{self.port} -> {self.target_port}")
            
        except Exception as e:
            logger.error(f"Failed to start HTTP proxy: {e}")
            await self.stop()
            raise TransportError(f"Failed to start HTTP proxy: {e}")

    async def stop(self) -> None:
        """Stop HTTP proxy."""
        try:
            if self._session:
                await self._session.close()
                self._session = None
            
            if self._site:
                await self._site.stop()
                self._site = None
            
            if self._runner:
                await self._runner.cleanup()
                self._runner = None
            
        except Exception as e:
            logger.warning(f"Error stopping HTTP proxy: {e}")
        
        await super().stop()

    def _setup_cors(self) -> None:
        """Setup CORS for the proxy."""
        @web.middleware
        async def cors_middleware(request: web.Request, handler):
            """CORS middleware."""
            # Handle preflight requests
            if request.method == "OPTIONS":
                response = web.Response()
            else:
                response = await handler(request)
            
            # Add CORS headers
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
            response.headers["Access-Control-Max-Age"] = "3600"
            
            return response
        
        self._app.middlewares.append(cors_middleware)

    async def _handle_mcp_request(self, request: web.Request) -> web.Response:
        """Handle MCP-specific requests."""
        path = request.match_info.get("path", "")
        
        # Build upstream URL
        upstream_url = f"http://localhost:{self.target_port}/mcp/{path}"
        if request.query_string:
            upstream_url += f"?{request.query_string}"
        
        try:
            # Read request body
            body = await request.read()
            
            # Forward request to container
            async with self._session.request(
                method=request.method,
                url=upstream_url,
                headers=dict(request.headers),
                data=body,
            ) as upstream_response:
                
                # Read response
                response_body = await upstream_response.read()
                
                # Create response
                response = web.Response(
                    body=response_body,
                    status=upstream_response.status,
                    headers=dict(upstream_response.headers),
                )
                
                # Add proxy headers
                response.headers["X-Proxy-By"] = "MCPManager"
                response.headers["X-Container-ID"] = self.container_id[:12]
                
                return response
                
        except Exception as e:
            logger.error(f"Error proxying MCP request: {e}")
            return web.json_response(
                {"error": "Proxy error", "message": str(e)},
                status=502
            )

    async def _handle_proxy_request(self, request: web.Request) -> web.Response:
        """Handle general proxy requests."""
        path = request.match_info.get("path", "")
        
        # Build upstream URL
        upstream_url = f"http://localhost:{self.target_port}/{path}"
        if request.query_string:
            upstream_url += f"?{request.query_string}"
        
        try:
            # Read request body
            body = await request.read()
            
            # Forward request to container
            async with self._session.request(
                method=request.method,
                url=upstream_url,
                headers=dict(request.headers),
                data=body,
            ) as upstream_response:
                
                # Read response
                response_body = await upstream_response.read()
                
                # Create response
                response = web.Response(
                    body=response_body,
                    status=upstream_response.status,
                    headers=dict(upstream_response.headers),
                )
                
                # Add proxy headers
                response.headers["X-Proxy-By"] = "MCPManager"
                
                return response
                
        except Exception as e:
            logger.error(f"Error proxying request: {e}")
            return web.json_response(
                {"error": "Proxy error", "message": str(e)},
                status=502
            )

    def get_url(self) -> str:
        """Get the proxy URL."""
        return f"http://{self.host}:{self.port}"

    def get_mcp_url(self) -> str:
        """Get the MCP-specific URL."""
        return f"http://{self.host}:{self.port}/mcp"

    async def health_check(self) -> bool:
        """Check if the proxy is healthy."""
        try:
            if not self.running or not self._session:
                return False
            
            # Check if proxy is responding
            async with self._session.get(f"http://{self.host}:{self.port}/health") as response:
                return response.status == 200
                
        except Exception:
            return False


class TransparentProxy:
    """Transparent proxy with automatic transport switching."""

    def __init__(self, container_id: str):
        """Initialize transparent proxy."""
        self.container_id = container_id
        self.stdio_transport = None
        self.sse_transport = None
        self.http_proxy = None
        self.active_transport = None

    async def start(self, config: Dict[str, Any]) -> None:
        """Start transparent proxy with automatic transport detection."""
        transport_type = config.get("transport", "auto")
        
        if transport_type == "auto":
            # Try to detect best transport
            transport_type = await self._detect_best_transport(config)
        
        if transport_type == "stdio":
            from mcpmanager.transport.stdio import StdioTransport
            self.active_transport = StdioTransport(self.container_id)
        elif transport_type == "sse":
            from mcpmanager.transport.sse import SSETransport
            self.active_transport = SSETransport(
                container_id=self.container_id,
                port=config.get("port", 8080),
                target_port=config.get("target_port")
            )
        elif transport_type == "proxy":
            self.active_transport = HTTPProxy(
                container_id=self.container_id,
                port=config.get("port", 8080),
                target_port=config.get("target_port"),
                middlewares=config.get("middlewares", [])
            )
        else:
            raise TransportError(f"Unsupported transport type: {transport_type}")
        
        await self.active_transport.start()
        logger.info(f"Transparent proxy started with {transport_type} transport")

    async def stop(self) -> None:
        """Stop transparent proxy."""
        if self.active_transport:
            await self.active_transport.stop()
            self.active_transport = None

    async def _detect_best_transport(self, config: Dict[str, Any]) -> str:
        """Detect the best transport type for the container."""
        # Simple heuristics for transport detection
        if config.get("port"):
            return "sse"  # If port is specified, use SSE
        
        # Default to stdio for simplicity
        return "stdio"

    def get_url(self) -> str:
        """Get the proxy URL."""
        if self.active_transport and hasattr(self.active_transport, "get_url"):
            return self.active_transport.get_url()
        return f"proxy://{self.container_id[:12]}"


class ProxyManager:
    """Manager for HTTP proxies."""

    def __init__(self):
        """Initialize proxy manager."""
        self.proxies: Dict[str, HTTPProxy] = {}

    async def create_proxy(
        self,
        container_id: str,
        port: int,
        target_port: Optional[int] = None,
        middlewares: Optional[List] = None
    ) -> HTTPProxy:
        """Create and start a new proxy."""
        if container_id in self.proxies:
            raise ValueError(f"Proxy for container {container_id} already exists")

        proxy = HTTPProxy(
            container_id=container_id,
            port=port,
            target_port=target_port,
            middlewares=middlewares
        )
        
        await proxy.start()
        self.proxies[container_id] = proxy
        
        return proxy

    async def stop_proxy(self, container_id: str) -> None:
        """Stop and remove a proxy."""
        if container_id in self.proxies:
            proxy = self.proxies[container_id]
            await proxy.stop()
            del self.proxies[container_id]

    async def stop_all_proxies(self) -> None:
        """Stop all proxies."""
        for container_id in list(self.proxies.keys()):
            await self.stop_proxy(container_id)

    def get_proxy(self, container_id: str) -> Optional[HTTPProxy]:
        """Get proxy for container."""
        return self.proxies.get(container_id)

    def list_proxies(self) -> List[str]:
        """List all active proxy container IDs."""
        return list(self.proxies.keys())