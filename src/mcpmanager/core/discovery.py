"""Dynamic MCP server discovery functionality."""

import logging
import os
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Set
import json
import platform

from mcpmanager.core.models import (
    MCPClientType,
    DiscoveredClient,
    ClientConfig,
)

logger = logging.getLogger(__name__)


class MCPDiscovery:
    """Dynamic MCP server discovery and client auto-configuration."""

    def __init__(self):
        """Initialize the discovery service."""
        self.supported_clients = {
            MCPClientType.VSCODE: {
                "name": "VS Code",
                "config_paths": self._get_vscode_config_paths(),
                "config_file": "settings.json",
                "mcp_key": "mcp.servers",
            },
            MCPClientType.CURSOR: {
                "name": "Cursor",
                "config_paths": self._get_cursor_config_paths(),
                "config_file": "settings.json",
                "mcp_key": "mcp.servers",
            },
            MCPClientType.ROO_CODE: {
                "name": "Roo Code",
                "config_paths": self._get_roo_config_paths(),
                "config_file": "settings.json",
                "mcp_key": "mcp.servers",
            },
            MCPClientType.CLAUDE_CODE: {
                "name": "Claude Code",
                "config_paths": self._get_claude_config_paths(),
                "config_file": "settings.json",
                "mcp_key": "mcp.servers",
            },
            MCPClientType.CLINE: {
                "name": "Cline",
                "config_paths": self._get_cline_config_paths(),
                "config_file": "settings.json",
                "mcp_key": "mcp.servers",
            },
        }

    def _get_home_dir(self) -> Path:
        """Get user home directory."""
        return Path.home()

    def _get_vscode_config_paths(self) -> List[Path]:
        """Get VS Code configuration paths."""
        home = self._get_home_dir()
        system = platform.system()
        
        if system == "Windows":
            return [
                home / "AppData" / "Roaming" / "Code" / "User",
                home / "AppData" / "Roaming" / "Code - Insiders" / "User",
            ]
        elif system == "Darwin":  # macOS
            return [
                home / "Library" / "Application Support" / "Code" / "User",
                home / "Library" / "Application Support" / "Code - Insiders" / "User",
            ]
        else:  # Linux
            return [
                home / ".config" / "Code" / "User",
                home / ".config" / "Code - Insiders" / "User",
            ]

    def _get_cursor_config_paths(self) -> List[Path]:
        """Get Cursor configuration paths."""
        home = self._get_home_dir()
        system = platform.system()
        
        if system == "Windows":
            return [home / "AppData" / "Roaming" / "Cursor" / "User"]
        elif system == "Darwin":  # macOS
            return [home / "Library" / "Application Support" / "Cursor" / "User"]
        else:  # Linux
            return [home / ".config" / "Cursor" / "User"]

    def _get_roo_config_paths(self) -> List[Path]:
        """Get Roo Code configuration paths."""
        # Roo Code is a VS Code extension, so it uses VS Code paths
        return self._get_vscode_config_paths()

    def _get_claude_config_paths(self) -> List[Path]:
        """Get Claude Code configuration paths."""
        home = self._get_home_dir()
        system = platform.system()
        
        if system == "Windows":
            return [home / "AppData" / "Roaming" / "ClaudeCode" / "User"]
        elif system == "Darwin":  # macOS
            return [home / "Library" / "Application Support" / "ClaudeCode" / "User"]
        else:  # Linux
            return [home / ".config" / "ClaudeCode" / "User"]

    def _get_cline_config_paths(self) -> List[Path]:
        """Get Cline configuration paths."""
        # Cline is a VS Code extension, so it uses VS Code paths
        return self._get_vscode_config_paths()

    async def discover_clients(self) -> List[DiscoveredClient]:
        """Discover installed MCP clients."""
        discovered = []
        
        for client_type, client_info in self.supported_clients.items():
            config_path = None
            installed = False
            
            # Check if any of the config paths exist
            for path in client_info["config_paths"]:
                config_file_path = path / client_info["config_file"]
                if config_file_path.exists():
                    installed = True
                    config_path = str(config_file_path)
                    break
            
            discovered.append(DiscoveredClient(
                client_type=client_type,
                installed=installed,
                registered=False,  # Will be updated when checking registration
                config_path=config_path,
            ))
        
        return discovered

    async def auto_configure_client(
        self, client_type: MCPClientType, server_name: str, server_url: str
    ) -> bool:
        """Auto-configure a client with MCP server."""
        if client_type not in self.supported_clients:
            logger.warning(f"Unsupported client type: {client_type}")
            return False

        client_info = self.supported_clients[client_type]
        
        # Find the config file
        config_path = None
        for path in client_info["config_paths"]:
            config_file_path = path / client_info["config_file"]
            if config_file_path.exists():
                config_path = config_file_path
                break
        
        if not config_path:
            logger.warning(f"No config file found for {client_info['name']}")
            return False

        try:
            # Read existing config
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config_data = {}

        # Update MCP servers configuration
        mcp_key = client_info["mcp_key"]
        if mcp_key not in config_data:
            config_data[mcp_key] = {}

        config_data[mcp_key][server_name] = {
            "url": server_url,
            "type": "sse" if "sse" in server_url else "stdio",
        }

        # Write updated config
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2)
            
            logger.info(f"Configured {client_info['name']} with MCP server {server_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to update {client_info['name']} config: {e}")
            return False

    async def remove_client_config(
        self, client_type: MCPClientType, server_name: str
    ) -> bool:
        """Remove MCP server configuration from a client."""
        if client_type not in self.supported_clients:
            return False

        client_info = self.supported_clients[client_type]
        
        # Find the config file
        config_path = None
        for path in client_info["config_paths"]:
            config_file_path = path / client_info["config_file"]
            if config_file_path.exists():
                config_path = config_file_path
                break
        
        if not config_path:
            return False

        try:
            # Read existing config
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # Remove MCP server configuration
            mcp_key = client_info["mcp_key"]
            if mcp_key in config_data and server_name in config_data[mcp_key]:
                del config_data[mcp_key][server_name]
                
                # Clean up empty mcp.servers section
                if not config_data[mcp_key]:
                    del config_data[mcp_key]

                # Write updated config
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2)
                
                logger.info(f"Removed {server_name} from {client_info['name']} config")
                return True
        except Exception as e:
            logger.error(f"Failed to remove config from {client_info['name']}: {e}")
            return False

        return False

    async def auto_configure_all_clients(
        self, server_name: str, server_url: str
    ) -> Dict[MCPClientType, bool]:
        """Auto-configure all discovered clients."""
        results = {}
        discovered_clients = await self.discover_clients()
        
        for client in discovered_clients:
            if client.installed:
                success = await self.auto_configure_client(
                    client.client_type, server_name, server_url
                )
                results[client.client_type] = success
        
        return results

    async def scan_for_mcp_servers(self) -> Dict[str, List[str]]:
        """Scan common locations for MCP servers."""
        discovered_servers = {}
        
        # Common package manager locations
        scan_locations = {
            "npm_global": self._get_npm_global_path(),
            "python_site": self._get_python_site_packages(),
            "local_projects": [Path.cwd()],
        }
        
        for location_type, paths in scan_locations.items():
            if not isinstance(paths, list):
                paths = [paths] if paths else []
            
            servers = []
            for path in paths:
                if path and path.exists():
                    servers.extend(await self._scan_directory_for_mcp(path))
            
            if servers:
                discovered_servers[location_type] = servers
        
        return discovered_servers

    def _get_npm_global_path(self) -> Optional[Path]:
        """Get npm global packages path."""
        try:
            import subprocess
            result = subprocess.run(
                ["npm", "root", "-g"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            return Path(result.stdout.strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def _get_python_site_packages(self) -> List[Path]:
        """Get Python site-packages paths."""
        import site
        return [Path(p) for p in site.getsitepackages() if Path(p).exists()]

    async def _scan_directory_for_mcp(self, directory: Path) -> List[str]:
        """Scan a directory for MCP server indicators."""
        mcp_servers = []
        
        try:
            # Look for package.json files with MCP server indicators
            for package_file in directory.rglob("package.json"):
                try:
                    with open(package_file, 'r', encoding='utf-8') as f:
                        package_data = json.load(f)
                    
                    # Check for MCP-related keywords
                    if self._is_mcp_package(package_data):
                        mcp_servers.append(package_data.get("name", str(package_file.parent)))
                except (json.JSONDecodeError, IOError):
                    continue
            
            # Look for Python packages with MCP indicators
            for setup_file in directory.rglob("setup.py"):
                parent_name = setup_file.parent.name
                if "mcp" in parent_name.lower():
                    mcp_servers.append(parent_name)
            
            # Look for pyproject.toml files
            for pyproject_file in directory.rglob("pyproject.toml"):
                try:
                    import tomllib
                    with open(pyproject_file, 'rb') as f:
                        pyproject_data = tomllib.load(f)
                    
                    if self._is_mcp_python_package(pyproject_data):
                        project_name = pyproject_data.get("project", {}).get("name")
                        if project_name:
                            mcp_servers.append(project_name)
                except Exception:
                    continue
        
        except Exception as e:
            logger.debug(f"Error scanning directory {directory}: {e}")
        
        return mcp_servers

    def _is_mcp_package(self, package_data: dict) -> bool:
        """Check if a package.json indicates an MCP server."""
        name = package_data.get("name", "").lower()
        description = package_data.get("description", "").lower()
        keywords = package_data.get("keywords", [])
        
        mcp_indicators = ["mcp", "model-context-protocol", "mcp-server"]
        
        # Check name
        if any(indicator in name for indicator in mcp_indicators):
            return True
        
        # Check description
        if any(indicator in description for indicator in mcp_indicators):
            return True
        
        # Check keywords
        if any(keyword.lower() in mcp_indicators for keyword in keywords):
            return True
        
        return False

    def _is_mcp_python_package(self, pyproject_data: dict) -> bool:
        """Check if a pyproject.toml indicates an MCP server."""
        project = pyproject_data.get("project", {})
        name = project.get("name", "").lower()
        description = project.get("description", "").lower()
        keywords = project.get("keywords", [])
        
        mcp_indicators = ["mcp", "model-context-protocol", "mcp-server"]
        
        # Check name
        if any(indicator in name for indicator in mcp_indicators):
            return True
        
        # Check description
        if any(indicator in description for indicator in mcp_indicators):
            return True
        
        # Check keywords
        if any(keyword.lower() in mcp_indicators for keyword in keywords):
            return True
        
        return False

    async def get_client_configs(self) -> List[ClientConfig]:
        """Get configurations for all discovered clients."""
        configs = []
        discovered_clients = await self.discover_clients()
        
        for client in discovered_clients:
            if client.installed and client.config_path:
                try:
                    with open(client.config_path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    
                    client_info = self.supported_clients[client.client_type]
                    mcp_key = client_info["mcp_key"]
                    servers = config_data.get(mcp_key, {})
                    
                    configs.append(ClientConfig(
                        client_type=client.client_type,
                        config_path=client.config_path,
                        servers=servers,
                    ))
                except Exception as e:
                    logger.debug(f"Error reading config for {client.client_type}: {e}")
        
        return configs