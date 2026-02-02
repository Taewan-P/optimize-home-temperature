#!/usr/bin/env python3
"""Data Collector Service - Main Entry Point

Collects sensor data from Home Assistant and writes to InfluxDB.
Polls temperature/humidity every 60s, weather every 5min, electricity daily.
"""

import asyncio
import logging
import os
import signal
import sys
from contextlib import AsyncExitStack

from dotenv import load_dotenv

from src.data_collector import DataCollector
from src.ha_client import HaClient

# Load environment variables
load_dotenv()

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class DataCollectorService:
    """Main data collector service with graceful shutdown support."""

    def __init__(self):
        self.exit_stack: AsyncExitStack | None = None
        self.data_collector: DataCollector | None = None
        self.running = False

    async def start(self) -> None:
        """Start the data collector service."""
        logger.info("Starting Data Collector Service")

        self.exit_stack = AsyncExitStack()
        await self.exit_stack.__aenter__()

        try:
            # Initialize Home Assistant client
            logger.info("Initializing Home Assistant client")
            ha_client = HaClient.from_env()
            await self.exit_stack.enter_async_context(ha_client)

            # Initialize Data Collector
            logger.info("Initializing Data Collector")
            self.data_collector = DataCollector.from_env(ha_client)
            await self.exit_stack.enter_async_context(self.data_collector)

            # Start collection loops
            logger.info("Starting data collection loops")
            await self.data_collector.start()

            self.running = True
            logger.info("Data Collector Service started successfully")

            # Keep running until shutdown
            while self.running:
                await asyncio.sleep(1)

        except KeyError as e:
            logger.error(f"Missing required environment variable: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error starting service: {e}", exc_info=True)
            sys.exit(1)

    async def stop(self) -> None:
        """Stop the data collector service gracefully."""
        logger.info("Stopping Data Collector Service")
        self.running = False

        if self.data_collector:
            await self.data_collector.stop()

        if self.exit_stack:
            await self.exit_stack.__aexit__(None, None, None)

        logger.info("Data Collector Service stopped")


# Global service instance for signal handling
service: DataCollectorService | None = None


def handle_shutdown_signal(signum: int, frame) -> None:
    """Handle shutdown signals (SIGINT, SIGTERM)."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown")
    if service and service.running:
        asyncio.create_task(service.stop())


async def main() -> None:
    """Main entry point."""
    global service

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    # Create and start service
    service = DataCollectorService()

    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
