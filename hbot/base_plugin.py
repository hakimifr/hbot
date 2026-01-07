import logging

from jsondb.database import JsonDB
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler

from hbot import PERSIST_DIR

logger = logging.getLogger(__name__)


class BasePlugin:
    name: str = "Base Plugin"
    description: str = "Not supposed to be instantiated."

    # There is no need to change the prefixes in the subclasses. This way, consistency is maintained for every plugins.
    # Unless there's a valid reason of doing so.
    config = JsonDB(__name__, PERSIST_DIR)

    config.read_database()
    if isinstance(config.data.get("prefixes"), list):
        prefixes: list[str] = config.data.get("prefixes")  # type: ignore
    else:
        prefixes: list[str] = ["."]

    # Allow other plugins to change the prefix
    config.close()

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    # Allow other plugins to change the prefix
    # TODO: add option to reload all modules and/or restart the bot
    def change_global_prefix(self, prefixes: list[str]) -> None:
        logger.info("changing global prefixes for bot to %s", prefixes)
        config = JsonDB(__name__, PERSIST_DIR)

        config.read_database()
        config.data.update({"prefixes": prefixes})
        config.write_database()

        config.close()

    def register_handlers(self) -> list[Handler]:
        raise NotImplementedError("a plugin must implement this method")
