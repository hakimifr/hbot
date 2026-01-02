# Welcome to plugin folder!

This bot's plugin system is meant to be as intuitive as possible.
Take a look at the example plugin below, to see how the implementation works.

```python
import logging

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class MyPlugin(BasePlugin):
    name: str = "Example Plugin"
    description: str = "This is the description of your plugin."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def ping(self, app: Client, message: Message) -> None:
        logger.debug("ping, pong!")
        await message.edit_text("Pong!")

    def register_handlers(self) -> list[Handler]:
        return [MessageHandler(self.ping, filters.command("ping", prefixes=self.prefixes) & filters.me)]
```

The plugin loader will call the method `register_handlers`, so it MUST be defined.
Note that the class `MyPlugin` must be a subclass of [`BasePlugin`](../base_plugin.py#L10-L43),
as this is how the loader knows that this class contains the `register_handler` method that needs
to be called. The name `MyPlugin` itself is arbitrary; you can name it anything
you want, as long as it is a subclass of [`BasePlugin`](../base_plugin.py:L10-L43).
