"""FastAPI server for MCPManager REST API."""

import logging
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mcpmanager.core.manager import MCPManager
from mcpmanager.core.models import (
    MCPServerConfig,
    MCPServerInstance,
    ContainerInfo,
    DiscoveredClient,
    TransportType,
)
from mcpmanager.core.discovery import MCPDiscovery

logger = logging.getLogger(__name__)

# Global manager instance
manager: Optional[MCPManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    global manager
    
    # Startup
    manager = MCPManager()
    await manager.initialize()
    logger.info("MCPManager API server started")
    
    yield
    
    # Shutdown
    if manager:
        await manager.cleanup()
    logger.info("MCPManager API server stopped")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="MCPManager API",
        description="REST API for MCPManager - Secure MCP Server Management",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Frontend origins
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Add routes
    app.include_router(servers_router, prefix="/api/v1/servers", tags=["servers"])
    app.include_router(discovery_router, prefix="/api/v1/discovery", tags=["discovery"])
    app.include_router(registry_router, prefix="/api/v1/registry", tags=["registry"])
    app.include_router(config_router, prefix="/api/v1/config", tags=["config"])
    app.include_router(inspector_router, prefix="/api/v1/inspector", tags=["inspector"])

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "service": "MCPManager API",
            "version": "0.1.0",
            "docs": "/docs",
            "openapi": "/openapi.json",
        }

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "mcpmanager-api"}

    return app


# Dependency to get manager instance
async def get_manager() -> MCPManager:
    """Get MCPManager instance."""
    if not manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCPManager not initialized"
        )
    return manager


# Request/Response models
class RunServerRequest(BaseModel):
    """Request model for running a server."""
    server_name: str
    image: Optional[str] = None
    transport: TransportType = TransportType.STDIO
    port: Optional[int] = None
    target_port: Optional[int] = None
    environment: Dict[str, str] = {}
    secrets: Dict[str, str] = {}
    detach: bool = True


class ServerResponse(BaseModel):
    """Response model for server information."""
    name: str
    container_id: str
    status: str
    image: str
    url: Optional[str] = None
    created_at: str
    config: Dict[str, Any]


# Routers
from fastapi import APIRouter

servers_router = APIRouter()


@servers_router.post("/run", response_model=ServerResponse)
async def run_server(
    request: RunServerRequest,
    mgr: MCPManager = Depends(get_manager)
):
    """Run an MCP server."""
    try:
        # Create config if custom image provided
        config = None
        if request.image:
            config = MCPServerConfig(
                name=request.server_name,
                image=request.image,
                transport=request.transport,
                port=request.port,
                target_port=request.target_port,
                environment=request.environment,
            )

        instance = await mgr.run_server(
            server_name=request.server_name,
            config=config,
            secrets=request.secrets,
        )

        return ServerResponse(
            name=instance.name,
            container_id=instance.container_id,
            status=instance.status.value,
            image=instance.config.image,
            url=instance.url,
            created_at=instance.created_at.isoformat(),
            config=instance.config.model_dump(),
        )

    except Exception as e:
        logger.error(f"Failed to run server: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@servers_router.get("/", response_model=List[ServerResponse])
async def list_servers(
    all: bool = False,
    mgr: MCPManager = Depends(get_manager)
):
    """List MCP servers."""
    try:
        instances = await mgr.list_servers(all=all)
        
        return [
            ServerResponse(
                name=instance.name,
                container_id=instance.container_id,
                status=instance.status.value,
                image=instance.config.image,
                url=instance.url,
                created_at=instance.created_at.isoformat(),
                config=instance.config.model_dump(),
            )
            for instance in instances
        ]

    except Exception as e:
        logger.error(f"Failed to list servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@servers_router.get("/{server_name}", response_model=ServerResponse)
async def get_server(
    server_name: str,
    mgr: MCPManager = Depends(get_manager)
):
    """Get information about a specific server."""
    try:
        instance = await mgr.get_server_status(server_name)
        if not instance:
            raise HTTPException(status_code=404, detail=f"Server {server_name} not found")

        return ServerResponse(
            name=instance.name,
            container_id=instance.container_id,
            status=instance.status.value,
            image=instance.config.image,
            url=instance.url,
            created_at=instance.created_at.isoformat(),
            config=instance.config.model_dump(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get server info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@servers_router.post("/{server_name}/stop")
async def stop_server(
    server_name: str,
    mgr: MCPManager = Depends(get_manager)
):
    """Stop an MCP server."""
    try:
        await mgr.stop_server(server_name)
        return {"message": f"Server {server_name} stopped successfully"}

    except Exception as e:
        logger.error(f"Failed to stop server: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@servers_router.post("/{server_name}/restart", response_model=ServerResponse)
async def restart_server(
    server_name: str,
    mgr: MCPManager = Depends(get_manager)
):
    """Restart an MCP server."""
    try:
        instance = await mgr.restart_server(server_name)

        return ServerResponse(
            name=instance.name,
            container_id=instance.container_id,
            status=instance.status.value,
            image=instance.config.image,
            url=instance.url,
            created_at=instance.created_at.isoformat(),
            config=instance.config.model_dump(),
        )

    except Exception as e:
        logger.error(f"Failed to restart server: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@servers_router.delete("/{server_name}")
async def remove_server(
    server_name: str,
    force: bool = False,
    mgr: MCPManager = Depends(get_manager)
):
    """Remove an MCP server."""
    try:
        await mgr.remove_server(server_name, force=force)
        return {"message": f"Server {server_name} removed successfully"}

    except Exception as e:
        logger.error(f"Failed to remove server: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@servers_router.get("/{server_name}/logs")
async def get_server_logs(
    server_name: str,
    follow: bool = False,
    tail: int = 100,
    mgr: MCPManager = Depends(get_manager)
):
    """Get logs for an MCP server."""
    try:
        logs = await mgr.get_server_logs(server_name, follow=follow, tail=tail)
        return {"logs": logs}

    except Exception as e:
        logger.error(f"Failed to get server logs: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# Discovery router
discovery_router = APIRouter()


@discovery_router.get("/clients", response_model=List[Dict[str, Any]])
async def discover_clients():
    """Discover installed MCP clients."""
    try:
        discovery = MCPDiscovery()
        clients = await discovery.discover_clients()
        
        return [
            {
                "client_type": client.client_type.value,
                "installed": client.installed,
                "registered": client.registered,
                "config_path": client.config_path,
            }
            for client in clients
        ]

    except Exception as e:
        logger.error(f"Failed to discover clients: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@discovery_router.get("/servers")
async def discover_servers():
    """Discover MCP servers in the environment."""
    try:
        discovery = MCPDiscovery()
        servers = await discovery.scan_for_mcp_servers()
        return servers

    except Exception as e:
        logger.error(f"Failed to discover servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@discovery_router.post("/configure-client")
async def configure_client(
    client_type: str,
    server_name: str,
    server_url: str
):
    """Configure a client with an MCP server."""
    try:
        from mcpmanager.core.models import MCPClientType
        
        client_enum = MCPClientType(client_type)
        discovery = MCPDiscovery()
        
        success = await discovery.auto_configure_client(
            client_enum, server_name, server_url
        )
        
        return {"success": success, "message": f"Client {client_type} configured" if success else "Configuration failed"}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid client type: {client_type}")
    except Exception as e:
        logger.error(f"Failed to configure client: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Registry router
registry_router = APIRouter()


@registry_router.get("/servers", response_model=List[Dict[str, Any]])
async def list_registry_servers(mgr: MCPManager = Depends(get_manager)):
    """List all servers in the registry."""
    try:
        servers = await mgr.registry.list_servers()
        
        return [
            {
                "name": server.name,
                "description": server.description,
                "image": server.image,
                "version": server.version,
                "tags": server.tags,
                "transport": server.transport.value,
            }
            for server in servers
        ]

    except Exception as e:
        logger.error(f"Failed to list registry servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@registry_router.get("/servers/search")
async def search_registry_servers(
    query: str,
    mgr: MCPManager = Depends(get_manager)
):
    """Search for servers in the registry."""
    try:
        servers = await mgr.search_servers(query)
        
        return [
            {
                "name": server.name,
                "description": server.description,
                "image": server.image,
                "version": server.version,
                "tags": server.tags,
                "transport": server.transport.value,
            }
            for server in servers
        ]

    except Exception as e:
        logger.error(f"Failed to search registry servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@registry_router.get("/servers/{server_name}")
async def get_registry_server_info(
    server_name: str,
    mgr: MCPManager = Depends(get_manager)
):
    """Get detailed information about a registry server."""
    try:
        info = await mgr.registry.get_server_info(server_name)
        return info

    except Exception as e:
        logger.error(f"Failed to get server info: {e}")
        raise HTTPException(status_code=404, detail=f"Server {server_name} not found")


@registry_router.get("/info")
async def get_registry_info(mgr: MCPManager = Depends(get_manager)):
    """Get registry information."""
    try:
        info = mgr.registry.get_registry_info()
        return info

    except Exception as e:
        logger.error(f"Failed to get registry info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Config router
config_router = APIRouter()


@config_router.get("/")
async def get_config(mgr: MCPManager = Depends(get_manager)):
    """Get current configuration."""
    try:
        config = await mgr.config_manager.get_config()
        return config.model_dump()

    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@config_router.post("/auto-discovery")
async def set_auto_discovery(
    enabled: bool,
    mgr: MCPManager = Depends(get_manager)
):
    """Enable or disable auto-discovery."""
    try:
        await mgr.config_manager.set_auto_discovery(enabled)
        return {"message": f"Auto-discovery {'enabled' if enabled else 'disabled'}"}

    except Exception as e:
        logger.error(f"Failed to set auto-discovery: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@config_router.post("/registry-url")
async def set_registry_url(
    url: Optional[str],
    mgr: MCPManager = Depends(get_manager)
):
    """Set registry URL."""
    try:
        await mgr.config_manager.set_registry_url(url)
        return {"message": f"Registry URL set to: {url or 'built-in'}"}

    except Exception as e:
        logger.error(f"Failed to set registry URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Inspector router
inspector_router = APIRouter()


@inspector_router.get("/{server_name}/debug")
async def get_debug_info(
    server_name: str,
    mgr: MCPManager = Depends(get_manager)
):
    """Get debug information for a server."""
    try:
        debug_info = await mgr.inspector.get_server_debug_info(server_name)
        return {
            "name": debug_info.name,
            "container_id": debug_info.container_id,
            "status": debug_info.status,
            "image": debug_info.image,
            "ports": debug_info.ports,
            "environment": debug_info.environment,
            "labels": debug_info.labels,
            "created_at": debug_info.created_at.isoformat(),
            "started_at": debug_info.started_at.isoformat() if debug_info.started_at else None,
            "finished_at": debug_info.finished_at.isoformat() if debug_info.finished_at else None,
            "exit_code": debug_info.exit_code,
            "restart_count": debug_info.restart_count,
            "network_settings": debug_info.network_settings,
            "mounts": debug_info.mounts,
        }

    except Exception as e:
        logger.error(f"Failed to get debug info: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@inspector_router.get("/{server_name}/metrics")
async def get_metrics(
    server_name: str,
    mgr: MCPManager = Depends(get_manager)
):
    """Get current metrics for a server."""
    try:
        metrics = await mgr.inspector.collect_metrics(server_name)
        return {
            "container_id": metrics.container_id,
            "cpu_percent": metrics.cpu_percent,
            "memory_usage_mb": metrics.memory_usage_mb,
            "memory_percent": metrics.memory_percent,
            "network_io_read_mb": metrics.network_io_read_mb,
            "network_io_write_mb": metrics.network_io_write_mb,
            "disk_io_read_mb": metrics.disk_io_read_mb,
            "disk_io_write_mb": metrics.disk_io_write_mb,
            "timestamp": metrics.timestamp.isoformat(),
            "uptime_seconds": metrics.uptime_seconds,
        }

    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@inspector_router.get("/{server_name}/metrics/history")
async def get_metrics_history(
    server_name: str,
    duration_minutes: int = 60,
    mgr: MCPManager = Depends(get_manager)
):
    """Get metrics history for a server."""
    try:
        history = await mgr.inspector.get_metrics_history(server_name, duration_minutes)
        return [
            {
                "container_id": metric.container_id,
                "cpu_percent": metric.cpu_percent,
                "memory_usage_mb": metric.memory_usage_mb,
                "memory_percent": metric.memory_percent,
                "network_io_read_mb": metric.network_io_read_mb,
                "network_io_write_mb": metric.network_io_write_mb,
                "disk_io_read_mb": metric.disk_io_read_mb,
                "disk_io_write_mb": metric.disk_io_write_mb,
                "timestamp": metric.timestamp.isoformat(),
                "uptime_seconds": metric.uptime_seconds,
            }
            for metric in history
        ]

    except Exception as e:
        logger.error(f"Failed to get metrics history: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@inspector_router.get("/{server_name}/analyze")
async def analyze_performance(
    server_name: str,
    mgr: MCPManager = Depends(get_manager)
):
    """Analyze server performance."""
    try:
        analysis = await mgr.inspector.analyze_performance(server_name)
        return analysis

    except Exception as e:
        logger.error(f"Failed to analyze performance: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@inspector_router.get("/{server_name}/trace")
async def trace_communication(
    server_name: str,
    duration_seconds: int = 60,
    mgr: MCPManager = Depends(get_manager)
):
    """Trace MCP communication."""
    try:
        trace_data = await mgr.inspector.trace_mcp_communication(server_name, duration_seconds)
        return {"trace_data": trace_data}

    except Exception as e:
        logger.error(f"Failed to trace communication: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@inspector_router.get("/{server_name}/report")
async def generate_debug_report(
    server_name: str,
    mgr: MCPManager = Depends(get_manager)
):
    """Generate comprehensive debug report."""
    try:
        report = await mgr.inspector.generate_debug_report(server_name)
        return report

    except Exception as e:
        logger.error(f"Failed to generate debug report: {e}")
        raise HTTPException(status_code=404, detail=str(e))


@inspector_router.post("/{server_name}/report/export")
async def export_debug_report(
    server_name: str,
    output_path: str,
    mgr: MCPManager = Depends(get_manager)
):
    """Export debug report to file."""
    try:
        file_path = await mgr.inspector.export_debug_report(server_name, output_path)
        return {"message": f"Debug report exported to {file_path}", "file_path": file_path}

    except Exception as e:
        logger.error(f"Failed to export debug report: {e}")
        raise HTTPException(status_code=500, detail=str(e))