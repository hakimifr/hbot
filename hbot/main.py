import logging
import os
import sys

from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.sync import idle

from hbot import PERSIST_DIR, PLUGINS_DIR
from hbot.base_plugin import BasePlugin
from hbot.plugins_loader import load_plugins

logger = logging.getLogger(__name__)
loaded_plugins: dict[BasePlugin, list[Handler]] = {}
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")

if api_id is None or api_hash is None:
    logger.critical("API_ID and API_HASH must be exported!")
    sys.exit(1)

if not (PERSIST_DIR.exists() and PERSIST_DIR.is_dir()):
    logger.critical("PERSIST_DIR '%s' does not exist!", PERSIST_DIR.as_posix())
    sys.exit(1)


async def get_loaded_plugins() -> dict[BasePlugin, list[Handler]]:
    return loaded_plugins


async def main() -> None:
    global loaded_plugins
    app = Client("hbot", api_id, api_hash)

    logger.info("loading plugins from %s", PLUGINS_DIR)
    loaded_plugins = load_plugins(app, PLUGINS_DIR)

    try:
        await app.start()
        await idle()
    finally:
        await app.stop()
        sys.exit(0)
