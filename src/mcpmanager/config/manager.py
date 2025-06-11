"""Configuration management for MCPManager."""

import logging
import json
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
import os

from mcpmanager.core.models import ConfigData, SecretsProvider, OIDCConfig, TelemetryConfig, VerificationConfig

logger = logging.getLogger(__name__)


class ConfigManager:
    """Configuration manager for MCPManager."""

    def __init__(self, config_dir: Optional[str] = None):
        """Initialize configuration manager."""
        self.config_dir = Path(config_dir) if config_dir else Path.home() / ".mcpmanager"
        self.config_file = self.config_dir / "config.json"
        self.state_file = self.config_dir / "state.json"
        self._config_data: Optional[ConfigData] = None

    async def initialize(self) -> None:
        """Initialize configuration directory and load config."""
        # Create config directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing config or create default
        await self._load_config()

    async def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_dict = json.load(f)
                self._config_data = ConfigData(**config_dict)
                logger.info(f"Configuration loaded from {self.config_file}")
            else:
                # Create default configuration
                self._config_data = ConfigData()
                await self._save_config()
                logger.info("Created default configuration")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            # Fall back to default config
            self._config_data = ConfigData()

    async def _save_config(self) -> None:
        """Save configuration to file."""
        try:
            config_dict = self._config_data.model_dump()
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, default=str)
            
            logger.debug(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            raise

    async def get_config(self) -> ConfigData:
        """Get current configuration."""
        if self._config_data is None:
            await self._load_config()
        return self._config_data

    async def set_auto_discovery(self, enabled: bool) -> None:
        """Set auto-discovery setting."""
        config = await self.get_config()
        config.auto_discovery_enabled = enabled
        await self._save_config()
        logger.info(f"Auto-discovery {'enabled' if enabled else 'disabled'}")

    async def set_registry_url(self, url: Optional[str]) -> None:
        """Set registry URL."""
        config = await self.get_config()
        config.registry_url = url
        await self._save_config()
        logger.info(f"Registry URL set to: {url or 'built-in'}")

    async def set_ca_cert_path(self, path: Optional[str]) -> None:
        """Set CA certificate path."""
        config = await self.get_config()
        config.ca_cert_path = path
        await self._save_config()
        logger.info(f"CA certificate path set to: {path}")

    async def set_secrets_provider(self, provider: SecretsProvider) -> None:
        """Set secrets provider."""
        config = await self.get_config()
        config.secrets_provider = provider
        await self._save_config()
        logger.info(f"Secrets provider set to: {provider.value}")

    async def add_registered_client(self, client_name: str) -> None:
        """Add a registered client."""
        config = await self.get_config()
        if client_name not in config.registered_clients:
            config.registered_clients.append(client_name)
            await self._save_config()
            logger.info(f"Registered client: {client_name}")

    async def remove_registered_client(self, client_name: str) -> None:
        """Remove a registered client."""
        config = await self.get_config()
        if client_name in config.registered_clients:
            config.registered_clients.remove(client_name)
            await self._save_config()
            logger.info(f"Unregistered client: {client_name}")

    async def set_oidc_config(self, oidc_config: Optional[OIDCConfig]) -> None:
        """Set OIDC configuration."""
        config = await self.get_config()
        config.oidc = oidc_config
        await self._save_config()
        logger.info("OIDC configuration updated")

    async def set_telemetry_config(self, telemetry_config: Optional[TelemetryConfig]) -> None:
        """Set telemetry configuration."""
        config = await self.get_config()
        config.telemetry = telemetry_config
        await self._save_config()
        logger.info("Telemetry configuration updated")

    async def set_verification_config(self, verification_config: Optional[VerificationConfig]) -> None:
        """Set verification configuration."""
        config = await self.get_config()
        config.verification = verification_config
        await self._save_config()
        logger.info("Verification configuration updated")

    def get_verification_config(self) -> Optional[Dict[str, Any]]:
        """Get verification configuration."""
        if self._config_data and self._config_data.verification:
            return self._config_data.verification.model_dump()
        return None

    async def get_state(self) -> Dict[str, Any]:
        """Get application state."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return {}

    async def save_state(self, state: Dict[str, Any]) -> None:
        """Save application state."""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, default=str)
            logger.debug(f"State saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            raise

    async def export_config(self, export_path: str, format: str = "json") -> None:
        """Export configuration to file."""
        config = await self.get_config()
        export_file = Path(export_path)
        
        try:
            config_dict = config.model_dump()
            
            if format.lower() == "yaml":
                with open(export_file, 'w', encoding='utf-8') as f:
                    yaml.dump(config_dict, f, default_flow_style=False)
            else:  # JSON
                with open(export_file, 'w', encoding='utf-8') as f:
                    json.dump(config_dict, f, indent=2, default=str)
            
            logger.info(f"Configuration exported to {export_file}")
        except Exception as e:
            logger.error(f"Failed to export configuration: {e}")
            raise

    async def import_config(self, import_path: str) -> None:
        """Import configuration from file."""
        import_file = Path(import_path)
        
        try:
            if not import_file.exists():
                raise FileNotFoundError(f"Configuration file not found: {import_path}")
            
            with open(import_file, 'r', encoding='utf-8') as f:
                if import_file.suffix.lower() in ['.yaml', '.yml']:
                    config_dict = yaml.safe_load(f)
                else:  # JSON
                    config_dict = json.load(f)
            
            # Validate configuration
            self._config_data = ConfigData(**config_dict)
            await self._save_config()
            
            logger.info(f"Configuration imported from {import_file}")
        except Exception as e:
            logger.error(f"Failed to import configuration: {e}")
            raise

    async def reset_config(self) -> None:
        """Reset configuration to defaults."""
        self._config_data = ConfigData()
        await self._save_config()
        logger.info("Configuration reset to defaults")

    def get_config_dir(self) -> Path:
        """Get configuration directory path."""
        return self.config_dir

    def get_config_file_path(self) -> Path:
        """Get configuration file path."""
        return self.config_file

    async def validate_config(self) -> bool:
        """Validate current configuration."""
        try:
            config = await self.get_config()
            
            # Validate OIDC config if present
            if config.oidc:
                if not config.oidc.issuer_url:
                    logger.error("OIDC issuer URL is required")
                    return False
                if not config.oidc.client_id:
                    logger.error("OIDC client ID is required")
                    return False
            
            # Validate registry URL if present
            if config.registry_url:
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        response = await client.head(config.registry_url, timeout=5.0)
                        if response.status_code >= 400:
                            logger.warning(f"Registry URL returned status {response.status_code}")
                except Exception as e:
                    logger.warning(f"Failed to validate registry URL: {e}")
            
            # Validate CA certificate if present
            if config.ca_cert_path:
                cert_path = Path(config.ca_cert_path)
                if not cert_path.exists():
                    logger.error(f"CA certificate file not found: {config.ca_cert_path}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            return False

    @classmethod
    def from_env(cls) -> "ConfigManager":
        """Create configuration manager from environment variables."""
        config_dir = os.getenv("MCPM_CONFIG_DIR")
        return cls(config_dir=config_dir)

    async def get_environment_overrides(self) -> Dict[str, Any]:
        """Get configuration overrides from environment variables."""
        overrides = {}
        
        # Auto-discovery
        if os.getenv("MCPM_AUTO_DISCOVERY"):
            overrides["auto_discovery_enabled"] = os.getenv("MCPM_AUTO_DISCOVERY").lower() in ["true", "1", "yes"]
        
        # Registry URL
        if os.getenv("MCPM_REGISTRY_URL"):
            overrides["registry_url"] = os.getenv("MCPM_REGISTRY_URL")
        
        # CA certificate
        if os.getenv("MCPM_CA_CERT_PATH"):
            overrides["ca_cert_path"] = os.getenv("MCPM_CA_CERT_PATH")
        
        # Secrets provider
        if os.getenv("MCPM_SECRETS_PROVIDER"):
            provider = os.getenv("MCPM_SECRETS_PROVIDER").lower()
            if provider in ["none", "encrypted", "1password"]:
                overrides["secrets_provider"] = provider
        
        return overrides

    async def apply_environment_overrides(self) -> None:
        """Apply environment variable overrides to configuration."""
        overrides = await self.get_environment_overrides()
        
        if overrides:
            config = await self.get_config()
            
            for key, value in overrides.items():
                setattr(config, key, value)
            
            logger.info(f"Applied environment overrides: {list(overrides.keys())}")
            # Note: Don't save to file, these are runtime overrides