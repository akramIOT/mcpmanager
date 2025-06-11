"""Permission management system."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml

from .profiles import (
    AdvancedPermissionProfile,
    PermissionTemplate,
    PERMISSION_TEMPLATES,
    SecurityLevel,
)

logger = logging.getLogger(__name__)


class PermissionManager:
    """Advanced permission management system."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize permission manager."""
        self.config_dir = config_dir or Path.home() / ".mcpmanager" / "permissions"
        self.profiles_dir = self.config_dir / "profiles"
        self.templates_dir = self.config_dir / "templates"
        
        # Ensure directories exist
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache for loaded profiles and templates
        self._profiles_cache: Dict[str, AdvancedPermissionProfile] = {}
        self._templates_cache: Dict[str, PermissionTemplate] = {}
        
        # Initialize with built-in profiles and templates
        self._initialize_builtin_resources()

    def _initialize_builtin_resources(self):
        """Initialize built-in profiles and templates."""
        try:
            # Create built-in profiles if they don't exist
            builtin_profiles = [
                AdvancedPermissionProfile.minimal(),
                AdvancedPermissionProfile.restricted(),
                AdvancedPermissionProfile.standard(),
                AdvancedPermissionProfile.privileged(),
            ]
            
            for profile in builtin_profiles:
                profile_path = self.profiles_dir / f"{profile.name}.json"
                if not profile_path.exists():
                    self._save_profile_sync(profile)
            
            # Create built-in templates if they don't exist
            for template_name, template in PERMISSION_TEMPLATES.items():
                template_path = self.templates_dir / f"{template_name}.json"
                if not template_path.exists():
                    self._save_template_sync(template)
                    
        except Exception as e:
            logger.error(f"Failed to initialize built-in resources: {e}")
    
    def _save_profile_sync(self, profile: AdvancedPermissionProfile):
        """Synchronously save a profile (for initialization)."""
        try:
            profile_path = self.profiles_dir / f"{profile.name}.json"
            with open(profile_path, 'w') as f:
                json.dump(profile.model_dump(), f, indent=2, default=str)
            logger.debug(f"Saved built-in profile: {profile.name}")
        except Exception as e:
            logger.error(f"Failed to save built-in profile {profile.name}: {e}")
    
    def _save_template_sync(self, template: PermissionTemplate):
        """Synchronously save a template (for initialization)."""
        try:
            template_path = self.templates_dir / f"{template.name}.json"
            with open(template_path, 'w') as f:
                json.dump(template.model_dump(), f, indent=2, default=str)
            logger.debug(f"Saved built-in template: {template.name}")
        except Exception as e:
            logger.error(f"Failed to save built-in template {template.name}: {e}")

    async def get_profile(self, name: str) -> Optional[AdvancedPermissionProfile]:
        """Get a permission profile by name."""
        # Check cache first
        if name in self._profiles_cache:
            return self._profiles_cache[name]
        
        # Try to load from file
        profile = await self._load_profile_from_file(name)
        if profile:
            self._profiles_cache[name] = profile
            return profile
        
        return None

    async def _load_profile_from_file(self, name: str) -> Optional[AdvancedPermissionProfile]:
        """Load profile from file."""
        for ext in [".json", ".yaml", ".yml"]:
            profile_path = self.profiles_dir / f"{name}{ext}"
            if profile_path.exists():
                try:
                    with open(profile_path, 'r', encoding='utf-8') as f:
                        if ext == ".json":
                            data = json.load(f)
                        else:
                            data = yaml.safe_load(f)
                    
                    return AdvancedPermissionProfile(**data)
                except Exception as e:
                    logger.error(f"Failed to load profile {name} from {profile_path}: {e}")
        
        return None

    async def save_profile(self, profile: AdvancedPermissionProfile, format: str = "json") -> None:
        """Save a permission profile."""
        try:
            if format == "json":
                profile_path = self.profiles_dir / f"{profile.name}.json"
                with open(profile_path, 'w', encoding='utf-8') as f:
                    json.dump(profile.model_dump(), f, indent=2, default=str)
            else:  # yaml
                profile_path = self.profiles_dir / f"{profile.name}.yaml"
                with open(profile_path, 'w', encoding='utf-8') as f:
                    yaml.dump(profile.model_dump(), f, default_flow_style=False)
            
            # Update cache
            self._profiles_cache[profile.name] = profile
            logger.info(f"Saved permission profile: {profile.name}")
            
        except Exception as e:
            logger.error(f"Failed to save profile {profile.name}: {e}")
            raise

    async def delete_profile(self, name: str) -> bool:
        """Delete a permission profile."""
        try:
            # Remove from cache
            self._profiles_cache.pop(name, None)
            
            # Remove files
            removed = False
            for ext in [".json", ".yaml", ".yml"]:
                profile_path = self.profiles_dir / f"{name}{ext}"
                if profile_path.exists():
                    profile_path.unlink()
                    removed = True
            
            if removed:
                logger.info(f"Deleted permission profile: {name}")
            
            return removed
            
        except Exception as e:
            logger.error(f"Failed to delete profile {name}: {e}")
            return False

    async def list_profiles(self) -> List[str]:
        """List all available permission profiles."""
        profiles = set()
        
        # Add cached profiles
        profiles.update(self._profiles_cache.keys())
        
        # Add profiles from files
        for profile_file in self.profiles_dir.glob("*.json"):
            profiles.add(profile_file.stem)
        for profile_file in self.profiles_dir.glob("*.yaml"):
            profiles.add(profile_file.stem)
        for profile_file in self.profiles_dir.glob("*.yml"):
            profiles.add(profile_file.stem)
        
        return sorted(list(profiles))

    async def get_template(self, name: str) -> Optional[PermissionTemplate]:
        """Get a permission template by name."""
        # Check cache first
        if name in self._templates_cache:
            return self._templates_cache[name]
        
        # Try built-in templates
        if name in PERMISSION_TEMPLATES:
            template = PERMISSION_TEMPLATES[name]
            self._templates_cache[name] = template
            return template
        
        # Try to load from file
        template = await self._load_template_from_file(name)
        if template:
            self._templates_cache[name] = template
            return template
        
        return None

    async def _load_template_from_file(self, name: str) -> Optional[PermissionTemplate]:
        """Load template from file."""
        for ext in [".json", ".yaml", ".yml"]:
            template_path = self.templates_dir / f"{name}{ext}"
            if template_path.exists():
                try:
                    with open(template_path, 'r', encoding='utf-8') as f:
                        if ext == ".json":
                            data = json.load(f)
                        else:
                            data = yaml.safe_load(f)
                    
                    return PermissionTemplate(**data)
                except Exception as e:
                    logger.error(f"Failed to load template {name} from {template_path}: {e}")
        
        return None

    async def save_template(self, template: PermissionTemplate, format: str = "json") -> None:
        """Save a permission template."""
        try:
            if format == "json":
                template_path = self.templates_dir / f"{template.name}.json"
                with open(template_path, 'w', encoding='utf-8') as f:
                    json.dump(template.model_dump(), f, indent=2, default=str)
            else:  # yaml
                template_path = self.templates_dir / f"{template.name}.yaml"
                with open(template_path, 'w', encoding='utf-8') as f:
                    yaml.dump(template.model_dump(), f, default_flow_style=False)
            
            # Update cache
            self._templates_cache[template.name] = template
            logger.info(f"Saved permission template: {template.name}")
            
        except Exception as e:
            logger.error(f"Failed to save template {template.name}: {e}")
            raise

    async def create_profile_from_template(
        self, 
        template_name: str, 
        profile_name: str,
        additional_overrides: Optional[Dict[str, Any]] = None
    ) -> AdvancedPermissionProfile:
        """Create a profile from a template."""
        template = await self.get_template(template_name)
        if not template:
            raise ValueError(f"Template not found: {template_name}")
        
        # Get base profile
        base_profile = await self.get_profile(template.base_profile)
        if not base_profile:
            raise ValueError(f"Base profile not found: {template.base_profile}")
        
        # Apply template overrides
        profile = template.apply_to_profile(base_profile)
        
        # Apply additional overrides
        if additional_overrides:
            profile_dict = profile.model_dump()
            for key, value in additional_overrides.items():
                if "." in key:
                    keys = key.split(".")
                    current = profile_dict
                    for k in keys[:-1]:
                        if k not in current:
                            current[k] = {}
                        current = current[k]
                    current[keys[-1]] = value
                else:
                    profile_dict[key] = value
            profile = AdvancedPermissionProfile(**profile_dict)
        
        # Update profile metadata
        profile.name = profile_name
        profile.description = f"Profile created from template: {template_name}"
        
        return profile

    async def validate_profile(self, profile: AdvancedPermissionProfile) -> List[str]:
        """Validate a permission profile and return warnings/errors."""
        warnings = []
        
        try:
            # Check for common security issues
            if profile.security_context and profile.security_context.privileged:
                warnings.append("Profile uses privileged mode - high security risk")
            
            if profile.security_context and not profile.security_context.run_as_non_root:
                warnings.append("Profile allows running as root - security risk")
            
            if profile.network_policy and profile.network_policy.allow_internet:
                warnings.append("Profile allows internet access - potential data exfiltration risk")
            
            if profile.volume_policy and profile.volume_policy.allow_host_paths:
                warnings.append("Profile allows host path mounts - container escape risk")
            
            if profile.volume_policy and profile.volume_policy.allow_sensitive_paths:
                warnings.append("Profile allows sensitive path access - critical security risk")
            
            if profile.capabilities:
                dangerous_caps = ["SYS_ADMIN", "SYS_MODULE", "SYS_RAWIO", "SYS_TIME", "NET_ADMIN"]
                for cap in profile.capabilities.add:
                    if cap in dangerous_caps:
                        warnings.append(f"Profile adds dangerous capability: {cap}")
            
            # Check resource limits
            if not profile.resource_limits:
                warnings.append("No resource limits specified - potential resource exhaustion")
            else:
                if not profile.resource_limits.memory:
                    warnings.append("No memory limit specified")
                if not profile.resource_limits.cpu_limit:
                    warnings.append("No CPU limit specified")
            
            # Check for conflicting settings
            if (profile.security_context and 
                profile.security_context.read_only_root_filesystem and 
                profile.write_paths and 
                any(path.startswith('/') and not path.startswith('/tmp') for path in profile.write_paths)):
                warnings.append("Read-only root filesystem enabled but write paths include root paths")
            
        except Exception as e:
            warnings.append(f"Validation error: {e}")
        
        return warnings

    async def get_profile_recommendations(self, use_case: str) -> List[str]:
        """Get profile recommendations for a specific use case."""
        recommendations = []
        
        use_case_lower = use_case.lower()
        
        # Analyze templates that match the use case
        for template_name, template in PERMISSION_TEMPLATES.items():
            if any(uc.lower() in use_case_lower for uc in template.use_cases):
                recommendations.append(template_name)
        
        # Add general recommendations based on keywords
        if any(keyword in use_case_lower for keyword in ["web", "http", "api", "service"]):
            recommendations.append("web-service")
        
        if any(keyword in use_case_lower for keyword in ["database", "db", "mysql", "postgres", "mongo"]):
            recommendations.append("database")
        
        if any(keyword in use_case_lower for keyword in ["ml", "ai", "machine learning", "tensorflow", "pytorch"]):
            recommendations.append("ml-workload")
        
        if any(keyword in use_case_lower for keyword in ["build", "ci", "cd", "test"]):
            recommendations.append("ci-cd")
        
        if any(keyword in use_case_lower for keyword in ["untrusted", "sandbox", "user code"]):
            recommendations.append("sandbox")
        
        # Remove duplicates and return
        return list(set(recommendations))

    async def export_profile(self, name: str, output_path: str, format: str = "json") -> None:
        """Export a profile to a file."""
        profile = await self.get_profile(name)
        if not profile:
            raise ValueError(f"Profile not found: {name}")
        
        output_file = Path(output_path)
        
        try:
            if format == "json":
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(profile.model_dump(), f, indent=2, default=str)
            else:  # yaml
                with open(output_file, 'w', encoding='utf-8') as f:
                    yaml.dump(profile.model_dump(), f, default_flow_style=False)
            
            logger.info(f"Exported profile {name} to {output_file}")
            
        except Exception as e:
            logger.error(f"Failed to export profile {name}: {e}")
            raise

    async def import_profile(self, file_path: str) -> AdvancedPermissionProfile:
        """Import a profile from a file."""
        input_file = Path(file_path)
        
        if not input_file.exists():
            raise FileNotFoundError(f"Profile file not found: {file_path}")
        
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                if input_file.suffix.lower() == ".json":
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f)
            
            profile = AdvancedPermissionProfile(**data)
            
            # Save the imported profile
            await self.save_profile(profile)
            
            logger.info(f"Imported profile {profile.name} from {input_file}")
            return profile
            
        except Exception as e:
            logger.error(f"Failed to import profile from {file_path}: {e}")
            raise

    def convert_to_legacy_profile(self, profile: AdvancedPermissionProfile) -> Dict[str, Any]:
        """Convert advanced profile to legacy PermissionProfile format."""
        from mcpmanager.core.models import PermissionProfile, NetworkPermissions
        
        # Build network permissions
        network_perms = {}
        if profile.network_policy:
            network_perms["default"] = NetworkPermissions(
                insecure_allow_all=profile.network_policy.allow_internet,
                allow_host=profile.network_policy.allowed_hosts,
                allow_port=profile.network_policy.allowed_ports
            )
        
        # Create legacy profile
        legacy_profile = PermissionProfile(
            read=profile.read_paths,
            write=profile.write_paths,
            network=network_perms if network_perms else None
        )
        
        return legacy_profile.model_dump()

    def get_runtime_config(self, profile: AdvancedPermissionProfile) -> Dict[str, Any]:
        """Generate runtime configuration for container engines."""
        config = {}
        
        # Security context
        if profile.security_context:
            config.update({
                "user": profile.security_context.run_as_user,
                "group": profile.security_context.run_as_group,
                "privileged": profile.security_context.privileged,
                "read_only_rootfs": profile.security_context.read_only_root_filesystem,
                "no_new_privs": not profile.security_context.allow_privilege_escalation,
            })
            
            if profile.security_context.seccomp_profile:
                config["security_opt"] = [f"seccomp={profile.security_context.seccomp_profile}"]
        
        # Capabilities
        if profile.capabilities:
            config["cap_add"] = profile.capabilities.add
            config["cap_drop"] = profile.capabilities.drop
        
        # Resource limits
        if profile.resource_limits:
            config.update({
                "mem_limit": profile.resource_limits.memory,
                "memswap_limit": profile.resource_limits.memory_swap,
                "cpu_quota": profile.resource_limits.cpu_limit,
                "pids_limit": profile.resource_limits.pids_limit,
            })
            
            if profile.resource_limits.ulimits:
                config["ulimits"] = profile.resource_limits.ulimits
        
        # Network
        if profile.network_policy:
            if profile.network_policy.mode.value != "bridge":
                config["network_mode"] = profile.network_policy.mode.value
        
        return config