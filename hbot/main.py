import logging
import os
import sys

from pyrogram.client import Client
from pyrogram.sync import idle

from hbot import PLUGINS_DIR
from hbot.plugins_loader import load_plugins

logger = logging.getLogger(__name__)

api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")


async def main() -> None:
    app = Client("hbot", api_id, api_hash)

    logger.info("loading plugins from %s", PLUGINS_DIR)
    load_plugins(app, PLUGINS_DIR)

    try:
        await app.start()
        await idle()
    finally:
        await app.stop()
        sys.exit(0)
