"""Main CLI entry point for MCPManager."""

import asyncio
import sys
import logging
from typing import Optional

import click
from mcpmanager.cli.commands import (
    run_cmd,
    list_cmd,
    stop_cmd,
    remove_cmd,
    restart_cmd,
    logs_cmd,
    config_cmd,
    registry_cmd,
    search_cmd,
    secret_cmd,
    serve_cmd,
    discovery_cmd,
    inspector_cmd,
    runtime_cmd,
    operator_cmd,
    verify_cmd,
    permissions_cmd,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Global context for passing manager instance
class CLIContext:
    def __init__(self):
        self.manager = None
        self.debug = False

@click.group()
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.pass_context
def cli(ctx: click.Context, debug: bool) -> None:
    """MCPManager - Secure MCP Server Management with Dynamic Discovery.
    
    MCPManager is a lightweight utility designed to simplify the deployment
    and management of MCP (Model Context Protocol) servers with enhanced
    security and dynamic discovery capabilities.
    """
    if ctx.obj is None:
        ctx.obj = CLIContext()
    
    ctx.obj.debug = debug
    
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("mcpmanager").setLevel(logging.DEBUG)


@cli.command()
@click.argument("server_name")
@click.option("--image", help="Container image to use")
@click.option("--transport", type=click.Choice(["stdio", "sse", "proxy", "transparent"]), default="stdio", help="Transport protocol")
@click.option("--port", type=int, help="Port for SSE transport")
@click.option("--target-port", type=int, help="Target port in container")
@click.option("--env", "-e", multiple=True, help="Environment variables (KEY=VALUE)")
@click.option("--secret", multiple=True, help="Secrets (name,target=ENV_VAR)")
@click.option("--detach", "-d", is_flag=True, help="Run in detached mode")
@click.option("--permission-profile", help="Permission profile file")
@click.option("--runtime", type=click.Choice(["docker", "podman", "kubernetes"]), help="Container runtime to use")
@click.pass_context
def run(
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
    runtime: Optional[str],
) -> None:
    """Run an MCP server."""
    async def _run():
        await run_cmd(
            ctx, server_name, image, transport, port, target_port,
            env, secret, detach, permission_profile, runtime
        )
    
    asyncio.run(_run())


@cli.command()
@click.option("--all", "-a", is_flag=True, help="Show all servers including stopped")
@click.option("--format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def list(ctx: click.Context, all: bool, format: str) -> None:
    """List MCP servers."""
    async def _list():
        await list_cmd(ctx, all, format)
    
    asyncio.run(_list())


@cli.command()
@click.argument("server_name")
@click.pass_context
def stop(ctx: click.Context, server_name: str) -> None:
    """Stop an MCP server."""
    async def _stop():
        await stop_cmd(ctx, server_name)
    
    asyncio.run(_stop())


@cli.command()
@click.argument("server_name")
@click.option("--force", "-f", is_flag=True, help="Force removal of running server")
@click.pass_context
def rm(ctx: click.Context, server_name: str, force: bool) -> None:
    """Remove an MCP server."""
    async def _rm():
        await remove_cmd(ctx, server_name, force)
    
    asyncio.run(_rm())


@cli.command()
@click.argument("server_name")
@click.pass_context
def restart(ctx: click.Context, server_name: str) -> None:
    """Restart an MCP server."""
    async def _restart():
        await restart_cmd(ctx, server_name)
    
    asyncio.run(_restart())


@cli.command()
@click.argument("server_name")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
@click.option("--tail", type=int, default=100, help="Number of lines to show")
@click.pass_context
def logs(ctx: click.Context, server_name: str, follow: bool, tail: int) -> None:
    """Get logs for an MCP server."""
    async def _logs():
        await logs_cmd(ctx, server_name, follow, tail)
    
    asyncio.run(_logs())


@cli.command()
@click.argument("query")
@click.pass_context
def search(ctx: click.Context, query: str) -> None:
    """Search for MCP servers in the registry."""
    async def _search():
        await search_cmd(ctx, query)
    
    asyncio.run(_search())


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int) -> None:
    """Start MCPManager API server."""
    async def _serve():
        await serve_cmd(ctx, host, port)
    
    asyncio.run(_serve())


# Add command groups
cli.add_command(config_cmd, name="config")
cli.add_command(registry_cmd, name="registry")
cli.add_command(secret_cmd, name="secret")
cli.add_command(discovery_cmd, name="discovery")
cli.add_command(inspector_cmd, name="inspector")
cli.add_command(runtime_cmd, name="runtime")
cli.add_command(operator_cmd, name="operator")
cli.add_command(verify_cmd, name="verify")
cli.add_command(permissions_cmd, name="permissions")


def main() -> None:
    """Main entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\nAborted!", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()