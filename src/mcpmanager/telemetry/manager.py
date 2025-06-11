"""OpenTelemetry telemetry management."""

import logging
import os
from typing import Dict, List, Optional, Any
from pathlib import Path

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor

from mcpmanager.core.models import TelemetryConfig

logger = logging.getLogger(__name__)


class TelemetryManager:
    """OpenTelemetry telemetry manager."""

    def __init__(self, config: Optional[TelemetryConfig] = None):
        """Initialize telemetry manager."""
        self.config = config or TelemetryConfig()
        self.tracer_provider: Optional[TracerProvider] = None
        self.meter_provider: Optional[MeterProvider] = None
        self.tracer = None
        self.meter = None
        self._initialized = False
        self._instrumentors = []

    async def initialize(self) -> None:
        """Initialize OpenTelemetry instrumentation."""
        if not self.config.enabled:
            logger.info("Telemetry disabled")
            return

        try:
            # Set up resource
            resource = Resource.create({
                SERVICE_NAME: "mcpmanager",
                SERVICE_VERSION: "1.0.0",
                "service.instance.id": os.getenv("HOSTNAME", "unknown"),
                "deployment.environment": os.getenv("ENVIRONMENT", "development"),
            })

            # Initialize tracing
            await self._initialize_tracing(resource)
            
            # Initialize metrics
            await self._initialize_metrics(resource)
            
            # Set up auto-instrumentation
            await self._setup_auto_instrumentation()
            
            self._initialized = True
            logger.info("OpenTelemetry telemetry initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize telemetry: {e}")
            # Don't fail the application if telemetry fails
            self.config.enabled = False

    async def _initialize_tracing(self, resource: Resource) -> None:
        """Initialize tracing with configured exporters."""
        # Create tracer provider
        self.tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(self.tracer_provider)

        # Add span processors based on configuration
        processors = []

        # OTLP exporter
        if self.config.endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=f"{self.config.endpoint}/v1/traces",
                    headers=self._get_auth_headers()
                )
                processors.append(BatchSpanProcessor(otlp_exporter))
                logger.info(f"Added OTLP trace exporter: {self.config.endpoint}")
            except Exception as e:
                logger.warning(f"Failed to create OTLP trace exporter: {e}")

        # Jaeger exporter
        jaeger_endpoint = os.getenv("JAEGER_ENDPOINT")
        if jaeger_endpoint:
            try:
                jaeger_exporter = JaegerExporter(
                    agent_host_name=jaeger_endpoint.split(":")[0],
                    agent_port=int(jaeger_endpoint.split(":")[1]) if ":" in jaeger_endpoint else 14268,
                )
                processors.append(BatchSpanProcessor(jaeger_exporter))
                logger.info(f"Added Jaeger trace exporter: {jaeger_endpoint}")
            except Exception as e:
                logger.warning(f"Failed to create Jaeger trace exporter: {e}")

        # Console exporter for development
        if os.getenv("OTEL_TRACES_CONSOLE", "false").lower() == "true":
            processors.append(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("Added console trace exporter")

        # Add processors to tracer provider
        for processor in processors:
            self.tracer_provider.add_span_processor(processor)

        # Create tracer
        self.tracer = trace.get_tracer(__name__)

    async def _initialize_metrics(self, resource: Resource) -> None:
        """Initialize metrics with configured exporters."""
        readers = []

        # OTLP metrics exporter
        if self.config.endpoint:
            try:
                otlp_metric_exporter = OTLPMetricExporter(
                    endpoint=f"{self.config.endpoint}/v1/metrics",
                    headers=self._get_auth_headers()
                )
                readers.append(PeriodicExportingMetricReader(otlp_metric_exporter))
                logger.info(f"Added OTLP metrics exporter: {self.config.endpoint}")
            except Exception as e:
                logger.warning(f"Failed to create OTLP metrics exporter: {e}")

        # Prometheus metrics exporter
        if self.config.enable_prometheus_metrics:
            try:
                prometheus_reader = PrometheusMetricReader()
                readers.append(prometheus_reader)
                logger.info("Added Prometheus metrics exporter")
            except Exception as e:
                logger.warning(f"Failed to create Prometheus metrics exporter: {e}")

        # Console exporter for development
        if os.getenv("OTEL_METRICS_CONSOLE", "false").lower() == "true":
            readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter()))
            logger.info("Added console metrics exporter")

        # Create meter provider
        self.meter_provider = MeterProvider(resource=resource, metric_readers=readers)
        metrics.set_meter_provider(self.meter_provider)

        # Create meter
        self.meter = metrics.get_meter(__name__)

    async def _setup_auto_instrumentation(self) -> None:
        """Set up automatic instrumentation for common libraries."""
        try:
            # Instrument logging
            logging_instrumentor = LoggingInstrumentor()
            logging_instrumentor.instrument(set_logging_format=True)
            self._instrumentors.append(logging_instrumentor)

            # Instrument HTTP requests
            requests_instrumentor = RequestsInstrumentor()
            requests_instrumentor.instrument()
            self._instrumentors.append(requests_instrumentor)

            # Instrument urllib3
            urllib3_instrumentor = URLLib3Instrumentor()
            urllib3_instrumentor.instrument()
            self._instrumentors.append(urllib3_instrumentor)

            # Instrument asyncio
            asyncio_instrumentor = AsyncioInstrumentor()
            asyncio_instrumentor.instrument()
            self._instrumentors.append(asyncio_instrumentor)

            logger.info("Auto-instrumentation configured")

        except Exception as e:
            logger.warning(f"Failed to set up auto-instrumentation: {e}")

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for OTLP exporters."""
        headers = {}
        
        # API key authentication
        api_key = os.getenv("OTEL_EXPORTER_OTLP_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key

        # Bearer token authentication
        token = os.getenv("OTEL_EXPORTER_OTLP_TOKEN")
        if token:
            headers["authorization"] = f"Bearer {token}"

        # Custom headers from environment
        custom_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
        if custom_headers:
            for header in custom_headers.split(","):
                if "=" in header:
                    key, value = header.split("=", 1)
                    headers[key.strip()] = value.strip()

        return headers

    def get_tracer(self, name: str) -> trace.Tracer:
        """Get a tracer instance."""
        if not self._initialized or not self.config.enabled:
            return trace.NoOpTracer()
        return trace.get_tracer(name)

    def get_meter(self, name: str) -> metrics.Meter:
        """Get a meter instance."""
        if not self._initialized or not self.config.enabled:
            return metrics.NoOpMeter()
        return metrics.get_meter(name)

    def start_span(self, name: str, **kwargs) -> trace.Span:
        """Start a new span."""
        if not self._initialized or not self.config.enabled:
            return trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)
        
        tracer = self.get_tracer(__name__)
        return tracer.start_span(name, **kwargs)

    def record_metric(self, name: str, value: float, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Record a metric value."""
        if not self._initialized or not self.config.enabled:
            return
        
        try:
            meter = self.get_meter(__name__)
            counter = meter.create_counter(name)
            counter.add(value, attributes or {})
        except Exception as e:
            logger.warning(f"Failed to record metric {name}: {e}")

    def record_histogram(self, name: str, value: float, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Record a histogram value."""
        if not self._initialized or not self.config.enabled:
            return
        
        try:
            meter = self.get_meter(__name__)
            histogram = meter.create_histogram(name)
            histogram.record(value, attributes or {})
        except Exception as e:
            logger.warning(f"Failed to record histogram {name}: {e}")

    def set_gauge(self, name: str, value: float, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Set a gauge value."""
        if not self._initialized or not self.config.enabled:
            return
        
        try:
            meter = self.get_meter(__name__)
            gauge = meter.create_up_down_counter(name)
            gauge.add(value, attributes or {})
        except Exception as e:
            logger.warning(f"Failed to set gauge {name}: {e}")

    async def shutdown(self) -> None:
        """Shutdown telemetry and flush remaining data."""
        if not self._initialized:
            return

        try:
            # Uninstrument auto-instrumentation
            for instrumentor in self._instrumentors:
                try:
                    instrumentor.uninstrument()
                except Exception as e:
                    logger.warning(f"Failed to uninstrument: {e}")

            # Shutdown tracer provider
            if self.tracer_provider:
                self.tracer_provider.shutdown()

            # Shutdown meter provider
            if self.meter_provider:
                self.meter_provider.shutdown()

            self._initialized = False
            logger.info("Telemetry shutdown completed")

        except Exception as e:
            logger.error(f"Error during telemetry shutdown: {e}")

    def add_span_attributes(self, span: trace.Span, attributes: Dict[str, Any]) -> None:
        """Add attributes to a span."""
        if not self._initialized or not self.config.enabled:
            return
        
        try:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        except Exception as e:
            logger.warning(f"Failed to add span attributes: {e}")

    def add_span_event(self, span: trace.Span, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add an event to a span."""
        if not self._initialized or not self.config.enabled:
            return
        
        try:
            span.add_event(name, attributes or {})
        except Exception as e:
            logger.warning(f"Failed to add span event: {e}")

    def record_exception(self, span: trace.Span, exception: Exception) -> None:
        """Record an exception in a span."""
        if not self._initialized or not self.config.enabled:
            return
        
        try:
            span.record_exception(exception)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))
        except Exception as e:
            logger.warning(f"Failed to record exception: {e}")

    def get_current_span(self) -> trace.Span:
        """Get the current active span."""
        if not self._initialized or not self.config.enabled:
            return trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)
        
        return trace.get_current_span()

    def is_enabled(self) -> bool:
        """Check if telemetry is enabled and initialized."""
        return self._initialized and self.config.enabled

    def get_config_summary(self) -> Dict[str, Any]:
        """Get telemetry configuration summary."""
        return {
            "enabled": self.config.enabled,
            "endpoint": self.config.endpoint,
            "prometheus_enabled": self.config.enable_prometheus_metrics,
            "initialized": self._initialized,
            "instrumentors": len(self._instrumentors),
            "environment_vars": {
                "OTEL_SERVICE_NAME": os.getenv("OTEL_SERVICE_NAME"),
                "OTEL_RESOURCE_ATTRIBUTES": os.getenv("OTEL_RESOURCE_ATTRIBUTES"),
                "OTEL_EXPORTER_OTLP_ENDPOINT": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
                "JAEGER_ENDPOINT": os.getenv("JAEGER_ENDPOINT"),
            }
        }