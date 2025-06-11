"""Advanced permission profiles and security policies."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field


class SecurityLevel(str, Enum):
    """Security level classification."""
    MINIMAL = "minimal"
    RESTRICTED = "restricted"
    STANDARD = "standard"
    PRIVILEGED = "privileged"


class CapabilityAction(str, Enum):
    """Linux capability actions."""
    ADD = "add"
    DROP = "drop"


class NetworkMode(str, Enum):
    """Network mode options."""
    NONE = "none"
    HOST = "host"
    BRIDGE = "bridge"
    CONTAINER = "container"
    CUSTOM = "custom"


class VolumeType(str, Enum):
    """Volume type options."""
    BIND = "bind"
    TMPFS = "tmpfs"
    VOLUME = "volume"
    SECRET = "secret"
    CONFIGMAP = "configmap"


class ResourceLimit(BaseModel):
    """Resource limits configuration."""
    memory: Optional[str] = None  # e.g., "512m", "1g"
    memory_swap: Optional[str] = None
    cpu_limit: Optional[str] = None  # e.g., "0.5", "2"
    cpu_reservation: Optional[str] = None
    pids_limit: Optional[int] = None
    ulimits: Dict[str, Union[int, str]] = Field(default_factory=dict)
    disk_quota: Optional[str] = None
    network_bandwidth: Optional[str] = None


class CapabilitySet(BaseModel):
    """Linux capabilities configuration."""
    add: List[str] = Field(default_factory=list)
    drop: List[str] = Field(default_factory=list)
    
    @classmethod
    def minimal(cls) -> "CapabilitySet":
        """Minimal capabilities (drop all)."""
        return cls(
            drop=["ALL"],
            add=[]
        )
    
    @classmethod
    def restricted(cls) -> "CapabilitySet":
        """Restricted capabilities for basic functionality."""
        return cls(
            drop=["ALL"],
            add=["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"]
        )
    
    @classmethod
    def standard(cls) -> "CapabilitySet":
        """Standard capabilities for most applications."""
        return cls(
            drop=["SYS_ADMIN", "SYS_MODULE", "SYS_RAWIO", "SYS_TIME"],
            add=[]
        )


class NetworkPolicy(BaseModel):
    """Network access policies."""
    mode: NetworkMode = NetworkMode.BRIDGE
    allowed_hosts: List[str] = Field(default_factory=list)
    blocked_hosts: List[str] = Field(default_factory=list)
    allowed_ports: List[int] = Field(default_factory=list)
    blocked_ports: List[int] = Field(default_factory=list)
    allow_localhost: bool = True
    allow_private_networks: bool = True
    allow_internet: bool = False
    dns_servers: List[str] = Field(default_factory=list)
    firewall_rules: List[Dict[str, Any]] = Field(default_factory=list)
    
    @classmethod
    def isolated(cls) -> "NetworkPolicy":
        """Completely isolated network policy."""
        return cls(
            mode=NetworkMode.NONE,
            allow_localhost=False,
            allow_private_networks=False,
            allow_internet=False
        )
    
    @classmethod
    def restricted(cls) -> "NetworkPolicy":
        """Restricted network access."""
        return cls(
            mode=NetworkMode.BRIDGE,
            allow_localhost=True,
            allow_private_networks=False,
            allow_internet=False,
            blocked_ports=[22, 23, 80, 443, 993, 995]  # Common service ports
        )


class VolumePolicy(BaseModel):
    """Volume mount policies."""
    allowed_types: List[VolumeType] = Field(default_factory=list)
    allowed_sources: List[str] = Field(default_factory=list)
    blocked_sources: List[str] = Field(default_factory=list)
    read_only_enforced: bool = True
    max_size: Optional[str] = None
    allow_host_paths: bool = False
    allow_sensitive_paths: bool = False
    sensitive_path_patterns: List[str] = Field(default_factory=lambda: [
        "/etc/passwd", "/etc/shadow", "/etc/hosts", "/etc/ssh/*",
        "/root/*", "/home/*/.ssh/*", "/var/run/docker.sock",
        "/proc/*", "/sys/*", "/dev/*"
    ])
    
    @classmethod
    def minimal(cls) -> "VolumePolicy":
        """Minimal volume access."""
        return cls(
            allowed_types=[VolumeType.TMPFS],
            read_only_enforced=True,
            allow_host_paths=False,
            allow_sensitive_paths=False
        )
    
    @classmethod
    def restricted(cls) -> "VolumePolicy":
        """Restricted volume access."""
        return cls(
            allowed_types=[VolumeType.TMPFS, VolumeType.VOLUME],
            allowed_sources=["/tmp", "/var/tmp", "/app/data"],
            read_only_enforced=True,
            allow_host_paths=False,
            allow_sensitive_paths=False
        )


class SecurityContext(BaseModel):
    """Security context configuration."""
    run_as_user: Optional[int] = None
    run_as_group: Optional[int] = None
    run_as_non_root: bool = True
    read_only_root_filesystem: bool = True
    allow_privilege_escalation: bool = False
    privileged: bool = False
    seccomp_profile: Optional[str] = None
    selinux_options: Dict[str, str] = Field(default_factory=dict)
    apparmor_profile: Optional[str] = None
    supplemental_groups: List[int] = Field(default_factory=list)
    fs_group: Optional[int] = None
    
    @classmethod
    def minimal(cls) -> "SecurityContext":
        """Minimal security context."""
        return cls(
            run_as_user=65534,  # nobody
            run_as_group=65534,
            run_as_non_root=True,
            read_only_root_filesystem=True,
            allow_privilege_escalation=False,
            privileged=False,
            seccomp_profile="runtime/default"
        )
    
    @classmethod
    def restricted(cls) -> "SecurityContext":
        """Restricted security context."""
        return cls(
            run_as_user=1000,
            run_as_group=1000,
            run_as_non_root=True,
            read_only_root_filesystem=True,
            allow_privilege_escalation=False,
            privileged=False,
            seccomp_profile="runtime/default"
        )


class AdvancedPermissionProfile(BaseModel):
    """Advanced permission profile with comprehensive security controls."""
    name: str
    description: Optional[str] = None
    security_level: SecurityLevel = SecurityLevel.STANDARD
    
    # Core permissions (backward compatibility)
    read_paths: List[str] = Field(default_factory=list)
    write_paths: List[str] = Field(default_factory=list)
    
    # Advanced controls
    resource_limits: Optional[ResourceLimit] = None
    capabilities: Optional[CapabilitySet] = None
    network_policy: Optional[NetworkPolicy] = None
    volume_policy: Optional[VolumePolicy] = None
    security_context: Optional[SecurityContext] = None
    
    # Environment controls
    allowed_env_vars: List[str] = Field(default_factory=list)
    blocked_env_vars: List[str] = Field(default_factory=list)
    env_var_patterns: List[str] = Field(default_factory=list)
    
    # Process controls
    allowed_commands: List[str] = Field(default_factory=list)
    blocked_commands: List[str] = Field(default_factory=list)
    shell_access: bool = False
    
    # Time-based controls
    max_runtime: Optional[str] = None  # e.g., "1h", "30m"
    allowed_time_windows: List[str] = Field(default_factory=list)
    
    # Audit and monitoring
    audit_level: str = "standard"  # minimal, standard, detailed
    log_all_commands: bool = False
    monitor_file_access: bool = False
    monitor_network_access: bool = False
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    version: str = "1.0"
    tags: List[str] = Field(default_factory=list)
    
    @classmethod
    def minimal(cls, name: str = "minimal") -> "AdvancedPermissionProfile":
        """Create minimal security profile."""
        return cls(
            name=name,
            description="Minimal security profile with maximum restrictions",
            security_level=SecurityLevel.MINIMAL,
            read_paths=["/app", "/tmp"],
            write_paths=["/tmp", "/app/tmp"],
            resource_limits=ResourceLimit(
                memory="128m",
                cpu_limit="0.1",
                pids_limit=10
            ),
            capabilities=CapabilitySet.minimal(),
            network_policy=NetworkPolicy.isolated(),
            volume_policy=VolumePolicy.minimal(),
            security_context=SecurityContext.minimal(),
            shell_access=False,
            max_runtime="5m",
            audit_level="detailed"
        )
    
    @classmethod
    def restricted(cls, name: str = "restricted") -> "AdvancedPermissionProfile":
        """Create restricted security profile."""
        return cls(
            name=name,
            description="Restricted security profile for untrusted applications",
            security_level=SecurityLevel.RESTRICTED,
            read_paths=["/app", "/etc/ssl", "/usr/share"],
            write_paths=["/tmp", "/app/data", "/app/logs"],
            resource_limits=ResourceLimit(
                memory="512m",
                cpu_limit="0.5",
                pids_limit=50
            ),
            capabilities=CapabilitySet.restricted(),
            network_policy=NetworkPolicy.restricted(),
            volume_policy=VolumePolicy.restricted(),
            security_context=SecurityContext.restricted(),
            blocked_env_vars=["PATH", "HOME", "USER"],
            shell_access=False,
            max_runtime="30m",
            audit_level="standard"
        )
    
    @classmethod
    def standard(cls, name: str = "standard") -> "AdvancedPermissionProfile":
        """Create standard security profile."""
        return cls(
            name=name,
            description="Standard security profile for typical applications",
            security_level=SecurityLevel.STANDARD,
            read_paths=["/app", "/etc", "/usr", "/lib", "/lib64"],
            write_paths=["/tmp", "/app/data", "/app/logs", "/app/cache"],
            resource_limits=ResourceLimit(
                memory="1g",
                cpu_limit="1.0",
                pids_limit=100
            ),
            capabilities=CapabilitySet.standard(),
            network_policy=NetworkPolicy(
                allow_localhost=True,
                allow_private_networks=True,
                allow_internet=True,
                blocked_ports=[22, 23]
            ),
            volume_policy=VolumePolicy(
                allowed_types=[VolumeType.VOLUME, VolumeType.TMPFS],
                read_only_enforced=False,
                allow_host_paths=False
            ),
            security_context=SecurityContext(
                run_as_non_root=True,
                read_only_root_filesystem=False,
                allow_privilege_escalation=False
            ),
            shell_access=True,
            max_runtime="2h",
            audit_level="standard"
        )
    
    @classmethod
    def privileged(cls, name: str = "privileged") -> "AdvancedPermissionProfile":
        """Create privileged security profile."""
        return cls(
            name=name,
            description="Privileged profile for trusted system applications",
            security_level=SecurityLevel.PRIVILEGED,
            read_paths=["/"],
            write_paths=["/tmp", "/app", "/var"],
            resource_limits=ResourceLimit(
                memory="4g",
                cpu_limit="2.0",
                pids_limit=1000
            ),
            capabilities=CapabilitySet(add=[], drop=[]),  # All capabilities
            network_policy=NetworkPolicy(
                mode=NetworkMode.HOST,
                allow_internet=True,
                allow_localhost=True,
                allow_private_networks=True
            ),
            volume_policy=VolumePolicy(
                allowed_types=list(VolumeType),
                allow_host_paths=True,
                allow_sensitive_paths=True,
                read_only_enforced=False
            ),
            security_context=SecurityContext(
                privileged=True,
                allow_privilege_escalation=True,
                read_only_root_filesystem=False
            ),
            shell_access=True,
            audit_level="minimal"
        )


class PermissionTemplate(BaseModel):
    """Template for creating permission profiles."""
    name: str
    description: Optional[str] = None
    base_profile: str  # Name of base profile to extend
    overrides: Dict[str, Any] = Field(default_factory=dict)
    use_cases: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    
    def apply_to_profile(self, profile: AdvancedPermissionProfile) -> AdvancedPermissionProfile:
        """Apply template overrides to a profile."""
        profile_dict = profile.model_dump()
        
        # Apply overrides
        for key, value in self.overrides.items():
            if "." in key:
                # Handle nested keys like "resource_limits.memory"
                keys = key.split(".")
                current = profile_dict
                for k in keys[:-1]:
                    if k not in current:
                        current[k] = {}
                    current = current[k]
                current[keys[-1]] = value
            else:
                profile_dict[key] = value
        
        return AdvancedPermissionProfile(**profile_dict)


# Predefined templates
PERMISSION_TEMPLATES = {
    "web-service": PermissionTemplate(
        name="web-service",
        description="Template for web service applications",
        base_profile="standard",
        overrides={
            "network_policy.allowed_ports": [80, 443, 8080, 8443],
            "network_policy.allow_internet": True,
            "read_paths": ["/app", "/etc/ssl", "/usr/share/zoneinfo"],
            "write_paths": ["/tmp", "/app/logs", "/app/cache"],
            "resource_limits.memory": "1g",
            "resource_limits.cpu_limit": "1.0"
        },
        use_cases=["HTTP APIs", "Web applications", "REST services"],
        tags=["web", "http", "api"]
    ),
    
    "database": PermissionTemplate(
        name="database",
        description="Template for database applications",
        base_profile="standard",
        overrides={
            "network_policy.allowed_ports": [3306, 5432, 27017, 6379],
            "network_policy.allow_internet": False,
            "write_paths": ["/var/lib/data", "/tmp", "/app/logs"],
            "resource_limits.memory": "2g",
            "resource_limits.cpu_limit": "2.0",
            "volume_policy.allowed_types": ["volume", "bind"],
            "max_runtime": None  # No time limit for databases
        },
        use_cases=["MySQL", "PostgreSQL", "MongoDB", "Redis"],
        tags=["database", "storage", "persistence"]
    ),
    
    "ml-workload": PermissionTemplate(
        name="ml-workload",
        description="Template for machine learning workloads",
        base_profile="standard",
        overrides={
            "resource_limits.memory": "8g",
            "resource_limits.cpu_limit": "4.0",
            "read_paths": ["/app", "/data", "/models", "/usr/local"],
            "write_paths": ["/tmp", "/app/output", "/app/checkpoints"],
            "network_policy.allow_internet": True,  # For downloading models
            "max_runtime": "24h"
        },
        use_cases=["TensorFlow", "PyTorch", "Scikit-learn", "Model training"],
        tags=["ml", "ai", "training", "gpu"]
    ),
    
    "ci-cd": PermissionTemplate(
        name="ci-cd",
        description="Template for CI/CD build processes",
        base_profile="standard",
        overrides={
            "network_policy.allow_internet": True,
            "shell_access": True,
            "read_paths": ["/", "/usr", "/lib", "/bin"],
            "write_paths": ["/tmp", "/build", "/app"],
            "resource_limits.memory": "4g",
            "resource_limits.cpu_limit": "2.0",
            "max_runtime": "2h",
            "audit_level": "detailed"
        },
        use_cases=["Build processes", "Testing", "Deployment", "Package creation"],
        tags=["ci", "cd", "build", "test"]
    ),
    
    "sandbox": PermissionTemplate(
        name="sandbox",
        description="Template for sandboxed execution",
        base_profile="minimal",
        overrides={
            "max_runtime": "10m",
            "resource_limits.memory": "64m",
            "resource_limits.cpu_limit": "0.1",
            "audit_level": "detailed",
            "log_all_commands": True,
            "monitor_file_access": True,
            "monitor_network_access": True
        },
        use_cases=["Code execution", "User-submitted code", "Untrusted workloads"],
        tags=["sandbox", "untrusted", "execution", "security"]
    )
}