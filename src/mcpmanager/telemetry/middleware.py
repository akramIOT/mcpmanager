"""Telemetry middleware for API and transport layers."""

import logging
import time
from typing import Dict, Any, Callable, Optional
from functools import wraps

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)


class TelemetryMiddleware:
    """Middleware for automatic telemetry instrumentation."""

    def __init__(self, telemetry_manager):
        """Initialize telemetry middleware."""
        self.telemetry_manager = telemetry_manager
        self.tracer = telemetry_manager.get_tracer("mcpmanager.middleware")
        self.metrics = None
        
        # Initialize metrics if available
        try:
            from .metrics import MetricsCollector
            self.metrics = MetricsCollector(telemetry_manager)
        except Exception as e:
            logger.warning(f"Failed to initialize metrics collector: {e}")

    def instrument_fastapi_app(self, app):
        """Instrument FastAPI application with telemetry."""
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=self.telemetry_manager.tracer_provider,
                meter_provider=self.telemetry_manager.meter_provider
            )
            logger.info("FastAPI application instrumented with telemetry")
        except ImportError:
            logger.warning("FastAPI instrumentation not available")
        except Exception as e:
            logger.warning(f"Failed to instrument FastAPI app: {e}")

    def instrument_httpx_client(self):
        """Instrument HTTPX client for outbound requests."""
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
            HTTPXClientInstrumentor().instrument()
            logger.info("HTTPX client instrumented with telemetry")
        except ImportError:
            logger.warning("HTTPX instrumentation not available")
        except Exception as e:
            logger.warning(f"Failed to instrument HTTPX client: {e}")

    def trace_async_function(self, span_name: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None):
        """Decorator to trace async functions."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                if not self.telemetry_manager.is_enabled():
                    return await func(*args, **kwargs)
                
                name = span_name or f"{func.__module__}.{func.__qualname__}"
                
                with self.tracer.start_as_current_span(name) as span:
                    try:
                        # Add function metadata
                        span.set_attribute("function.name", func.__name__)
                        span.set_attribute("function.module", func.__module__)
                        
                        # Add custom attributes
                        if attributes:
                            for key, value in attributes.items():
                                span.set_attribute(key, value)
                        
                        # Add simple arguments
                        for i, arg in enumerate(args):
                            if isinstance(arg, (str, int, float, bool)):
                                span.set_attribute(f"args.{i}", str(arg))
                        
                        for key, value in kwargs.items():
                            if isinstance(value, (str, int, float, bool)):
                                span.set_attribute(f"kwargs.{key}", str(value))
                        
                        result = await func(*args, **kwargs)
                        
                        # Mark span as successful
                        span.set_status(Status(StatusCode.OK))
                        
                        return result
                        
                    except Exception as e:
                        # Record exception and mark span as error
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
            
            return wrapper
        return decorator

    def trace_sync_function(self, span_name: Optional[str] = None, attributes: Optional[Dict[str, Any]] = None):
        """Decorator to trace synchronous functions."""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not self.telemetry_manager.is_enabled():
                    return func(*args, **kwargs)
                
                name = span_name or f"{func.__module__}.{func.__qualname__}"
                
                with self.tracer.start_as_current_span(name) as span:
                    try:
                        # Add function metadata
                        span.set_attribute("function.name", func.__name__)
                        span.set_attribute("function.module", func.__module__)
                        
                        # Add custom attributes
                        if attributes:
                            for key, value in attributes.items():
                                span.set_attribute(key, value)
                        
                        # Add simple arguments
                        for i, arg in enumerate(args):
                            if isinstance(arg, (str, int, float, bool)):
                                span.set_attribute(f"args.{i}", str(arg))
                        
                        for key, value in kwargs.items():
                            if isinstance(value, (str, int, float, bool)):
                                span.set_attribute(f"kwargs.{key}", str(value))
                        
                        result = func(*args, **kwargs)
                        
                        # Mark span as successful
                        span.set_status(Status(StatusCode.OK))
                        
                        return result
                        
                    except Exception as e:
                        # Record exception and mark span as error
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
            
            return wrapper
        return decorator

    def create_request_middleware(self):
        """Create middleware for HTTP requests."""
        async def middleware(request, call_next):
            if not self.telemetry_manager.is_enabled():
                return await call_next(request)
            
            start_time = time.time()
            
            # Extract trace context from headers
            try:
                from opentelemetry.propagate import extract
                extract(dict(request.headers))
            except Exception as e:
                logger.debug(f"Failed to extract trace context: {e}")
            
            # Create span for request
            with self.tracer.start_as_current_span(
                f"{request.method} {request.url.path}"
            ) as span:
                try:
                    # Add request attributes
                    span.set_attribute("http.method", request.method)
                    span.set_attribute("http.url", str(request.url))
                    span.set_attribute("http.scheme", request.url.scheme)
                    span.set_attribute("http.host", request.url.hostname or "unknown")
                    span.set_attribute("http.target", request.url.path)
                    
                    if request.url.query:
                        span.set_attribute("http.query", request.url.query)
                    
                    # Add user agent if available
                    user_agent = request.headers.get("user-agent")
                    if user_agent:
                        span.set_attribute("http.user_agent", user_agent)
                    
                    # Process request
                    response = await call_next(request)
                    
                    # Add response attributes
                    span.set_attribute("http.status_code", response.status_code)
                    span.set_attribute("http.response_size", len(response.body) if hasattr(response, 'body') else 0)
                    
                    # Record metrics
                    if self.metrics:
                        duration = time.time() - start_time
                        with self.metrics.time_api_request(request.method, request.url.path):
                            pass
                    
                    # Set span status based on response
                    if response.status_code >= 400:
                        span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                    else:
                        span.set_status(Status(StatusCode.OK))
                    
                    return response
                    
                except Exception as e:
                    # Record exception
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    
                    # Record metrics
                    if self.metrics:
                        with self.metrics.time_api_request(request.method, request.url.path):
                            pass
                    
                    raise
        
        return middleware

    def instrument_transport_layer(self, transport_class):
        """Instrument transport layer with telemetry."""
        original_start = transport_class.start
        original_stop = transport_class.stop
        
        @wraps(original_start)
        async def traced_start(self, *args, **kwargs):
            if not self.telemetry_manager.is_enabled():
                return await original_start(self, *args, **kwargs)
            
            transport_type = getattr(self, 'transport_type', 'unknown')
            
            with self.tracer.start_as_current_span(f"transport.start") as span:
                span.set_attribute("mcpmanager.transport.type", transport_type)
                span.set_attribute("mcpmanager.operation", "start")
                
                try:
                    result = await original_start(self, *args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    
                    # Record metrics
                    if self.metrics:
                        self.metrics.record_transport_connection(transport_type, True)
                    
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    
                    # Record metrics
                    if self.metrics:
                        self.metrics.record_transport_connection(transport_type, False)
                    
                    raise
        
        @wraps(original_stop)
        async def traced_stop(self, *args, **kwargs):
            if not self.telemetry_manager.is_enabled():
                return await original_stop(self, *args, **kwargs)
            
            transport_type = getattr(self, 'transport_type', 'unknown')
            
            with self.tracer.start_as_current_span(f"transport.stop") as span:
                span.set_attribute("mcpmanager.transport.type", transport_type)
                span.set_attribute("mcpmanager.operation", "stop")
                
                try:
                    result = await original_stop(self, *args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
        
        # Replace methods
        transport_class.start = traced_start
        transport_class.stop = traced_stop
        
        logger.debug(f"Instrumented transport class: {transport_class.__name__}")

    def add_correlation_id_middleware(self):
        """Create middleware to add correlation IDs."""
        async def middleware(request, call_next):
            # Generate or extract correlation ID
            correlation_id = request.headers.get("x-correlation-id")
            if not correlation_id:
                import uuid
                correlation_id = str(uuid.uuid4())
            
            # Add to current span
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                current_span.set_attribute("correlation.id", correlation_id)
            
            # Process request
            response = await call_next(request)
            
            # Add correlation ID to response
            response.headers["x-correlation-id"] = correlation_id
            
            return response
        
        return middleware

    def instrument_database_operations(self, db_class):
        """Instrument database operations with telemetry."""
        # This would be implemented based on the specific database library used
        # For example, SQLAlchemy, asyncpg, etc.
        logger.debug(f"Database instrumentation requested for: {db_class.__name__}")

    def create_error_tracking_middleware(self):
        """Create middleware for error tracking."""
        async def middleware(request, call_next):
            try:
                return await call_next(request)
            except Exception as e:
                # Add error context to current span
                current_span = trace.get_current_span()
                if current_span and current_span.is_recording():
                    current_span.record_exception(e)
                    current_span.set_attribute("error.type", type(e).__name__)
                    current_span.set_attribute("error.message", str(e))
                    current_span.set_status(Status(StatusCode.ERROR, str(e)))
                
                # Log error with trace context
                trace_id = None
                span_id = None
                if current_span and current_span.is_recording():
                    context = current_span.get_span_context()
                    trace_id = f"{context.trace_id:032x}"
                    span_id = f"{context.span_id:016x}"
                
                logger.error(
                    f"Request failed: {e}",
                    extra={
                        "trace_id": trace_id,
                        "span_id": span_id,
                        "url": str(request.url),
                        "method": request.method
                    }
                )
                
                raise
        
        return middleware

    def get_middleware_summary(self) -> Dict[str, Any]:
        """Get middleware configuration summary."""
        return {
            "enabled": self.telemetry_manager.is_enabled(),
            "tracer_name": self.tracer.instrumentation_scope.name if hasattr(self.tracer, 'instrumentation_scope') else "unknown",
            "metrics_enabled": self.metrics is not None,
            "instrumented_components": [
                "request_middleware",
                "correlation_middleware", 
                "error_tracking_middleware"
            ]
        }