import asyncio
import logging
import os

from aiohttp import web
from dotenv import load_dotenv

from src.alerting import Alerting
from src.controller import Controller
from src.ha_client import HaClient

logger = logging.getLogger(__name__)

CONTROL_LOOP_INTERVAL = 30
HEALTH_PORT = 8080


async def health_handler(request):
    controller = request.app["controller"]
    health = controller.get_health()
    return web.json_response(health)


async def control_loop(app):
    controller = app["controller"]

    while True:
        try:
            await controller.run_control_cycle()

            health = controller.get_health()
            logger.info(
                "Controller state: %s | Temp: %.1f°C | Decision: %s",
                health["state"],
                health["last_temperature"] if health["last_temperature"] else 0.0,
                health["last_decision"] or "None",
            )

        except Exception as e:
            logger.exception("Error in control loop: %s", e)

        await asyncio.sleep(CONTROL_LOOP_INTERVAL)


async def start_background_tasks(app):
    app["control_loop_task"] = asyncio.create_task(control_loop(app))


async def cleanup_background_tasks(app):
    app["control_loop_task"].cancel()
    await app["control_loop_task"]


async def main():
    load_dotenv()

    logger.info("Control service starting...")

    ha_client = HaClient.from_env()

    alerting = Alerting(
        ha_url=os.environ["HA_URL"],
        ha_token=os.environ["HA_TOKEN"],
        discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL", ""),
    )

    controller = Controller(
        ha_client=ha_client,
        alerting=alerting,
        heater_entity_id=os.environ["HA_HEATER_CLIMATE_ID"],
        temp_sensor_id=os.environ["HA_TEMP_SENSOR_ID"],
        on_temp=float(os.environ.get("HEATER_ON_TEMP", "25.0")),
        off_temp=float(os.environ.get("HEATER_OFF_TEMP", "26.0")),
        min_cycle_time=int(os.environ.get("MIN_CYCLE_TIME_SECONDS", "180")),
        sensor_stale_timeout=int(os.environ.get("SENSOR_STALE_TIMEOUT_SECONDS", "300")),
        manual_override_timeout=int(os.environ.get("MANUAL_OVERRIDE_TIMEOUT_SECONDS", "1800")),
    )

    async with ha_client:
        app = web.Application()
        app["controller"] = controller
        app["ha_client"] = ha_client

        app.router.add_get("/health", health_handler)

        app.on_startup.append(start_background_tasks)
        app.on_cleanup.append(cleanup_background_tasks)

        logger.info("Starting health endpoint on port %d", HEALTH_PORT)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
        await site.start()

        logger.info(
            "Control service running. Health endpoint: http://localhost:%d/health", HEALTH_PORT
        )

        await asyncio.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(main())
