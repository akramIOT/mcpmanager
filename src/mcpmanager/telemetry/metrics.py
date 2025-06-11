"""Metrics collection for MCPManager operations."""

import time
import logging
from typing import Dict, Any, Optional
from contextlib import contextmanager
from datetime import datetime

from opentelemetry import metrics

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collector for MCPManager-specific metrics."""

    def __init__(self, telemetry_manager):
        """Initialize metrics collector."""
        self.telemetry_manager = telemetry_manager
        self.meter = telemetry_manager.get_meter("mcpmanager.metrics")
        
        # Define metrics
        self._setup_metrics()

    def _setup_metrics(self):
        """Set up all metrics instruments."""
        try:
            # Server lifecycle metrics
            self.servers_total = self.meter.create_counter(
                "mcpmanager_servers_total",
                description="Total number of MCP servers created",
                unit="1"
            )
            
            self.servers_active = self.meter.create_up_down_counter(
                "mcpmanager_servers_active",
                description="Number of currently active MCP servers",
                unit="1"
            )
            
            self.server_start_duration = self.meter.create_histogram(
                "mcpmanager_server_start_duration_seconds",
                description="Time taken to start MCP servers",
                unit="s"
            )
            
            self.server_stop_duration = self.meter.create_histogram(
                "mcpmanager_server_stop_duration_seconds", 
                description="Time taken to stop MCP servers",
                unit="s"
            )

            # Container metrics
            self.containers_created = self.meter.create_counter(
                "mcpmanager_containers_created_total",
                description="Total number of containers created",
                unit="1"
            )
            
            self.container_start_failures = self.meter.create_counter(
                "mcpmanager_container_start_failures_total",
                description="Total number of container start failures",
                unit="1"
            )

            # Image verification metrics
            self.image_verifications = self.meter.create_counter(
                "mcpmanager_image_verifications_total",
                description="Total number of image verifications performed",
                unit="1"
            )
            
            self.image_verification_duration = self.meter.create_histogram(
                "mcpmanager_image_verification_duration_seconds",
                description="Time taken for image verification",
                unit="s"
            )
            
            self.image_verification_failures = self.meter.create_counter(
                "mcpmanager_image_verification_failures_total",
                description="Total number of image verification failures",
                unit="1"
            )

            # Transport metrics
            self.transport_connections = self.meter.create_counter(
                "mcpmanager_transport_connections_total",
                description="Total number of transport connections established",
                unit="1"
            )
            
            self.transport_failures = self.meter.create_counter(
                "mcpmanager_transport_failures_total",
                description="Total number of transport connection failures",
                unit="1"
            )

            # Registry metrics
            self.registry_lookups = self.meter.create_counter(
                "mcpmanager_registry_lookups_total",
                description="Total number of registry lookups",
                unit="1"
            )
            
            self.registry_lookup_duration = self.meter.create_histogram(
                "mcpmanager_registry_lookup_duration_seconds",
                description="Time taken for registry lookups",
                unit="s"
            )

            # Secret metrics
            self.secret_retrievals = self.meter.create_counter(
                "mcpmanager_secret_retrievals_total",
                description="Total number of secret retrievals",
                unit="1"
            )
            
            self.secret_retrieval_failures = self.meter.create_counter(
                "mcpmanager_secret_retrieval_failures_total",
                description="Total number of secret retrieval failures",
                unit="1"
            )

            # Permission metrics
            self.permission_validations = self.meter.create_counter(
                "mcpmanager_permission_validations_total",
                description="Total number of permission profile validations",
                unit="1"
            )
            
            self.permission_violations = self.meter.create_counter(
                "mcpmanager_permission_violations_total",
                description="Total number of permission violations detected",
                unit="1"
            )

            # Runtime metrics
            self.runtime_operations = self.meter.create_counter(
                "mcpmanager_runtime_operations_total",
                description="Total number of runtime operations",
                unit="1"
            )
            
            self.runtime_operation_duration = self.meter.create_histogram(
                "mcpmanager_runtime_operation_duration_seconds",
                description="Time taken for runtime operations",
                unit="s"
            )

            # API metrics
            self.api_requests = self.meter.create_counter(
                "mcpmanager_api_requests_total",
                description="Total number of API requests",
                unit="1"
            )
            
            self.api_request_duration = self.meter.create_histogram(
                "mcpmanager_api_request_duration_seconds",
                description="Time taken for API requests",
                unit="s"
            )

            logger.debug("Metrics instruments initialized")

        except Exception as e:
            logger.warning(f"Failed to initialize metrics: {e}")

    def record_server_created(self, server_name: str, transport_type: str, runtime: str) -> None:
        """Record server creation."""
        try:
            attributes = {
                "server_name": server_name,
                "transport_type": transport_type,
                "runtime": runtime
            }
            self.servers_total.add(1, attributes)
            self.servers_active.add(1, attributes)
            logger.debug(f"Recorded server creation: {server_name}")
        except Exception as e:
            logger.warning(f"Failed to record server creation metric: {e}")

    def record_server_stopped(self, server_name: str, transport_type: str, runtime: str) -> None:
        """Record server stop."""
        try:
            attributes = {
                "server_name": server_name,
                "transport_type": transport_type, 
                "runtime": runtime
            }
            self.servers_active.add(-1, attributes)
            logger.debug(f"Recorded server stop: {server_name}")
        except Exception as e:
            logger.warning(f"Failed to record server stop metric: {e}")

    @contextmanager
    def time_server_start(self, server_name: str, transport_type: str):
        """Time server start operation."""
        start_time = time.time()
        try:
            yield
            duration = time.time() - start_time
            attributes = {
                "server_name": server_name,
                "transport_type": transport_type,
                "status": "success"
            }
            self.server_start_duration.record(duration, attributes)
        except Exception as e:
            duration = time.time() - start_time
            attributes = {
                "server_name": server_name,
                "transport_type": transport_type,
                "status": "failure",
                "error_type": type(e).__name__
            }
            self.server_start_duration.record(duration, attributes)
            raise

    @contextmanager
    def time_server_stop(self, server_name: str):
        """Time server stop operation."""
        start_time = time.time()
        try:
            yield
            duration = time.time() - start_time
            attributes = {
                "server_name": server_name,
                "status": "success"
            }
            self.server_stop_duration.record(duration, attributes)
        except Exception as e:
            duration = time.time() - start_time
            attributes = {
                "server_name": server_name,
                "status": "failure",
                "error_type": type(e).__name__
            }
            self.server_stop_duration.record(duration, attributes)
            raise

    def record_container_created(self, image: str, runtime: str) -> None:
        """Record container creation."""
        try:
            attributes = {
                "image": image,
                "runtime": runtime
            }
            self.containers_created.add(1, attributes)
        except Exception as e:
            logger.warning(f"Failed to record container creation metric: {e}")

    def record_container_start_failure(self, image: str, runtime: str, error_type: str) -> None:
        """Record container start failure."""
        try:
            attributes = {
                "image": image,
                "runtime": runtime,
                "error_type": error_type
            }
            self.container_start_failures.add(1, attributes)
        except Exception as e:
            logger.warning(f"Failed to record container start failure metric: {e}")

    @contextmanager
    def time_image_verification(self, image: str):
        """Time image verification operation."""
        start_time = time.time()
        try:
            yield
            duration = time.time() - start_time
            attributes = {
                "image": image,
                "status": "success"
            }
            self.image_verifications.add(1, attributes)
            self.image_verification_duration.record(duration, attributes)
        except Exception as e:
            duration = time.time() - start_time
            attributes = {
                "image": image,
                "status": "failure",
                "error_type": type(e).__name__
            }
            self.image_verification_failures.add(1, attributes)
            self.image_verification_duration.record(duration, attributes)
            raise

    def record_transport_connection(self, transport_type: str, success: bool) -> None:
        """Record transport connection attempt."""
        try:
            attributes = {
                "transport_type": transport_type,
                "status": "success" if success else "failure"
            }
            
            if success:
                self.transport_connections.add(1, attributes)
            else:
                self.transport_failures.add(1, attributes)
        except Exception as e:
            logger.warning(f"Failed to record transport connection metric: {e}")

    @contextmanager
    def time_registry_lookup(self, registry_type: str):
        """Time registry lookup operation."""
        start_time = time.time()
        try:
            yield
            duration = time.time() - start_time
            attributes = {
                "registry_type": registry_type,
                "status": "success"
            }
            self.registry_lookups.add(1, attributes)
            self.registry_lookup_duration.record(duration, attributes)
        except Exception as e:
            duration = time.time() - start_time
            attributes = {
                "registry_type": registry_type,
                "status": "failure",
                "error_type": type(e).__name__
            }
            self.registry_lookup_duration.record(duration, attributes)
            raise

    def record_secret_retrieval(self, provider: str, success: bool) -> None:
        """Record secret retrieval attempt."""
        try:
            attributes = {
                "provider": provider,
                "status": "success" if success else "failure"
            }
            
            if success:
                self.secret_retrievals.add(1, attributes)
            else:
                self.secret_retrieval_failures.add(1, attributes)
        except Exception as e:
            logger.warning(f"Failed to record secret retrieval metric: {e}")

    def record_permission_validation(self, profile_name: str, violations_count: int) -> None:
        """Record permission profile validation."""
        try:
            attributes = {
                "profile_name": profile_name,
                "has_violations": violations_count > 0
            }
            self.permission_validations.add(1, attributes)
            
            if violations_count > 0:
                violation_attributes = {
                    "profile_name": profile_name
                }
                self.permission_violations.add(violations_count, violation_attributes)
        except Exception as e:
            logger.warning(f"Failed to record permission validation metric: {e}")

    @contextmanager
    def time_runtime_operation(self, operation: str, runtime: str):
        """Time runtime operation."""
        start_time = time.time()
        try:
            yield
            duration = time.time() - start_time
            attributes = {
                "operation": operation,
                "runtime": runtime,
                "status": "success"
            }
            self.runtime_operations.add(1, attributes)
            self.runtime_operation_duration.record(duration, attributes)
        except Exception as e:
            duration = time.time() - start_time
            attributes = {
                "operation": operation,
                "runtime": runtime,
                "status": "failure",
                "error_type": type(e).__name__
            }
            self.runtime_operation_duration.record(duration, attributes)
            raise

    @contextmanager
    def time_api_request(self, method: str, endpoint: str):
        """Time API request."""
        start_time = time.time()
        try:
            yield
            duration = time.time() - start_time
            attributes = {
                "method": method,
                "endpoint": endpoint,
                "status": "success"
            }
            self.api_requests.add(1, attributes)
            self.api_request_duration.record(duration, attributes)
        except Exception as e:
            duration = time.time() - start_time
            attributes = {
                "method": method,
                "endpoint": endpoint,
                "status": "failure",
                "error_type": type(e).__name__
            }
            self.api_request_duration.record(duration, attributes)
            raise

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of recorded metrics."""
        # Note: This is a simple summary - in production you'd typically
        # query the metrics backend for actual values
        return {
            "metrics_enabled": self.telemetry_manager.is_enabled(),
            "instruments_created": 14,  # Number of metric instruments
            "last_updated": datetime.now().isoformat()
        }