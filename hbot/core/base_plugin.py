import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import final

from jsondb.database import JsonDB
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler

from hbot import PERSIST_DIR

logger = logging.getLogger(__name__)


@dataclass
class RegisterHandlerResult:
    handlers: list[Handler]
    group: int = 0


class BasePlugin(ABC):
    """The core to every plugins in this bot.

    When :py:meth:`load_plugins()` is called to load plugins, it finds plugin in the plugins/ directory,
    and calls the :py:meth:`register_handler()` method in any class that inherit this class. If you do
    not inherit this class, the loader will assume it as an ordinary class that should not be
    touched. :py:meth:`issubclass()` is used to determine if a class inherits this class.

    Attributes:
        name: (class attribute) The name of the plugin.
        description: (class attribute) The description of the attribute.
        config: (class attribute) The jsondb config attached, this is used to store global prefixes.
        app: The app (pyrogram ``Client``) instance.
    """

    name: str = "Base Plugin"
    description: str = "Not supposed to be instantiated."

    # There is no need to change the prefixes in the subclasses. This way, consistency is maintained
    # for every plugins. Unless there's a valid reason of doing so.
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
    @final
    def change_global_prefix(self, prefixes: list[str]) -> None:
        """This method is used to change the global prefixes for commands of the bot."""
        logger.info("changing global prefixes for bot to %s", prefixes)
        config = JsonDB(__name__, PERSIST_DIR)

        config.read_database()
        config.data.update({"prefixes": prefixes})
        config.write_database()

        config.close()

    @abstractmethod
    def register_handlers(self) -> RegisterHandlerResult | Awaitable[RegisterHandlerResult]:
        """This is the abstract method that must be implemented by subclasses for the bot to work.

        The plugin loader will call this method. The default implementation will raise
        NotImplementedError exception.

        Raises:
            NotImplementedError: This is abstract method. Please provide your own implementation.
        """
        raise NotImplementedError("a plugin must implement this method")
