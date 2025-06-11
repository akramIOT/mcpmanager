"""Base transport class."""

import logging

logger = logging.getLogger(__name__)


class BaseTransport:
    """Base class for all transports."""

    def __init__(self, container_id: str):
        """Initialize base transport."""
        self.container_id = container_id
        self.running = False

    async def start(self) -> None:
        """Start the transport."""
        self.running = True
        logger.info(f"Transport started for container {self.container_id[:12]}")

    async def stop(self) -> None:
        """Stop the transport."""
        self.running = False
        logger.info(f"Transport stopped for container {self.container_id[:12]}")

    async def is_running(self) -> bool:
        """Check if transport is running."""
        return self.running