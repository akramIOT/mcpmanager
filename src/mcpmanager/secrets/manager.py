"""Secrets management for MCPManager."""

import logging
from typing import List, Optional
from abc import ABC, abstractmethod

from mcpmanager.core.models import SecretsProvider
from mcpmanager.config.manager import ConfigManager

logger = logging.getLogger(__name__)


class SecretsBackend(ABC):
    """Abstract base class for secrets backends."""

    @abstractmethod
    async def get_secret(self, name: str) -> str:
        """Get a secret value."""
        pass

    @abstractmethod
    async def set_secret(self, name: str, value: str) -> None:
        """Set a secret value."""
        pass

    @abstractmethod
    async def delete_secret(self, name: str) -> None:
        """Delete a secret."""
        pass

    @abstractmethod
    async def list_secrets(self) -> List[str]:
        """List all secret names."""
        pass


class NoneSecretsBackend(SecretsBackend):
    """No-op secrets backend that doesn't store secrets."""

    async def get_secret(self, name: str) -> str:
        """Get a secret value."""
        raise ValueError(f"Secrets backend not configured: {name}")

    async def set_secret(self, name: str, value: str) -> None:
        """Set a secret value."""
        raise ValueError("Secrets backend not configured")

    async def delete_secret(self, name: str) -> None:
        """Delete a secret."""
        raise ValueError("Secrets backend not configured")

    async def list_secrets(self) -> List[str]:
        """List all secret names."""
        return []


class EncryptedSecretsBackend(SecretsBackend):
    """Encrypted secrets backend using local keyring."""

    def __init__(self):
        """Initialize encrypted secrets backend."""
        self._keyring = None
        self._service_name = "mcpmanager"

    async def _get_keyring(self):
        """Get keyring instance."""
        if self._keyring is None:
            try:
                import keyring
                self._keyring = keyring
            except ImportError:
                raise RuntimeError("keyring package required for encrypted secrets. Install with: pip install keyring")
        
        return self._keyring

    async def get_secret(self, name: str) -> str:
        """Get a secret value from keyring."""
        keyring = await self._get_keyring()
        
        try:
            value = keyring.get_password(self._service_name, name)
            if value is None:
                raise ValueError(f"Secret not found: {name}")
            return value
        except Exception as e:
            logger.error(f"Failed to get secret {name}: {e}")
            raise

    async def set_secret(self, name: str, value: str) -> None:
        """Set a secret value in keyring."""
        keyring = await self._get_keyring()
        
        try:
            keyring.set_password(self._service_name, name, value)
            logger.info(f"Secret {name} stored successfully")
        except Exception as e:
            logger.error(f"Failed to set secret {name}: {e}")
            raise

    async def delete_secret(self, name: str) -> None:
        """Delete a secret from keyring."""
        keyring = await self._get_keyring()
        
        try:
            keyring.delete_password(self._service_name, name)
            logger.info(f"Secret {name} deleted successfully")
        except Exception as e:
            logger.error(f"Failed to delete secret {name}: {e}")
            raise

    async def list_secrets(self) -> List[str]:
        """List all secret names."""
        # keyring doesn't provide a direct way to list all secrets
        # This is a limitation of the keyring API
        logger.warning("Listing secrets not supported by encrypted backend")
        return []


class OnePasswordSecretsBackend(SecretsBackend):
    """1Password secrets backend."""

    def __init__(self):
        """Initialize 1Password secrets backend."""
        self._op_client = None

    async def _get_op_client(self):
        """Get 1Password CLI client."""
        if self._op_client is None:
            try:
                import subprocess
                # Check if op CLI is available
                result = subprocess.run(
                    ["op", "--version"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                self._op_client = "available"
                logger.info(f"1Password CLI version: {result.stdout.strip()}")
            except (subprocess.CalledProcessError, FileNotFoundError):
                raise RuntimeError("1Password CLI not found. Please install op CLI tool.")
        
        return self._op_client

    async def get_secret(self, name: str) -> str:
        """Get a secret value from 1Password."""
        await self._get_op_client()
        
        try:
            import subprocess
            import os
            
            # Check for service account token
            if not os.getenv("OP_SERVICE_ACCOUNT_TOKEN"):
                raise ValueError("OP_SERVICE_ACCOUNT_TOKEN environment variable required")
            
            # Use op CLI to get secret
            result = subprocess.run(
                ["op", "read", name],
                capture_output=True,
                text=True,
                check=True,
                env=os.environ
            )
            
            return result.stdout.strip()
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get secret {name} from 1Password: {e.stderr}")
            raise ValueError(f"Secret not found or access denied: {name}")
        except Exception as e:
            logger.error(f"Failed to get secret {name}: {e}")
            raise

    async def set_secret(self, name: str, value: str) -> None:
        """Set a secret value in 1Password."""
        # 1Password CLI doesn't support creating secrets programmatically
        # in the same way as other backends
        raise NotImplementedError("Setting secrets not supported with 1Password backend")

    async def delete_secret(self, name: str) -> None:
        """Delete a secret from 1Password."""
        raise NotImplementedError("Deleting secrets not supported with 1Password backend")

    async def list_secrets(self) -> List[str]:
        """List all secret names."""
        # This would require parsing vault items, which is complex
        # and depends on the vault structure
        raise NotImplementedError("Listing secrets not supported with 1Password backend")


class SecretsManager:
    """Main secrets manager."""

    def __init__(self, config_manager: ConfigManager):
        """Initialize secrets manager."""
        self.config_manager = config_manager
        self._backend: Optional[SecretsBackend] = None

    async def initialize(self) -> None:
        """Initialize the secrets manager."""
        config = await self.config_manager.get_config()
        provider = config.secrets_provider
        
        if provider == SecretsProvider.NONE:
            self._backend = NoneSecretsBackend()
        elif provider == SecretsProvider.ENCRYPTED:
            self._backend = EncryptedSecretsBackend()
        elif provider == SecretsProvider.ONEPASSWORD:
            self._backend = OnePasswordSecretsBackend()
        else:
            raise ValueError(f"Unknown secrets provider: {provider}")
        
        logger.info(f"Secrets manager initialized with {provider.value} backend")

    async def get_secret(self, name: str) -> str:
        """Get a secret value."""
        if not self._backend:
            await self.initialize()
        
        return await self._backend.get_secret(name)

    async def set_secret(self, name: str, value: str) -> None:
        """Set a secret value."""
        if not self._backend:
            await self.initialize()
        
        await self._backend.set_secret(name, value)

    async def delete_secret(self, name: str) -> None:
        """Delete a secret."""
        if not self._backend:
            await self.initialize()
        
        await self._backend.delete_secret(name)

    async def list_secrets(self) -> List[str]:
        """List all secret names."""
        if not self._backend:
            await self.initialize()
        
        return await self._backend.list_secrets()

    async def test_secret(self, name: str) -> bool:
        """Test if a secret exists and can be retrieved."""
        try:
            await self.get_secret(name)
            return True
        except Exception:
            return False

    async def get_provider_info(self) -> dict:
        """Get information about the current secrets provider."""
        config = await self.config_manager.get_config()
        provider = config.secrets_provider
        
        info = {
            "provider": provider.value,
            "supports_set": provider != SecretsProvider.ONEPASSWORD,
            "supports_delete": provider == SecretsProvider.ENCRYPTED,
            "supports_list": provider == SecretsProvider.ENCRYPTED,
        }
        
        if provider == SecretsProvider.ONEPASSWORD:
            import os
            info["service_account_configured"] = bool(os.getenv("OP_SERVICE_ACCOUNT_TOKEN"))
        
        return info