"""Pytest configuration and fixtures."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_docker_client():
    """Mock Docker client."""
    mock = MagicMock()
    mock.initialize = AsyncMock()
    mock.cleanup = AsyncMock()
    mock.create_container = AsyncMock(return_value="container-123")
    mock.start_container = AsyncMock()
    mock.stop_container = AsyncMock()
    mock.remove_container = AsyncMock()
    mock.list_containers = AsyncMock(return_value=[])
    mock.get_container_info = AsyncMock()
    mock.get_container_logs = AsyncMock(return_value="test logs")
    mock.is_container_running = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_secrets_manager():
    """Mock secrets manager."""
    mock = MagicMock()
    mock.initialize = AsyncMock()
    mock.get_secret = AsyncMock(return_value="secret-value")
    mock.set_secret = AsyncMock()
    mock.delete_secret = AsyncMock()
    mock.list_secrets = AsyncMock(return_value=["secret1", "secret2"])
    return mock


@pytest.fixture
def mock_config_manager():
    """Mock configuration manager."""
    from mcpmanager.core.models import ConfigData
    
    mock = MagicMock()
    mock.initialize = AsyncMock()
    mock.get_config = AsyncMock(return_value=ConfigData())
    mock.set_auto_discovery = AsyncMock()
    mock.set_registry_url = AsyncMock()
    return mock


@pytest.fixture
def mock_registry():
    """Mock MCP registry."""
    from mcpmanager.core.models import MCPServerConfig
    
    mock = MagicMock()
    mock.initialize = AsyncMock()
    mock.get_server_config = AsyncMock(return_value=MCPServerConfig(
        name="test-server",
        image="test:latest"
    ))
    mock.list_servers = AsyncMock(return_value=[])
    mock.search_servers = AsyncMock(return_value=[])
    return mock