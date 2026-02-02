import asyncio
import logging

logger = logging.getLogger(__name__)


async def main():
    logger.info("Control service starting...")
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
