"""SSE (Server-Sent Events) transport implementation."""

import asyncio
import logging
from typing import Optional, Dict, Any
import json
import aiohttp
from aiohttp import web
import httpx

from mcpmanager.transport.base import BaseTransport

logger = logging.getLogger(__name__)


class SSETransport(BaseTransport):
    """SSE transport for MCP communication."""

    def __init__(
        self,
        container_id: str,
        port: int,
        target_port: Optional[int] = None,
        host: str = "localhost",
        **kwargs,
    ):
        """Initialize SSE transport."""
        super().__init__(container_id)
        self.port = port
        self.target_port = target_port or port
        self.host = host
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._session: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        """Start SSE transport."""
        await super().start()
        
        try:
            # Create aiohttp application
            self._app = web.Application()
            
            # Add routes for MCP proxy
            self._app.router.add_post("/mcp", self._handle_mcp_request)
            self._app.router.add_get("/mcp/sse", self._handle_sse_connection)
            self._app.router.add_get("/health", self._handle_health_check)
            self._app.router.add_get("/", self._handle_root)
            
            # Enable CORS
            self._setup_cors()
            
            # Create runner and start server
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            
            self._site = web.TCPSite(self._runner, self.host, self.port)
            await self._site.start()
            
            # Create HTTP session for container communication
            self._session = httpx.AsyncClient(timeout=30.0)
            
            logger.info(f"SSE transport started on {self.host}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start SSE transport: {e}")
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop SSE transport."""
        try:
            if self._session:
                await self._session.aclose()
                self._session = None
            
            if self._site:
                await self._site.stop()
                self._site = None
            
            if self._runner:
                await self._runner.cleanup()
                self._runner = None
            
        except Exception as e:
            logger.warning(f"Error stopping SSE transport: {e}")
        
        await super().stop()

    def _setup_cors(self) -> None:
        """Setup CORS for the web application."""
        async def cors_middleware(request: web.Request, handler):
            """CORS middleware."""
            response = await handler(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            return response
        
        # Add CORS middleware
        self._app.middlewares.append(cors_middleware)
        
        # Handle preflight requests
        async def options_handler(request: web.Request):
            return web.Response(
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                }
            )
        
        self._app.router.add_options("/{path:.*}", options_handler)

    async def _handle_mcp_request(self, request: web.Request) -> web.Response:
        """Handle MCP request and proxy to container."""
        try:
            # Read request data
            request_data = await request.read()
            
            # Proxy to container
            container_url = f"http://localhost:{self.target_port}/mcp"
            
            async with self._session.post(container_url, content=request_data) as response:
                response_data = await response.read()
                
                return web.Response(
                    body=response_data,
                    content_type=response.headers.get("content-type", "application/json"),
                    status=response.status_code,
                )
                
        except Exception as e:
            logger.error(f"Failed to proxy MCP request: {e}")
            return web.json_response(
                {"error": "Internal server error"},
                status=500,
            )

    async def _handle_sse_connection(self, request: web.Request) -> web.StreamResponse:
        """Handle SSE connection for real-time communication."""
        response = web.StreamResponse()
        response.headers["Content-Type"] = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        
        await response.prepare(request)
        
        try:
            # Connect to container SSE endpoint
            container_url = f"http://localhost:{self.target_port}/mcp/sse"
            
            async with self._session.stream("GET", container_url) as container_response:
                async for chunk in container_response.aiter_bytes():
                    await response.write(chunk)
                    
        except Exception as e:
            logger.error(f"SSE connection error: {e}")
            await response.write(f"event: error\ndata: {str(e)}\n\n".encode())
        
        return response

    async def _handle_health_check(self, request: web.Request) -> web.Response:
        """Handle health check requests."""
        try:
            # Check if container is responding
            container_url = f"http://localhost:{self.target_port}/health"
            
            async with self._session.get(container_url) as response:
                if response.status_code == 200:
                    return web.json_response({"status": "healthy"})
                else:
                    return web.json_response(
                        {"status": "unhealthy", "container_status": response.status_code},
                        status=503,
                    )
                    
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return web.json_response(
                {"status": "unhealthy", "error": str(e)},
                status=503,
            )

    async def _handle_root(self, request: web.Request) -> web.Response:
        """Handle root requests."""
        return web.json_response({
            "service": "MCPManager SSE Transport",
            "container_id": self.container_id[:12],
            "endpoints": {
                "mcp": "/mcp",
                "sse": "/mcp/sse",
                "health": "/health",
            }
        })

    async def send_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request to the container and get response."""
        if not self.running or not self._session:
            raise RuntimeError("Transport not running")
        
        try:
            container_url = f"http://localhost:{self.target_port}/mcp"
            
            async with self._session.post(
                container_url,
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code == 200:
                    return await response.json()
                else:
                    raise RuntimeError(f"Container returned status {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Failed to send request: {e}")
            raise

    def get_url(self) -> str:
        """Get the transport URL."""
        return f"http://{self.host}:{self.port}/mcp"

    def get_sse_url(self) -> str:
        """Get the SSE endpoint URL."""
        return f"http://{self.host}:{self.port}/mcp/sse"

    async def health_check(self) -> bool:
        """Check if the transport is healthy."""
        try:
            if not self.running or not self._session:
                return False
            
            # Check container health
            container_url = f"http://localhost:{self.target_port}/health"
            
            async with self._session.get(container_url) as response:
                return response.status_code == 200
                
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    async def get_server_info(self) -> Dict[str, Any]:
        """Get information about the MCP server."""
        try:
            if not self.running or not self._session:
                raise RuntimeError("Transport not running")
            
            container_url = f"http://localhost:{self.target_port}/info"
            
            async with self._session.get(container_url) as response:
                if response.status_code == 200:
                    return await response.json()
                else:
                    return {"error": f"Server returned status {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"Failed to get server info: {e}")
            return {"error": str(e)}