"""Distributed tracing support for MCPManager."""

import logging
from typing import Dict, Any, Optional, Callable
from functools import wraps
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)


class TracingManager:
    """Manager for distributed tracing operations."""

    def __init__(self, telemetry_manager):
        """Initialize tracing manager."""
        self.telemetry_manager = telemetry_manager
        self.tracer = telemetry_manager.get_tracer("mcpmanager.tracing")

    @contextmanager
    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Start a new span with context management."""
        span = self.tracer.start_span(name)
        
        try:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            
            with trace.use_span(span, end_on_exit=False):
                yield span
            
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
        finally:
            span.end()

    def trace_method(self, span_name: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None):
        """Decorator to trace method calls."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                name = span_name or f"{func.__module__}.{func.__qualname__}"
                
                with self.start_span(name, attributes) as span:
                    # Add method info to span
                    span.set_attribute("method.name", func.__name__)
                    span.set_attribute("method.module", func.__module__)
                    
                    # Add arguments if they're simple types
                    for i, arg in enumerate(args[1:], 1):  # Skip 'self'
                        if isinstance(arg, (str, int, float, bool)):
                            span.set_attribute(f"method.arg.{i}", str(arg))
                    
                    for key, value in kwargs.items():
                        if isinstance(value, (str, int, float, bool)):
                            span.set_attribute(f"method.kwarg.{key}", str(value))
                    
                    result = await func(*args, **kwargs)
                    
                    # Add result info if it's a simple type
                    if isinstance(result, (str, int, float, bool)):
                        span.set_attribute("method.result", str(result))
                    
                    return result
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                name = span_name or f"{func.__module__}.{func.__qualname__}"
                
                with self.start_span(name, attributes) as span:
                    # Add method info to span
                    span.set_attribute("method.name", func.__name__)
                    span.set_attribute("method.module", func.__module__)
                    
                    # Add arguments if they're simple types
                    for i, arg in enumerate(args[1:], 1):  # Skip 'self'
                        if isinstance(arg, (str, int, float, bool)):
                            span.set_attribute(f"method.arg.{i}", str(arg))
                    
                    for key, value in kwargs.items():
                        if isinstance(value, (str, int, float, bool)):
                            span.set_attribute(f"method.kwarg.{key}", str(value))
                    
                    result = func(*args, **kwargs)
                    
                    # Add result info if it's a simple type
                    if isinstance(result, (str, int, float, bool)):
                        span.set_attribute("method.result", str(result))
                    
                    return result
            
            # Return appropriate wrapper based on function type
            if hasattr(func, '__code__') and func.__code__.co_flags & 0x80:  # CO_COROUTINE
                return async_wrapper
            else:
                return sync_wrapper
        
        return decorator

    def trace_server_lifecycle(self, operation: str, server_name: str):
        """Create span for server lifecycle operations."""
        attributes = {
            "mcpmanager.operation": operation,
            "mcpmanager.server.name": server_name,
            "mcpmanager.component": "server_manager"
        }
        return self.start_span(f"mcpmanager.server.{operation}", attributes)

    def trace_container_operation(self, operation: str, image: str, runtime: str):
        """Create span for container operations."""
        attributes = {
            "mcpmanager.operation": operation,
            "mcpmanager.container.image": image,
            "mcpmanager.container.runtime": runtime,
            "mcpmanager.component": "container_manager"
        }
        return self.start_span(f"mcpmanager.container.{operation}", attributes)

    def trace_image_verification(self, image: str):
        """Create span for image verification."""
        attributes = {
            "mcpmanager.operation": "verify",
            "mcpmanager.image": image,
            "mcpmanager.component": "image_verifier"
        }
        return self.start_span("mcpmanager.image.verify", attributes)

    def trace_permission_check(self, profile_name: str):
        """Create span for permission checking."""
        attributes = {
            "mcpmanager.operation": "validate",
            "mcpmanager.permission.profile": profile_name,
            "mcpmanager.component": "permission_manager"
        }
        return self.start_span("mcpmanager.permission.validate", attributes)

    def trace_transport_connection(self, transport_type: str, target: str):
        """Create span for transport connections."""
        attributes = {
            "mcpmanager.operation": "connect",
            "mcpmanager.transport.type": transport_type,
            "mcpmanager.transport.target": target,
            "mcpmanager.component": "transport_factory"
        }
        return self.start_span("mcpmanager.transport.connect", attributes)

    def trace_registry_lookup(self, server_name: str, registry_type: str):
        """Create span for registry lookups."""
        attributes = {
            "mcpmanager.operation": "lookup",
            "mcpmanager.server.name": server_name,
            "mcpmanager.registry.type": registry_type,
            "mcpmanager.component": "registry"
        }
        return self.start_span("mcpmanager.registry.lookup", attributes)

    def trace_secret_retrieval(self, secret_name: str, provider: str):
        """Create span for secret retrieval."""
        attributes = {
            "mcpmanager.operation": "retrieve",
            "mcpmanager.secret.name": secret_name,
            "mcpmanager.secret.provider": provider,
            "mcpmanager.component": "secrets_manager"
        }
        return self.start_span("mcpmanager.secret.retrieve", attributes)

    def trace_api_request(self, method: str, endpoint: str):
        """Create span for API requests."""
        attributes = {
            "http.method": method,
            "http.route": endpoint,
            "mcpmanager.component": "api_server"
        }
        return self.start_span(f"HTTP {method} {endpoint}", attributes)

    def add_server_context(self, span: trace.Span, server_name: str, config: Dict[str, Any]) -> None:
        """Add server context to span."""
        try:
            span.set_attribute("mcpmanager.server.name", server_name)
            span.set_attribute("mcpmanager.server.image", config.get("image", "unknown"))
            span.set_attribute("mcpmanager.server.transport", config.get("transport", "unknown"))
            
            if config.get("port"):
                span.set_attribute("mcpmanager.server.port", config["port"])
        except Exception as e:
            logger.warning(f"Failed to add server context to span: {e}")

    def add_container_context(self, span: trace.Span, container_id: str, image: str) -> None:
        """Add container context to span."""
        try:
            span.set_attribute("mcpmanager.container.id", container_id)
            span.set_attribute("mcpmanager.container.image", image)
        except Exception as e:
            logger.warning(f"Failed to add container context to span: {e}")

    def add_error_context(self, span: trace.Span, error: Exception) -> None:
        """Add error context to span."""
        try:
            span.record_exception(error)
            span.set_attribute("error.type", type(error).__name__)
            span.set_attribute("error.message", str(error))
            span.set_status(Status(StatusCode.ERROR, str(error)))
        except Exception as e:
            logger.warning(f"Failed to add error context to span: {e}")

    def add_custom_attributes(self, span: trace.Span, attributes: Dict[str, Any]) -> None:
        """Add custom attributes to span."""
        try:
            for key, value in attributes.items():
                # Convert complex objects to strings
                if isinstance(value, (dict, list)):
                    value = str(value)
                elif not isinstance(value, (str, int, float, bool)):
                    value = str(value)
                
                span.set_attribute(key, value)
        except Exception as e:
            logger.warning(f"Failed to add custom attributes to span: {e}")

    def get_current_trace_id(self) -> Optional[str]:
        """Get current trace ID for correlation."""
        try:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                trace_id = current_span.get_span_context().trace_id
                return f"{trace_id:032x}"
            return None
        except Exception as e:
            logger.warning(f"Failed to get current trace ID: {e}")
            return None

    def get_current_span_id(self) -> Optional[str]:
        """Get current span ID for correlation."""
        try:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                span_id = current_span.get_span_context().span_id
                return f"{span_id:016x}"
            return None
        except Exception as e:
            logger.warning(f"Failed to get current span ID: {e}")
            return None

    def inject_trace_headers(self) -> Dict[str, str]:
        """Inject trace context into headers for propagation."""
        try:
            from opentelemetry.propagate import inject
            headers = {}
            inject(headers)
            return headers
        except Exception as e:
            logger.warning(f"Failed to inject trace headers: {e}")
            return {}

    def extract_trace_context(self, headers: Dict[str, str]) -> None:
        """Extract trace context from headers."""
        try:
            from opentelemetry.propagate import extract
            extract(headers)
        except Exception as e:
            logger.warning(f"Failed to extract trace context: {e}")

    def create_child_span(self, parent_span: trace.Span, name: str, attributes: Optional[Dict[str, Any]] = None) -> trace.Span:
        """Create a child span from a parent span."""
        try:
            with trace.use_span(parent_span):
                child_span = self.tracer.start_span(name)
                
                if attributes:
                    self.add_custom_attributes(child_span, attributes)
                
                return child_span
        except Exception as e:
            logger.warning(f"Failed to create child span: {e}")
            return trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)

    def is_enabled(self) -> bool:
        """Check if tracing is enabled."""
        return self.telemetry_manager.is_enabled()

    def get_tracing_summary(self) -> Dict[str, Any]:
        """Get tracing configuration summary."""
        current_span = trace.get_current_span()
        return {
            "enabled": self.is_enabled(),
            "current_trace_id": self.get_current_trace_id(),
            "current_span_id": self.get_current_span_id(),
            "current_span_recording": current_span.is_recording() if current_span else False,
            "tracer_name": self.tracer.instrumentation_scope.name if hasattr(self.tracer, 'instrumentation_scope') else "unknown"
        }