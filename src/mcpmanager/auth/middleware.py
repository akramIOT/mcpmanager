"""Authentication and authorization middleware."""

import logging
from typing import Optional, Dict, Any, Callable, Awaitable
from abc import ABC, abstractmethod

from mcpmanager.core.models import OIDCConfig

logger = logging.getLogger(__name__)


class AuthMiddleware(ABC):
    """Abstract base class for authentication middleware."""

    @abstractmethod
    async def authenticate(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Authenticate a request and return user context if successful."""
        pass

    @abstractmethod
    async def authorize(self, user_context: Dict[str, Any], resource: str, action: str) -> bool:
        """Authorize a user action on a resource."""
        pass


class AnonymousAuth(AuthMiddleware):
    """Anonymous authentication - allows all requests."""

    async def authenticate(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Allow anonymous access."""
        return {"user": "anonymous", "authenticated": False}

    async def authorize(self, user_context: Dict[str, Any], resource: str, action: str) -> bool:
        """Allow all actions for anonymous users."""
        return True


class LocalAuth(AuthMiddleware):
    """Local authentication - validates against local configuration."""

    def __init__(self, allowed_users: Optional[Dict[str, str]] = None):
        """Initialize with allowed users (username -> password hash)."""
        self.allowed_users = allowed_users or {}

    async def authenticate(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Authenticate using local user database."""
        username = request_data.get("username")
        password = request_data.get("password")

        if not username or not password:
            return None

        # In a real implementation, you would hash the password and compare
        # For now, this is a simple example
        if username in self.allowed_users:
            stored_password = self.allowed_users[username]
            if password == stored_password:  # Simple comparison for demo
                return {
                    "user": username,
                    "authenticated": True,
                    "roles": ["user"],
                }

        return None

    async def authorize(self, user_context: Dict[str, Any], resource: str, action: str) -> bool:
        """Authorize based on user roles."""
        if not user_context.get("authenticated"):
            return False

        # Simple role-based authorization
        roles = user_context.get("roles", [])
        
        # Admin users can do everything
        if "admin" in roles:
            return True

        # Regular users can read but not modify
        if "user" in roles:
            return action in ["read", "list", "get"]

        return False


class OIDCAuth(AuthMiddleware):
    """OIDC authentication middleware."""

    def __init__(self, config: OIDCConfig):
        """Initialize OIDC authentication."""
        self.config = config
        self._client = None

    async def _get_oidc_client(self):
        """Get or create OIDC client."""
        if self._client is None:
            try:
                from authlib.integrations.httpx_client import AsyncOAuth2Client
                
                self._client = AsyncOAuth2Client(
                    client_id=self.config.client_id,
                    client_secret=self.config.client_secret,
                )
                
                # Discover endpoints
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self.config.issuer_url}/.well-known/openid-configuration")
                    response.raise_for_status()
                    self._discovery = response.json()
                    
            except ImportError:
                logger.error("OIDC authentication requires 'authlib' package. Install with: pip install authlib")
                raise
            except Exception as e:
                logger.error(f"Failed to initialize OIDC client: {e}")
                raise

        return self._client

    async def authenticate(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Authenticate using OIDC token."""
        token = request_data.get("authorization")
        if not token:
            return None

        # Remove "Bearer " prefix if present
        if token.startswith("Bearer "):
            token = token[7:]

        try:
            client = await self._get_oidc_client()
            
            # Validate token with OIDC provider
            import httpx
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get(
                    self._discovery["userinfo_endpoint"],
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code == 200:
                    user_info = response.json()
                    return {
                        "user": user_info.get("sub"),
                        "email": user_info.get("email"),
                        "name": user_info.get("name"),
                        "authenticated": True,
                        "token": token,
                        "user_info": user_info,
                    }
                else:
                    logger.warning(f"Token validation failed: {response.status_code}")
                    return None

        except Exception as e:
            logger.error(f"OIDC authentication failed: {e}")
            return None

    async def authorize(self, user_context: Dict[str, Any], resource: str, action: str) -> bool:
        """Authorize based on OIDC claims."""
        if not user_context.get("authenticated"):
            return False

        # Extract groups/roles from token claims
        user_info = user_context.get("user_info", {})
        groups = user_info.get("groups", [])
        roles = user_info.get("roles", [])

        # Check for admin permissions
        if "admin" in groups or "admin" in roles:
            return True

        # Check for resource-specific permissions
        if f"{resource}:{action}" in groups or f"{resource}:{action}" in roles:
            return True

        # Default to read-only for authenticated users
        if action in ["read", "list", "get"]:
            return True

        return False


class AuthMiddlewareFactory:
    """Factory for creating authentication middleware."""

    @staticmethod
    def create_anonymous() -> AuthMiddleware:
        """Create anonymous authentication middleware."""
        return AnonymousAuth()

    @staticmethod
    def create_local(allowed_users: Optional[Dict[str, str]] = None) -> AuthMiddleware:
        """Create local authentication middleware."""
        return LocalAuth(allowed_users)

    @staticmethod
    def create_oidc(config: OIDCConfig) -> AuthMiddleware:
        """Create OIDC authentication middleware."""
        return OIDCAuth(config)


class AuthenticationError(Exception):
    """Authentication error."""
    pass


class AuthorizationError(Exception):
    """Authorization error."""
    pass


async def auth_middleware_wrapper(
    middleware: AuthMiddleware,
    handler: Callable[[Dict[str, Any]], Awaitable[Any]]
) -> Callable[[Dict[str, Any]], Awaitable[Any]]:
    """Wrap a handler with authentication middleware."""
    
    async def wrapped_handler(request_data: Dict[str, Any]) -> Any:
        # Authenticate the request
        user_context = await middleware.authenticate(request_data)
        if user_context is None:
            raise AuthenticationError("Authentication failed")

        # Add user context to request
        request_data["user_context"] = user_context

        # Call the original handler
        return await handler(request_data)

    return wrapped_handler


async def authz_middleware_wrapper(
    middleware: AuthMiddleware,
    resource: str,
    action: str,
    handler: Callable[[Dict[str, Any]], Awaitable[Any]]
) -> Callable[[Dict[str, Any]], Awaitable[Any]]:
    """Wrap a handler with authorization middleware."""
    
    async def wrapped_handler(request_data: Dict[str, Any]) -> Any:
        # Get user context from request
        user_context = request_data.get("user_context")
        if user_context is None:
            raise AuthenticationError("No user context found")

        # Authorize the action
        authorized = await middleware.authorize(user_context, resource, action)
        if not authorized:
            raise AuthorizationError(f"Access denied to {action} on {resource}")

        # Call the original handler
        return await handler(request_data)

    return wrapped_handler