"""CLI command implementations."""

import asyncio
import json
import sys
from typing import Optional, Dict, Any
from pathlib import Path

import click
from mcpmanager.core.manager import MCPManager
from mcpmanager.core.discovery import MCPDiscovery
from mcpmanager.core.models import (
    MCPServerConfig,
    TransportType,
    PermissionProfile,
    SecretReference,
)
from mcpmanager.config.manager import ConfigManager
from mcpmanager.inspector import DebugSession
from mcpmanager.runtime.base import RuntimeType


async def get_manager(ctx: click.Context) -> MCPManager:
    """Get or create MCPManager instance."""
    if not hasattr(ctx.obj, 'manager') or ctx.obj.manager is None:
        ctx.obj.manager = MCPManager()
        await ctx.obj.manager.initialize()
    return ctx.obj.manager


async def run_cmd(
    ctx: click.Context,
    server_name: str,
    image: Optional[str],
    transport: str,
    port: Optional[int],
    target_port: Optional[int],
    env: tuple,
    secret: tuple,
    detach: bool,
    permission_profile: Optional[str],
    runtime: Optional[str] = None,
) -> None:
    """Run command implementation."""
    manager = await get_manager(ctx)
    
    try:
        # Parse environment variables
        environment = {}
        for env_var in env:
            if "=" not in env_var:
                raise click.BadParameter(f"Invalid environment variable format: {env_var}")
            key, value = env_var.split("=", 1)
            environment[key] = value
        
        # Parse secrets
        secrets = {}
        secret_refs = []
        for secret_spec in secret:
            if "," not in secret_spec or "=" not in secret_spec:
                raise click.BadParameter(f"Invalid secret format: {secret_spec}")
            secret_name, target_part = secret_spec.split(",", 1)
            if not target_part.startswith("target="):
                raise click.BadParameter(f"Invalid secret format: {secret_spec}")
            target = target_part[7:]  # Remove "target="
            secrets[secret_name] = target
            secret_refs.append(SecretReference(name=secret_name, target=target))
        
        # Load permission profile if provided
        profile = None
        if permission_profile:
            profile_path = Path(permission_profile)
            if not profile_path.exists():
                raise click.BadParameter(f"Permission profile file not found: {permission_profile}")
            
            with open(profile_path, 'r') as f:
                profile_data = json.load(f)
            profile = PermissionProfile(**profile_data)
        
        # Create or get server config
        config = None
        if image:
            # Custom server configuration
            config = MCPServerConfig(
                name=server_name,
                image=image,
                transport=TransportType(transport),
                port=port,
                target_port=target_port,
                environment=environment,
                secrets=secret_refs,
                permission_profile=profile,
            )
        
        # Run the server
        instance = await manager.run_server(
            server_name=server_name,
            config=config,
            secrets=secrets,
        )
        
        click.echo(f"MCP server '{server_name}' started successfully")
        if instance.url:
            click.echo(f"Server URL: {instance.url}")
        
        # Auto-configure clients if enabled
        config_manager = ConfigManager()
        config_data = await config_manager.get_config()
        if config_data.auto_discovery_enabled:
            discovery = MCPDiscovery()
            results = await discovery.auto_configure_all_clients(
                server_name, instance.url or f"http://localhost:{port or 8080}"
            )
            
            for client_type, success in results.items():
                if success:
                    click.echo(f"Configured {client_type.value} client")
        
        if not detach:
            click.echo("Press Ctrl+C to stop the server")
            try:
                # Keep the process running
                while True:
                    status = await manager.get_server_status(server_name)
                    if not status or status.status != "running":
                        break
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                click.echo("\nStopping server...")
                await manager.stop_server(server_name)
    
    except Exception as e:
        click.echo(f"Error running server: {e}", err=True)
        sys.exit(1)


async def list_cmd(ctx: click.Context, all: bool, format: str) -> None:
    """List command implementation."""
    manager = await get_manager(ctx)
    
    try:
        instances = await manager.list_servers(all=all)
        
        if format == "json":
            data = [
                {
                    "name": instance.name,
                    "container_id": instance.container_id,
                    "status": instance.status.value,
                    "image": instance.config.image,
                    "created": instance.created_at.isoformat(),
                    "url": instance.url,
                }
                for instance in instances
            ]
            click.echo(json.dumps(data, indent=2))
        else:
            # Table format
            if not instances:
                click.echo("No MCP servers found")
                return
            
            click.echo(f"{'Name':<20} {'Status':<12} {'Image':<30} {'URL':<40}")
            click.echo("-" * 100)
            
            for instance in instances:
                url = instance.url or "N/A"
                click.echo(f"{instance.name:<20} {instance.status.value:<12} {instance.config.image:<30} {url:<40}")
    
    except Exception as e:
        click.echo(f"Error listing servers: {e}", err=True)
        sys.exit(1)


async def stop_cmd(ctx: click.Context, server_name: str) -> None:
    """Stop command implementation."""
    manager = await get_manager(ctx)
    
    try:
        await manager.stop_server(server_name)
        click.echo(f"MCP server '{server_name}' stopped successfully")
    except Exception as e:
        click.echo(f"Error stopping server: {e}", err=True)
        sys.exit(1)


async def remove_cmd(ctx: click.Context, server_name: str, force: bool) -> None:
    """Remove command implementation."""
    manager = await get_manager(ctx)
    
    try:
        await manager.remove_server(server_name, force=force)
        click.echo(f"MCP server '{server_name}' removed successfully")
    except Exception as e:
        click.echo(f"Error removing server: {e}", err=True)
        sys.exit(1)


async def restart_cmd(ctx: click.Context, server_name: str) -> None:
    """Restart command implementation."""
    manager = await get_manager(ctx)
    
    try:
        instance = await manager.restart_server(server_name)
        click.echo(f"MCP server '{server_name}' restarted successfully")
        if instance.url:
            click.echo(f"Server URL: {instance.url}")
    except Exception as e:
        click.echo(f"Error restarting server: {e}", err=True)
        sys.exit(1)


async def logs_cmd(ctx: click.Context, server_name: str, follow: bool, tail: int) -> None:
    """Logs command implementation."""
    manager = await get_manager(ctx)
    
    try:
        logs = await manager.get_server_logs(server_name, follow=follow, tail=tail)
        click.echo(logs)
    except Exception as e:
        click.echo(f"Error getting logs: {e}", err=True)
        sys.exit(1)


async def search_cmd(ctx: click.Context, query: str) -> None:
    """Search command implementation."""
    manager = await get_manager(ctx)
    
    try:
        servers = await manager.search_servers(query)
        
        if not servers:
            click.echo(f"No servers found matching '{query}'")
            return
        
        click.echo(f"Found {len(servers)} server(s) matching '{query}':")
        click.echo()
        
        for server in servers:
            click.echo(f"Name: {server.name}")
            if server.description:
                click.echo(f"Description: {server.description}")
            click.echo(f"Image: {server.image}")
            if server.tags:
                click.echo(f"Tags: {', '.join(server.tags)}")
            click.echo("-" * 50)
    
    except Exception as e:
        click.echo(f"Error searching servers: {e}", err=True)
        sys.exit(1)


async def serve_cmd(ctx: click.Context, host: str, port: int) -> None:
    """Serve command implementation."""
    try:
        from mcpmanager.api.server import create_app
        import uvicorn
        
        app = create_app()
        
        click.echo(f"Starting MCPManager API server on {host}:{port}")
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
    
    except ImportError:
        click.echo("API server dependencies not installed. Install with: pip install 'mcpmanager[api]'", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error starting API server: {e}", err=True)
        sys.exit(1)


# Command groups
@click.group()
def config_cmd():
    """Configuration management commands."""
    pass


@config_cmd.command("auto-discovery")
@click.argument("enabled", type=click.Choice(["enable", "disable", "true", "false"]))
async def config_auto_discovery(enabled: str):
    """Enable or disable client auto-discovery."""
    config_manager = ConfigManager()
    
    enable = enabled in ["enable", "true"]
    await config_manager.set_auto_discovery(enable)
    
    status = "enabled" if enable else "disabled"
    click.echo(f"Auto-discovery {status}")


@config_cmd.command("registry-url")
@click.argument("url", required=False)
async def config_registry_url(url: Optional[str]):
    """Get or set the registry URL."""
    config_manager = ConfigManager()
    
    if url:
        await config_manager.set_registry_url(url)
        click.echo(f"Registry URL set to: {url}")
    else:
        config_data = await config_manager.get_config()
        current_url = config_data.registry_url or "Built-in registry"
        click.echo(f"Current registry URL: {current_url}")


@click.group()
def registry_cmd():
    """Registry management commands."""
    pass


@registry_cmd.command("list")
async def registry_list():
    """List all servers in the registry."""
    from mcpmanager.core.registry import MCPRegistry
    
    registry = MCPRegistry()
    await registry.initialize()
    
    servers = await registry.list_servers()
    
    if not servers:
        click.echo("No servers found in registry")
        return
    
    click.echo(f"{'Name':<20} {'Description':<50} {'Tags':<30}")
    click.echo("-" * 100)
    
    for server in servers:
        description = (server.description or "")[:47] + "..." if server.description and len(server.description) > 50 else server.description or ""
        tags = ", ".join(server.tags[:3]) + ("..." if len(server.tags) > 3 else "")
        click.echo(f"{server.name:<20} {description:<50} {tags:<30}")


@registry_cmd.command("info")
@click.argument("server_name")
async def registry_info(server_name: str):
    """Get detailed information about a server."""
    from mcpmanager.core.registry import MCPRegistry
    
    registry = MCPRegistry()
    await registry.initialize()
    
    try:
        info = await registry.get_server_info(server_name)
        
        click.echo(f"Server: {info['name']}")
        click.echo(f"Description: {info['description'] or 'N/A'}")
        click.echo(f"Image: {info['image']}")
        click.echo(f"Version: {info['version'] or 'N/A'}")
        click.echo(f"Transport: {info['transport']}")
        if info['port']:
            click.echo(f"Port: {info['port']}")
        if info['tags']:
            click.echo(f"Tags: {', '.join(info['tags'])}")
        if info['command']:
            click.echo(f"Command: {' '.join(info['command'])}")
        if info['secrets_required']:
            click.echo(f"Required secrets: {', '.join(info['secrets_required'])}")
    
    except Exception as e:
        click.echo(f"Error getting server info: {e}", err=True)
        sys.exit(1)


@click.group()
def secret_cmd():
    """Secrets management commands."""
    pass


@secret_cmd.command("set")
@click.argument("name")
@click.option("--value", prompt=True, hide_input=True, help="Secret value")
async def secret_set(name: str, value: str):
    """Set a secret."""
    from mcpmanager.secrets.manager import SecretsManager
    
    config_manager = ConfigManager()
    secrets_manager = SecretsManager(config_manager)
    await secrets_manager.initialize()
    
    await secrets_manager.set_secret(name, value)
    click.echo(f"Secret '{name}' set successfully")


@secret_cmd.command("get")
@click.argument("name")
async def secret_get(name: str):
    """Get a secret value."""
    from mcpmanager.secrets.manager import SecretsManager
    
    config_manager = ConfigManager()
    secrets_manager = SecretsManager(config_manager)
    await secrets_manager.initialize()
    
    try:
        value = await secrets_manager.get_secret(name)
        click.echo(f"Secret '{name}': {value}")
    except Exception as e:
        click.echo(f"Error getting secret: {e}", err=True)
        sys.exit(1)


@secret_cmd.command("list")
async def secret_list():
    """List all secrets."""
    from mcpmanager.secrets.manager import SecretsManager
    
    config_manager = ConfigManager()
    secrets_manager = SecretsManager(config_manager)
    await secrets_manager.initialize()
    
    secrets = await secrets_manager.list_secrets()
    
    if not secrets:
        click.echo("No secrets found")
        return
    
    click.echo("Available secrets:")
    for secret_name in secrets:
        click.echo(f"  {secret_name}")


@click.group()
def discovery_cmd():
    """Client discovery and configuration commands."""
    pass


@discovery_cmd.command("scan")
async def discovery_scan():
    """Scan for installed MCP clients."""
    discovery = MCPDiscovery()
    clients = await discovery.discover_clients()
    
    if not clients:
        click.echo("No MCP clients found")
        return
    
    click.echo(f"{'Client':<15} {'Installed':<10} {'Config Path':<50}")
    click.echo("-" * 75)
    
    for client in clients:
        status = "Yes" if client.installed else "No"
        config_path = client.config_path or "N/A"
        click.echo(f"{client.client_type.value:<15} {status:<10} {config_path:<50}")


@discovery_cmd.command("scan-servers")
async def discovery_scan_servers():
    """Scan for MCP servers in the environment."""
    discovery = MCPDiscovery()
    servers = await discovery.scan_for_mcp_servers()
    
    if not servers:
        click.echo("No MCP servers found in environment")
        return
    
    click.echo("Discovered MCP servers:")
    for location, server_list in servers.items():
        click.echo(f"\n{location}:")
        for server in server_list:
            click.echo(f"  {server}")


@click.group()
def inspector_cmd():
    """Inspector and debugging commands."""
    pass


@inspector_cmd.command("debug")
@click.argument("server_name")
@click.option("--export", "-e", type=click.Path(), help="Export debug report to file")
async def inspector_debug(ctx: click.Context, server_name: str, export: Optional[str]):
    """Get debug information for a server."""
    manager = await get_manager(ctx)
    
    try:
        if export:
            # Export full debug report
            report_path = await manager.inspector.export_debug_report(server_name, export)
            click.echo(f"Debug report exported to: {report_path}")
        else:
            # Show debug info
            debug_info = await manager.inspector.get_server_debug_info(server_name)
            
            click.echo(f"Debug Information for {server_name}")
            click.echo("=" * 50)
            click.echo(f"Container ID: {debug_info.container_id}")
            click.echo(f"Status: {debug_info.status}")
            click.echo(f"Image: {debug_info.image}")
            click.echo(f"Created: {debug_info.created_at}")
            click.echo(f"Started: {debug_info.started_at or 'N/A'}")
            click.echo(f"Restart Count: {debug_info.restart_count}")
            
            if debug_info.ports:
                click.echo(f"Ports: {', '.join(str(p['container_port']) for p in debug_info.ports)}")
            
            if debug_info.exit_code is not None:
                click.echo(f"Exit Code: {debug_info.exit_code}")
    
    except Exception as e:
        click.echo(f"Error getting debug info: {e}", err=True)
        sys.exit(1)


@inspector_cmd.command("metrics")
@click.argument("server_name")
@click.option("--history", "-h", is_flag=True, help="Show metrics history")
@click.option("--duration", "-d", default=60, help="Duration in minutes for history")
async def inspector_metrics(ctx: click.Context, server_name: str, history: bool, duration: int):
    """Get performance metrics for a server."""
    manager = await get_manager(ctx)
    
    try:
        if history:
            # Show metrics history
            metrics_history = await manager.inspector.get_metrics_history(server_name, duration)
            
            if not metrics_history:
                click.echo(f"No metrics history found for {server_name}")
                return
            
            click.echo(f"Metrics History for {server_name} (last {duration} minutes)")
            click.echo("=" * 60)
            click.echo(f"{'Time':<20} {'CPU %':<8} {'Memory MB':<12} {'Memory %':<10}")
            click.echo("-" * 60)
            
            for metric in metrics_history[-20:]:  # Show last 20 entries
                time_str = metric.timestamp.strftime("%H:%M:%S")
                click.echo(f"{time_str:<20} {metric.cpu_percent:<8.1f} {metric.memory_usage_mb:<12.1f} {metric.memory_percent:<10.1f}")
        else:
            # Show current metrics
            metrics = await manager.inspector.collect_metrics(server_name)
            
            click.echo(f"Current Metrics for {server_name}")
            click.echo("=" * 40)
            click.echo(f"CPU Usage: {metrics.cpu_percent:.1f}%")
            click.echo(f"Memory Usage: {metrics.memory_usage_mb:.1f} MB ({metrics.memory_percent:.1f}%)")
            click.echo(f"Network I/O: {metrics.network_io_read_mb:.1f} MB read, {metrics.network_io_write_mb:.1f} MB write")
            click.echo(f"Disk I/O: {metrics.disk_io_read_mb:.1f} MB read, {metrics.disk_io_write_mb:.1f} MB write")
            click.echo(f"Uptime: {metrics.uptime_seconds:.1f} seconds")
    
    except Exception as e:
        click.echo(f"Error getting metrics: {e}", err=True)
        sys.exit(1)


@inspector_cmd.command("analyze")
@click.argument("server_name")
async def inspector_analyze(ctx: click.Context, server_name: str):
    """Analyze server performance and provide insights."""
    manager = await get_manager(ctx)
    
    try:
        analysis = await manager.inspector.analyze_performance(server_name)
        
        click.echo(f"Performance Analysis for {server_name}")
        click.echo("=" * 50)
        
        if analysis["status"] == "no_data":
            click.echo(analysis["message"])
            return
        
        # Show averages
        averages = analysis["averages"]
        click.echo(f"Average CPU: {averages['cpu_percent']}%")
        click.echo(f"Average Memory: {averages['memory_usage_mb']} MB ({averages['memory_percent']}%)")
        click.echo(f"Metrics analyzed: {analysis['metrics_count']} data points")
        
        # Show anomalies
        anomalies = analysis["anomalies"]
        if anomalies:
            click.echo("\nAnomalies detected:")
            for anomaly in anomalies:
                severity = anomaly["severity"].upper()
                click.echo(f"  [{severity}] {anomaly['message']}")
        else:
            click.echo("\nNo anomalies detected")
        
        # Show recommendations
        recommendations = analysis["recommendations"]
        if recommendations:
            click.echo("\nRecommendations:")
            for rec in recommendations:
                click.echo(f"  • {rec}")
    
    except Exception as e:
        click.echo(f"Error analyzing performance: {e}", err=True)
        sys.exit(1)


@inspector_cmd.command("trace")
@click.argument("server_name")
@click.option("--duration", "-d", default=60, help="Duration in seconds to trace")
async def inspector_trace(ctx: click.Context, server_name: str, duration: int):
    """Trace MCP communication for debugging."""
    manager = await get_manager(ctx)
    
    try:
        click.echo(f"Tracing MCP communication for {server_name} ({duration} seconds)...")
        trace_data = await manager.inspector.trace_mcp_communication(server_name, duration)
        
        if not trace_data:
            click.echo("No MCP communication detected")
            return
        
        click.echo(f"\nMCP Communication Trace ({len(trace_data)} entries)")
        click.echo("=" * 60)
        
        for entry in trace_data:
            timestamp = entry["timestamp"]
            content = entry["content"]
            click.echo(f"[{timestamp}] {content}")
    
    except Exception as e:
        click.echo(f"Error tracing communication: {e}", err=True)
        sys.exit(1)


@inspector_cmd.command("session")
@click.argument("server_name")
async def inspector_session(ctx: click.Context, server_name: str):
    """Start an interactive debugging session."""
    manager = await get_manager(ctx)
    
    try:
        session = DebugSession(manager.inspector, server_name)
        
        click.echo(f"Starting debug session for {server_name}")
        click.echo("Available commands: status, metrics, logs, trace, analyze, restart, quit")
        click.echo("Type 'help' for more information or 'quit' to exit")
        
        while True:
            try:
                command = click.prompt("\ndebug> ", type=str).strip()
                
                if command in ["quit", "exit", "q"]:
                    break
                elif command == "help":
                    click.echo("Available commands:")
                    click.echo("  status   - Show server status")
                    click.echo("  metrics  - Show current metrics")
                    click.echo("  logs     - Show recent logs")
                    click.echo("  trace    - Trace MCP communication")
                    click.echo("  analyze  - Analyze performance")
                    click.echo("  restart  - Restart the server")
                    click.echo("  quit     - Exit debug session")
                    continue
                
                # Execute command
                if command == "logs":
                    result = await session.execute_command("logs", tail=20)
                elif command == "trace":
                    result = await session.execute_command("trace", duration=10)
                else:
                    result = await session.execute_command(command)
                
                # Display result
                if "error" in result:
                    click.echo(f"Error: {result['error']}")
                else:
                    command_result = result.get("result", {})
                    if command == "status":
                        info = command_result
                        click.echo(f"Status: {info.get('status', 'unknown')}")
                        click.echo(f"Container: {info.get('container_id', 'unknown')}")
                    elif command == "metrics":
                        metrics = command_result
                        click.echo(f"CPU: {metrics.get('cpu_percent', 0):.1f}%")
                        click.echo(f"Memory: {metrics.get('memory_usage_mb', 0):.1f} MB")
                    elif command == "logs":
                        logs = command_result.get("logs", [])
                        for log_line in logs[-10:]:  # Show last 10 lines
                            if log_line.strip():
                                click.echo(log_line)
                    elif command == "analyze":
                        analysis = command_result
                        if analysis.get("anomalies"):
                            click.echo("Anomalies:")
                            for anomaly in analysis["anomalies"]:
                                click.echo(f"  {anomaly['message']}")
                        else:
                            click.echo("No anomalies detected")
                    elif command == "restart":
                        if command_result.get("status") == "success":
                            click.echo("Server restarted successfully")
                        else:
                            click.echo(f"Restart failed: {command_result.get('error')}")
                    else:
                        click.echo(json.dumps(command_result, indent=2, default=str))
            
            except KeyboardInterrupt:
                click.echo("\nUse 'quit' to exit")
            except Exception as e:
                click.echo(f"Error: {e}")
        
        # Show session summary
        summary = session.get_session_summary()
        click.echo(f"\nSession completed. Executed {summary['commands_executed']} commands.")
    
    except Exception as e:
        click.echo(f"Error starting debug session: {e}", err=True)
        sys.exit(1)


@click.group()
def runtime_cmd():
    """Runtime management commands."""
    pass


@runtime_cmd.command("list")
async def runtime_list(ctx: click.Context):
    """List available container runtimes."""
    manager = await get_manager(ctx)
    
    try:
        available_runtimes = manager.runtime_manager.get_available_runtimes()
        active_runtime = manager.runtime_manager.get_active_runtime()
        
        if not available_runtimes:
            click.echo("No container runtimes available")
            return
        
        click.echo(f"{'Runtime':<12} {'Status':<8} {'Active':<6}")
        click.echo("-" * 26)
        
        for runtime_type in available_runtimes:
            status = "Available"
            active = "Yes" if active_runtime.runtime_type == runtime_type else "No"
            click.echo(f"{runtime_type.value:<12} {status:<8} {active:<6}")
    
    except Exception as e:
        click.echo(f"Error listing runtimes: {e}", err=True)
        sys.exit(1)


@runtime_cmd.command("info")
@click.argument("runtime_type", required=False)
async def runtime_info(ctx: click.Context, runtime_type: Optional[str]):
    """Get runtime information."""
    manager = await get_manager(ctx)
    
    try:
        if runtime_type:
            try:
                rt = RuntimeType(runtime_type)
                info = await manager.runtime_manager.get_runtime_info(rt)
                
                click.echo(f"Runtime: {info.name}")
                click.echo(f"Type: {info.type.value}")
                click.echo(f"Version: {info.version}")
                click.echo(f"Available: {info.available}")
                click.echo(f"Status: {info.status}")
                click.echo(f"Capabilities: {', '.join(info.capabilities)}")
                
                if info.config:
                    click.echo("\nConfiguration:")
                    for key, value in info.config.items():
                        click.echo(f"  {key}: {value}")
                        
            except ValueError:
                click.echo(f"Invalid runtime type: {runtime_type}")
                click.echo("Valid types: docker, podman, kubernetes")
                sys.exit(1)
        else:
            # Show info for all runtimes
            info_list = await manager.runtime_manager.get_runtime_info()
            
            for info in info_list:
                click.echo(f"\n{info.name} ({info.type.value})")
                click.echo(f"  Version: {info.version}")
                click.echo(f"  Available: {info.available}")
                click.echo(f"  Status: {info.status}")
                click.echo(f"  Capabilities: {len(info.capabilities)} features")
    
    except Exception as e:
        click.echo(f"Error getting runtime info: {e}", err=True)
        sys.exit(1)


@runtime_cmd.command("switch")
@click.argument("runtime_type")
async def runtime_switch(ctx: click.Context, runtime_type: str):
    """Switch to a different runtime."""
    manager = await get_manager(ctx)
    
    try:
        rt = RuntimeType(runtime_type)
        await manager.runtime_manager.switch_runtime(rt)
        click.echo(f"Switched to {runtime_type} runtime")
    
    except ValueError:
        click.echo(f"Invalid runtime type: {runtime_type}")
        click.echo("Valid types: docker, podman, kubernetes")
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error switching runtime: {e}", err=True)
        sys.exit(1)


@runtime_cmd.command("health")
async def runtime_health(ctx: click.Context):
    """Check runtime health status."""
    manager = await get_manager(ctx)
    
    try:
        health = await manager.runtime_manager.health_check()
        
        click.echo(f"Overall Status: {health['overall']}")
        click.echo(f"Active Runtime: {health['active_runtime']}")
        click.echo("\nRuntime Status:")
        
        for runtime_name, status in health['runtimes'].items():
            available = "✓" if status['available'] else "✗"
            click.echo(f"  {runtime_name}: {available} {status['status']}")
            if 'version' in status:
                click.echo(f"    Version: {status['version']}")
            if 'error' in status:
                click.echo(f"    Error: {status['error']}")
    
    except Exception as e:
        click.echo(f"Error checking runtime health: {e}", err=True)
        sys.exit(1)


@runtime_cmd.command("capabilities")
@click.argument("runtime_type", required=False)
async def runtime_capabilities(ctx: click.Context, runtime_type: Optional[str]):
    """Show runtime capabilities."""
    manager = await get_manager(ctx)
    
    try:
        if runtime_type:
            try:
                rt = RuntimeType(runtime_type)
                capabilities = manager.runtime_manager.get_runtime_capabilities(rt)
                runtime_caps = capabilities.get(runtime_type, [])
                
                click.echo(f"{runtime_type} capabilities:")
                for cap in runtime_caps:
                    click.echo(f"  • {cap}")
                    
            except ValueError:
                click.echo(f"Invalid runtime type: {runtime_type}")
                sys.exit(1)
        else:
            # Show capabilities for all runtimes
            all_capabilities = manager.runtime_manager.get_runtime_capabilities()
            
            for runtime_name, capabilities in all_capabilities.items():
                click.echo(f"\n{runtime_name}:")
                for cap in capabilities:
                    click.echo(f"  • {cap}")
    
    except Exception as e:
        click.echo(f"Error getting capabilities: {e}", err=True)
        sys.exit(1)


@click.group()
def operator_cmd():
    """Kubernetes operator commands."""
    pass


@operator_cmd.command("install")
@click.option("--namespace", default="mcpmanager-system", help="Operator namespace")
@click.option("--image", default="mcpmanager/operator:latest", help="Operator image")
async def operator_install(namespace: str, image: str):
    """Install the MCPManager Kubernetes operator."""
    from mcpmanager.operator import MCPOperator
    
    try:
        operator = MCPOperator()
        
        # Validate environment
        if not await operator.validate_environment():
            click.echo("Environment validation failed", err=True)
            sys.exit(1)
        
        click.echo("Installing MCPManager operator...")
        
        # Install CRDs
        click.echo("Installing Custom Resource Definitions...")
        await operator.install_crds()
        
        # Install RBAC
        click.echo("Installing RBAC resources...")
        await operator.install_rbac(namespace)
        
        # Install operator
        click.echo("Installing operator deployment...")
        await operator.install_operator(namespace, image)
        
        click.echo(f"✓ MCPManager operator installed successfully in namespace: {namespace}")
        click.echo("You can now create MCPServer resources!")
    
    except Exception as e:
        click.echo(f"Error installing operator: {e}", err=True)
        sys.exit(1)


@operator_cmd.command("uninstall")
async def operator_uninstall():
    """Uninstall the MCPManager Kubernetes operator."""
    from mcpmanager.operator import MCPOperator
    
    try:
        operator = MCPOperator()
        
        click.echo("⚠️  This will delete ALL MCPServer resources!")
        if not click.confirm("Are you sure you want to uninstall the operator?"):
            click.echo("Aborted")
            return
        
        click.echo("Uninstalling MCPManager operator...")
        await operator.uninstall()
        
        click.echo("✓ MCPManager operator uninstalled successfully")
    
    except Exception as e:
        click.echo(f"Error uninstalling operator: {e}", err=True)
        sys.exit(1)


@operator_cmd.command("status")
async def operator_status():
    """Show operator status."""
    from mcpmanager.operator import MCPOperator
    
    try:
        operator = MCPOperator()
        status = await operator.status()
        
        click.echo("MCPManager Operator Status")
        click.echo("=" * 30)
        click.echo(f"CRD: {status['crd']}")
        click.echo(f"RBAC: {status['rbac']}")
        click.echo(f"Operator: {status['operator']}")
        
        mcpservers = status.get("mcpservers", [])
        if mcpservers:
            click.echo(f"\nMCPServers ({len(mcpservers)}):")
            click.echo(f"{'Name':<20} {'Namespace':<15} {'Phase':<10} {'Ready':<5} {'Image':<30}")
            click.echo("-" * 80)
            
            for server in mcpservers:
                ready_str = f"{server['ready_replicas']}/{server['replicas']}"
                image_short = server['image'][:27] + "..." if len(server['image']) > 30 else server['image']
                click.echo(f"{server['name']:<20} {server['namespace']:<15} {server['phase']:<10} {ready_str:<5} {image_short:<30}")
        else:
            click.echo("\nNo MCPServers found")
    
    except Exception as e:
        click.echo(f"Error getting operator status: {e}", err=True)
        sys.exit(1)


@operator_cmd.command("run")
@click.option("--namespace", help="Namespace to watch (default: all)")
async def operator_run(namespace: Optional[str]):
    """Run the operator (used inside Kubernetes)."""
    from mcpmanager.operator import MCPOperator
    
    try:
        operator = MCPOperator(namespace)
        await operator.start()
    
    except KeyboardInterrupt:
        click.echo("Operator stopped")
    except Exception as e:
        click.echo(f"Operator failed: {e}", err=True)
        sys.exit(1)


@operator_cmd.command("validate")
async def operator_validate():
    """Validate environment for operator installation."""
    from mcpmanager.operator import MCPOperator
    
    try:
        operator = MCPOperator()
        
        click.echo("Validating environment...")
        if await operator.validate_environment():
            click.echo("✓ Environment is ready for operator installation")
        else:
            click.echo("✗ Environment validation failed", err=True)
            sys.exit(1)
    
    except Exception as e:
        click.echo(f"Error validating environment: {e}", err=True)
        sys.exit(1)


@operator_cmd.command("create-mcpserver")
@click.argument("name")
@click.argument("image")
@click.option("--namespace", default="default", help="Namespace for MCPServer")
@click.option("--transport", type=click.Choice(["stdio", "sse", "proxy", "transparent"]), default="stdio", help="Transport protocol")
@click.option("--port", type=int, help="Port for network transports")
@click.option("--replicas", default=1, help="Number of replicas")
@click.option("--env", "-e", multiple=True, help="Environment variables (KEY=VALUE)")
async def operator_create_mcpserver(name: str, image: str, namespace: str, transport: str, port: Optional[int], replicas: int, env: tuple):
    """Create an MCPServer resource."""
    try:
        # Parse environment variables
        environment = {}
        for env_var in env:
            if "=" not in env_var:
                raise click.BadParameter(f"Invalid environment variable format: {env_var}")
            key, value = env_var.split("=", 1)
            environment[key] = value
        
        # Create MCPServer manifest
        mcpserver = {
            "apiVersion": "mcpmanager.io/v1alpha1",
            "kind": "MCPServer",
            "metadata": {
                "name": name,
                "namespace": namespace
            },
            "spec": {
                "image": image,
                "transport": transport,
                "replicas": replicas
            }
        }
        
        if port:
            mcpserver["spec"]["port"] = port
        
        if environment:
            mcpserver["spec"]["environment"] = environment
        
        # Apply the resource
        import json
        import asyncio
        
        manifest_yaml = json.dumps(mcpserver)
        process = await asyncio.create_subprocess_exec(
            "kubectl", "apply", "-f", "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate(input=manifest_yaml.encode())
        
        if process.returncode != 0:
            raise Exception(f"Failed to create MCPServer: {stderr.decode()}")
        
        click.echo(f"✓ MCPServer '{name}' created in namespace '{namespace}'")
        click.echo("Use 'mcpm operator status' to check the status")
    
    except Exception as e:
        click.echo(f"Error creating MCPServer: {e}", err=True)
        sys.exit(1)


# Verification commands
@click.group()
def verify_cmd():
    """Image verification commands."""
    pass


@verify_cmd.command("image")
@click.argument("image")
@click.option("--config", help="Verification configuration file")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
async def verify_image_cmd(ctx: click.Context, image: str, config: Optional[str], format: str) -> None:
    """Verify an image."""
    manager = await get_manager(ctx)
    
    try:
        verification_config = None
        if config:
            config_path = Path(config)
            if not config_path.exists():
                raise click.BadParameter(f"Configuration file not found: {config}")
            
            with open(config_path, 'r') as f:
                if config_path.suffix.lower() in ['.yaml', '.yml']:
                    import yaml
                    verification_config = yaml.safe_load(f)
                else:
                    verification_config = json.load(f)
        
        result = await manager.verify_image(image, verification_config)
        
        if format == "json":
            click.echo(json.dumps(result, indent=2))
        else:
            # Table format
            status = "✓ VERIFIED" if result["verified"] else "✗ FAILED"
            click.echo(f"Image: {image}")
            click.echo(f"Status: {status}")
            click.echo(f"Digest: {result['digest']}")
            click.echo(f"Signatures: {len(result['signatures'])}")
            click.echo(f"Attestations: {len(result['attestations'])}")
            
            if result["policy_violations"]:
                click.echo("\nPolicy Violations:")
                for violation in result["policy_violations"]:
                    click.echo(f"  - {violation}")
    
    except Exception as e:
        click.echo(f"Error verifying image: {e}", err=True)
        sys.exit(1)


@verify_cmd.command("vulnerabilities")
@click.argument("image")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
async def verify_vulnerabilities_cmd(ctx: click.Context, image: str, format: str) -> None:
    """Get vulnerability information for an image."""
    manager = await get_manager(ctx)
    
    try:
        result = await manager.get_image_vulnerabilities(image)
        
        if format == "json":
            click.echo(json.dumps(result, indent=2))
        else:
            # Table format
            summary = result.get("summary", {})
            click.echo(f"Image: {image}")
            click.echo(f"Scanner: {result.get('scanner', 'unknown')}")
            click.echo(f"Total vulnerabilities: {summary.get('total', 0)}")
            click.echo(f"Critical: {summary.get('critical', 0)}")
            click.echo(f"High: {summary.get('high', 0)}")
            click.echo(f"Medium: {summary.get('medium', 0)}")
            click.echo(f"Low: {summary.get('low', 0)}")
    
    except Exception as e:
        click.echo(f"Error getting vulnerabilities: {e}", err=True)
        sys.exit(1)


@verify_cmd.command("config")
@click.option("--enable/--disable", default=None, help="Enable or disable verification")
@click.option("--set", "set_values", multiple=True, help="Set configuration values (key=value)")
@click.option("--show", is_flag=True, help="Show current configuration")
@click.option("--preset", type=click.Choice(["default", "strict"]), help="Apply preset configuration")
@click.pass_context
async def verify_config_cmd(
    ctx: click.Context, 
    enable: Optional[bool], 
    set_values: tuple, 
    show: bool,
    preset: Optional[str]
) -> None:
    """Manage verification configuration."""
    manager = await get_manager(ctx)
    config_manager = manager.config_manager
    
    try:
        if show:
            verification_config = config_manager.get_verification_config()
            if verification_config:
                click.echo(json.dumps(verification_config, indent=2))
            else:
                click.echo("No verification configuration found")
            return
        
        if preset:
            from mcpmanager.verification.policy import create_default_policy, create_strict_policy
            from mcpmanager.core.models import VerificationConfig
            
            if preset == "default":
                policy = create_default_policy()
                config = VerificationConfig(
                    enabled=True,
                    methods=[{
                        "type": "sigstore",
                        "verify_signatures": True,
                        "verify_attestations": False,
                        "allow_unsigned": True
                    }],
                    policy=policy
                )
            else:  # strict
                policy = create_strict_policy()
                config = VerificationConfig(
                    enabled=True,
                    methods=[{
                        "type": "sigstore",
                        "verify_signatures": True,
                        "verify_attestations": True,
                        "allow_unsigned": False,
                        "attestation_types": ["slsa-provenance"]
                    }],
                    policy=policy
                )
            
            await config_manager.set_verification_config(config)
            click.echo(f"Applied {preset} verification configuration")
            return
        
        # Get current config
        current_config = config_manager.get_verification_config()
        if not current_config:
            from mcpmanager.core.models import VerificationConfig
            current_config = VerificationConfig().model_dump()
        
        # Apply enable/disable
        if enable is not None:
            current_config["enabled"] = enable
        
        # Apply set values
        for set_value in set_values:
            if "=" not in set_value:
                raise click.BadParameter(f"Invalid set format: {set_value}")
            key, value = set_value.split("=", 1)
            
            # Parse value
            if value.lower() in ["true", "false"]:
                value = value.lower() == "true"
            elif value.isdigit():
                value = int(value)
            
            # Set nested value
            keys = key.split(".")
            config_part = current_config
            for k in keys[:-1]:
                if k not in config_part:
                    config_part[k] = {}
                config_part = config_part[k]
            config_part[keys[-1]] = value
        
        # Save configuration
        from mcpmanager.core.models import VerificationConfig
        config = VerificationConfig(**current_config)
        await config_manager.set_verification_config(config)
        
        click.echo("Verification configuration updated")
    
    except Exception as e:
        click.echo(f"Error managing verification config: {e}", err=True)
        sys.exit(1)


# Permission commands
@click.group()
def permissions_cmd():
    """Advanced permission management commands."""
    pass


@permissions_cmd.command("list")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
async def permissions_list_cmd(ctx: click.Context, format: str) -> None:
    """List all permission profiles."""
    manager = await get_manager(ctx)
    
    try:
        profiles = await manager.list_permission_profiles()
        
        if format == "json":
            click.echo(json.dumps(profiles, indent=2))
        else:
            if profiles:
                click.echo("Available permission profiles:")
                for profile in profiles:
                    click.echo(f"  - {profile}")
            else:
                click.echo("No permission profiles found")
    
    except Exception as e:
        click.echo(f"Error listing permission profiles: {e}", err=True)
        sys.exit(1)


@permissions_cmd.command("show")
@click.argument("name")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
async def permissions_show_cmd(ctx: click.Context, name: str, format: str) -> None:
    """Show details of a permission profile."""
    manager = await get_manager(ctx)
    
    try:
        profile = await manager.get_permission_profile(name)
        
        if not profile:
            click.echo(f"Permission profile not found: {name}", err=True)
            sys.exit(1)
        
        if format == "json":
            click.echo(json.dumps(profile, indent=2, default=str))
        else:
            # Table format
            click.echo(f"Permission Profile: {profile['name']}")
            click.echo(f"Description: {profile.get('description', 'N/A')}")
            click.echo(f"Security Level: {profile['security_level']}")
            click.echo(f"Created: {profile['created_at']}")
            
            if profile['read_paths']:
                click.echo(f"\nRead Paths:")
                for path in profile['read_paths']:
                    click.echo(f"  - {path}")
            
            if profile['write_paths']:
                click.echo(f"\nWrite Paths:")
                for path in profile['write_paths']:
                    click.echo(f"  - {path}")
            
            if profile.get('resource_limits'):
                limits = profile['resource_limits']
                click.echo(f"\nResource Limits:")
                if limits.get('memory'):
                    click.echo(f"  Memory: {limits['memory']}")
                if limits.get('cpu_limit'):
                    click.echo(f"  CPU: {limits['cpu_limit']}")
            
            if profile.get('network_policy'):
                network = profile['network_policy']
                click.echo(f"\nNetwork Policy:")
                click.echo(f"  Internet Access: {network.get('allow_internet', False)}")
                click.echo(f"  Localhost Access: {network.get('allow_localhost', True)}")
    
    except Exception as e:
        click.echo(f"Error showing permission profile: {e}", err=True)
        sys.exit(1)


@permissions_cmd.command("create")
@click.argument("name")
@click.option("--template", help="Template to use as base")
@click.option("--description", help="Profile description")
@click.option("--security-level", type=click.Choice(["minimal", "restricted", "standard", "privileged"]), help="Security level")
@click.option("--read-path", "read_paths", multiple=True, help="Allowed read paths")
@click.option("--write-path", "write_paths", multiple=True, help="Allowed write paths")
@click.option("--memory-limit", help="Memory limit (e.g., 512m, 1g)")
@click.option("--cpu-limit", help="CPU limit (e.g., 0.5, 1.0)")
@click.option("--allow-internet/--no-internet", default=None, help="Allow internet access")
@click.option("--shell-access/--no-shell", default=None, help="Allow shell access")
@click.pass_context
async def permissions_create_cmd(
    ctx: click.Context,
    name: str,
    template: Optional[str],
    description: Optional[str],
    security_level: Optional[str],
    read_paths: tuple,
    write_paths: tuple,
    memory_limit: Optional[str],
    cpu_limit: Optional[str],
    allow_internet: Optional[bool],
    shell_access: Optional[bool]
) -> None:
    """Create a new permission profile."""
    manager = await get_manager(ctx)
    
    try:
        overrides = {}
        
        if description:
            overrides["description"] = description
        if security_level:
            overrides["security_level"] = security_level
        if read_paths:
            overrides["read_paths"] = list(read_paths)
        if write_paths:
            overrides["write_paths"] = list(write_paths)
        if memory_limit or cpu_limit:
            resource_limits = {}
            if memory_limit:
                resource_limits["memory"] = memory_limit
            if cpu_limit:
                resource_limits["cpu_limit"] = cpu_limit
            overrides["resource_limits"] = resource_limits
        if allow_internet is not None:
            overrides["network_policy"] = {"allow_internet": allow_internet}
        if shell_access is not None:
            overrides["shell_access"] = shell_access
        
        profile = await manager.create_permission_profile(name, template, overrides)
        
        click.echo(f"✓ Permission profile '{name}' created successfully")
        
        # Validate the profile
        warnings = await manager.validate_permission_profile(name)
        if warnings:
            click.echo("\nWarnings:")
            for warning in warnings:
                click.echo(f"  ⚠ {warning}")
    
    except Exception as e:
        click.echo(f"Error creating permission profile: {e}", err=True)
        sys.exit(1)


@permissions_cmd.command("delete")
@click.argument("name")
@click.option("--force", "-f", is_flag=True, help="Force deletion without confirmation")
@click.pass_context
async def permissions_delete_cmd(ctx: click.Context, name: str, force: bool) -> None:
    """Delete a permission profile."""
    manager = await get_manager(ctx)
    
    try:
        if not force:
            if not click.confirm(f"Delete permission profile '{name}'?"):
                click.echo("Cancelled")
                return
        
        success = await manager.delete_permission_profile(name)
        
        if success:
            click.echo(f"✓ Permission profile '{name}' deleted successfully")
        else:
            click.echo(f"Permission profile '{name}' not found", err=True)
            sys.exit(1)
    
    except Exception as e:
        click.echo(f"Error deleting permission profile: {e}", err=True)
        sys.exit(1)


@permissions_cmd.command("validate")
@click.argument("name")
@click.pass_context
async def permissions_validate_cmd(ctx: click.Context, name: str) -> None:
    """Validate a permission profile."""
    manager = await get_manager(ctx)
    
    try:
        warnings = await manager.validate_permission_profile(name)
        
        if not warnings:
            click.echo(f"✓ Permission profile '{name}' is valid")
        else:
            click.echo(f"Permission profile '{name}' has warnings:")
            for warning in warnings:
                click.echo(f"  ⚠ {warning}")
    
    except Exception as e:
        click.echo(f"Error validating permission profile: {e}", err=True)
        sys.exit(1)


@permissions_cmd.command("recommend")
@click.argument("use_case")
@click.pass_context
async def permissions_recommend_cmd(ctx: click.Context, use_case: str) -> None:
    """Get permission profile recommendations for a use case."""
    manager = await get_manager(ctx)
    
    try:
        recommendations = await manager.get_permission_recommendations(use_case)
        
        if recommendations:
            click.echo(f"Recommended permission profiles for '{use_case}':")
            for rec in recommendations:
                click.echo(f"  - {rec}")
        else:
            click.echo(f"No specific recommendations for '{use_case}'. Consider using 'standard' profile.")
    
    except Exception as e:
        click.echo(f"Error getting recommendations: {e}", err=True)
        sys.exit(1)


@permissions_cmd.command("templates")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
async def permissions_templates_cmd(ctx: click.Context, format: str) -> None:
    """List available permission templates."""
    try:
        from mcpmanager.permissions.profiles import PERMISSION_TEMPLATES
        
        if format == "json":
            templates_data = {}
            for name, template in PERMISSION_TEMPLATES.items():
                templates_data[name] = template.model_dump()
            click.echo(json.dumps(templates_data, indent=2, default=str))
        else:
            click.echo("Available permission templates:")
            for name, template in PERMISSION_TEMPLATES.items():
                click.echo(f"\n{name}:")
                click.echo(f"  Description: {template.description}")
                click.echo(f"  Base Profile: {template.base_profile}")
                if template.use_cases:
                    click.echo(f"  Use Cases: {', '.join(template.use_cases)}")
                if template.tags:
                    click.echo(f"  Tags: {', '.join(template.tags)}")
    
    except Exception as e:
        click.echo(f"Error listing templates: {e}", err=True)
        sys.exit(1)