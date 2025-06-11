"""Tests for MCPManager core functionality."""

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from mcpmanager.core.manager import MCPManager
from mcpmanager.core.models import MCPServerConfig, TransportType
from mcpmanager.exceptions import MCPManagerError


class TestMCPManager:
    """Test cases for MCPManager."""

    @pytest_asyncio.fixture
    async def manager(self):
        """Create a test MCPManager instance."""
        with patch('mcpmanager.container.docker_client.DockerClient') as mock_docker, \
             patch('mcpmanager.secrets.manager.SecretsManager') as mock_secrets, \
             patch('mcpmanager.config.manager.ConfigManager') as mock_config, \
             patch('mcpmanager.core.registry.MCPRegistry') as mock_registry, \
             patch('mcpmanager.runtime.manager.RuntimeManager') as mock_runtime:
            
            # Setup mocks
            mock_docker.return_value.initialize = AsyncMock()
            mock_docker.return_value.cleanup = AsyncMock()
            mock_secrets.return_value.initialize = AsyncMock()
            mock_registry.return_value.initialize = AsyncMock()
            mock_runtime.return_value.initialize = AsyncMock()
            mock_runtime.return_value.cleanup = AsyncMock()
            mock_config.return_value = MagicMock()
            
            manager = MCPManager(
                docker_client=mock_docker.return_value,
                secrets_manager=mock_secrets.return_value,
                config_manager=mock_config.return_value,
                registry=mock_registry.return_value,
                runtime_manager=mock_runtime.return_value,
            )
            
            await manager.initialize()
            yield manager
            await manager.cleanup()

    @pytest.mark.asyncio
    async def test_initialize(self, manager):
        """Test manager initialization."""
        assert manager.docker_client is not None
        assert manager.secrets_manager is not None
        assert manager.registry is not None

    @pytest.mark.asyncio 
    async def test_run_server_success(self, manager):
        """Test successful server creation."""
        # Mock dependencies
        manager.registry.get_server_config = AsyncMock(return_value=MCPServerConfig(
            name="test-server",
            image="test-image:latest",
            transport=TransportType.STDIO,
        ))
        
        manager.runtime_manager.create_container = AsyncMock(return_value="container-123")
        manager.runtime_manager.start_container = AsyncMock()
        manager.transport_factory.create_transport = AsyncMock()
        
        mock_transport = AsyncMock()
        mock_transport.start = AsyncMock()
        manager.transport_factory.create_transport.return_value = mock_transport
        
        # Test server creation
        instance = await manager.run_server("test-server")
        
        assert instance.name == "test-server"
        assert instance.container_id == "container-123"
        assert "test-server" in manager._running_servers

    @pytest.mark.asyncio
    async def test_run_server_duplicate(self, manager):
        """Test running duplicate server raises error."""
        # Add a server to running servers
        manager._running_servers["test-server"] = MagicMock()
        
        with pytest.raises(ValueError, match="already running"):
            await manager.run_server("test-server")

    @pytest.mark.asyncio
    async def test_stop_server_success(self, manager):
        """Test successful server stop."""
        # Setup running server
        mock_instance = MagicMock()
        mock_instance.container_id = "container-123"
        manager._running_servers["test-server"] = mock_instance
        
        manager.runtime_manager.stop_container = AsyncMock()
        
        # Test server stop
        await manager.stop_server("test-server")
        
        assert "test-server" not in manager._running_servers
        manager.runtime_manager.stop_container.assert_called_once_with("container-123")

    @pytest.mark.asyncio
    async def test_stop_server_not_found(self, manager):
        """Test stopping non-existent server raises error."""
        with pytest.raises(ValueError, match="not running"):
            await manager.stop_server("non-existent")

    @pytest.mark.asyncio
    async def test_list_servers(self, manager):
        """Test listing servers."""
        # Add mock servers
        mock_instance1 = MagicMock()
        mock_instance2 = MagicMock()
        manager._running_servers = {
            "server1": mock_instance1,
            "server2": mock_instance2,
        }
        
        servers = await manager.list_servers()
        
        assert len(servers) == 2
        assert mock_instance1 in servers
        assert mock_instance2 in servers

    @pytest.mark.asyncio
    async def test_search_servers(self, manager):
        """Test server search."""
        mock_servers = [
            MCPServerConfig(name="fetch-server", image="fetch:latest"),
            MCPServerConfig(name="github-server", image="github:latest"),
        ]
        manager.registry.search_servers = AsyncMock(return_value=mock_servers)
        
        results = await manager.search_servers("fetch")
        
        assert len(results) == 2
        manager.registry.search_servers.assert_called_once_with("fetch")


@pytest.mark.asyncio
async def test_manager_context_manager():
    """Test manager as async context manager."""
    with patch('mcpmanager.container.docker_client.DockerClient') as mock_docker, \
         patch('mcpmanager.secrets.manager.SecretsManager') as mock_secrets, \
         patch('mcpmanager.config.manager.ConfigManager') as mock_config, \
         patch('mcpmanager.core.registry.MCPRegistry') as mock_registry, \
         patch('mcpmanager.runtime.manager.RuntimeManager') as mock_runtime:
        
        # Setup mocks
        mock_docker.return_value.initialize = AsyncMock()
        mock_docker.return_value.cleanup = AsyncMock()
        mock_secrets.return_value.initialize = AsyncMock()
        mock_registry.return_value.initialize = AsyncMock()
        mock_runtime.return_value.initialize = AsyncMock()
        mock_runtime.return_value.cleanup = AsyncMock()
        
        async with MCPManager() as manager:
            assert manager is not None
        
        # Cleanup should be called
        mock_docker.return_value.cleanup.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])