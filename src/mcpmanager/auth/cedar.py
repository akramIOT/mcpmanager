"""Cedar-based authorization system."""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class CedarAuthz:
    """Cedar-based authorization system."""

    def __init__(self, policy_file: Optional[str] = None, entities_file: Optional[str] = None):
        """Initialize Cedar authorization."""
        self.policy_file = policy_file
        self.entities_file = entities_file
        self._policies: List[str] = []
        self._entities: Dict[str, Any] = {}
        
    async def initialize(self) -> None:
        """Initialize the authorization system."""
        if self.policy_file:
            await self._load_policies()
        if self.entities_file:
            await self._load_entities()

    async def _load_policies(self) -> None:
        """Load Cedar policies from file."""
        try:
            policy_path = Path(self.policy_file)
            if policy_path.exists():
                with open(policy_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Simple policy parsing - in real implementation use Cedar SDK
                # For now, assume policies are stored as JSON array
                if policy_path.suffix.lower() == '.json':
                    policies_data = json.loads(content)
                    self._policies = policies_data.get("policies", [])
                else:
                    # Cedar policy file
                    self._policies = [content]
                
                logger.info(f"Loaded {len(self._policies)} policies from {self.policy_file}")
        except Exception as e:
            logger.error(f"Failed to load policies: {e}")
            raise

    async def _load_entities(self) -> None:
        """Load entities from file."""
        try:
            entities_path = Path(self.entities_file)
            if entities_path.exists():
                with open(entities_path, 'r', encoding='utf-8') as f:
                    self._entities = json.load(f)
                
                logger.info(f"Loaded entities from {self.entities_file}")
        except Exception as e:
            logger.error(f"Failed to load entities: {e}")
            raise

    async def authorize(
        self,
        principal: Dict[str, Any],
        action: str,
        resource: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Authorize a request using Cedar policies."""
        try:
            # Create authorization request
            auth_request = {
                "principal": principal,
                "action": {"type": "Action", "id": action},
                "resource": resource,
                "context": context or {},
            }

            # Evaluate policies (simplified implementation)
            # In real implementation, use Cedar evaluation engine
            return await self._evaluate_policies(auth_request)

        except Exception as e:
            logger.error(f"Authorization failed: {e}")
            return False

    async def _evaluate_policies(self, request: Dict[str, Any]) -> bool:
        """Evaluate policies against the request."""
        # Simplified policy evaluation
        # In real implementation, use Cedar SDK
        
        principal = request["principal"]
        action_id = request["action"]["id"]
        resource = request["resource"]
        context = request["context"]

        # Default policies for demo
        default_policies = [
            # Admin users can do everything
            {
                "effect": "permit",
                "conditions": [
                    {"principal.type": "User"},
                    {"principal.role": "admin"}
                ]
            },
            # Users can read their own resources
            {
                "effect": "permit",
                "conditions": [
                    {"principal.type": "User"},
                    {"action": "read"},
                    {"principal.id": "resource.owner"}
                ]
            },
            # Users can list public resources
            {
                "effect": "permit",
                "conditions": [
                    {"principal.type": "User"},
                    {"action": "list"},
                    {"resource.visibility": "public"}
                ]
            }
        ]

        # Evaluate each policy
        for policy in default_policies:
            if await self._match_policy(policy, request):
                if policy["effect"] == "permit":
                    return True
                elif policy["effect"] == "forbid":
                    return False

        # Default deny
        return False

    async def _match_policy(self, policy: Dict[str, Any], request: Dict[str, Any]) -> bool:
        """Check if a policy matches the request."""
        conditions = policy.get("conditions", [])
        
        for condition in conditions:
            for key, expected_value in condition.items():
                if not await self._evaluate_condition(key, expected_value, request):
                    return False
        
        return True

    async def _evaluate_condition(self, key: str, expected_value: Any, request: Dict[str, Any]) -> bool:
        """Evaluate a single condition."""
        try:
            # Parse dotted key notation
            parts = key.split(".")
            current = request
            
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return False
            
            return current == expected_value
        except Exception:
            return False

    def create_principal(self, user_type: str, user_id: str, **attributes) -> Dict[str, Any]:
        """Create a principal entity."""
        return {
            "type": user_type,
            "id": user_id,
            **attributes
        }

    def create_resource(self, resource_type: str, resource_id: str, **attributes) -> Dict[str, Any]:
        """Create a resource entity."""
        return {
            "type": resource_type,
            "id": resource_id,
            **attributes
        }

    async def get_permitted_actions(
        self,
        principal: Dict[str, Any],
        resource: Dict[str, Any],
        actions: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Get list of permitted actions for a principal on a resource."""
        permitted = []
        
        for action in actions:
            if await self.authorize(principal, action, resource, context):
                permitted.append(action)
        
        return permitted

    async def filter_resources(
        self,
        principal: Dict[str, Any],
        action: str,
        resources: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Filter resources based on authorization."""
        permitted_resources = []
        
        for resource in resources:
            if await self.authorize(principal, action, resource, context):
                permitted_resources.append(resource)
        
        return permitted_resources


class CedarMiddleware:
    """Cedar authorization middleware for MCP requests."""

    def __init__(self, cedar_authz: CedarAuthz):
        """Initialize middleware with Cedar authorization."""
        self.cedar_authz = cedar_authz

    async def process_request(
        self,
        user_context: Dict[str, Any],
        resource_type: str,
        resource_id: str,
        action: str,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Process authorization request."""
        # Create principal from user context
        principal = self.cedar_authz.create_principal(
            user_type="User",
            user_id=user_context.get("user", "anonymous"),
            role=user_context.get("role", "user"),
            **user_context
        )

        # Create resource
        resource = self.cedar_authz.create_resource(
            resource_type=resource_type,
            resource_id=resource_id,
        )

        # Authorize
        return await self.cedar_authz.authorize(principal, action, resource, context)

    async def filter_mcp_servers(
        self,
        user_context: Dict[str, Any],
        servers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter MCP servers based on user permissions."""
        principal = self.cedar_authz.create_principal(
            user_type="User",
            user_id=user_context.get("user", "anonymous"),
            role=user_context.get("role", "user"),
            **user_context
        )

        # Convert servers to resource format
        resources = []
        for server in servers:
            resource = self.cedar_authz.create_resource(
                resource_type="MCPServer",
                resource_id=server.get("name", "unknown"),
                **server
            )
            resources.append(resource)

        # Filter based on "read" permission
        permitted_resources = await self.cedar_authz.filter_resources(
            principal, "read", resources
        )

        # Convert back to server format
        permitted_servers = []
        for i, resource in enumerate(resources):
            if resource in permitted_resources:
                permitted_servers.append(servers[i])

        return permitted_servers