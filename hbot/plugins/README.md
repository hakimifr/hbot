# Welcome to plugin folder!

This bot's plugin system is meant to be as intuitive as possible.
Take a look at the example plugin below, to see how the implementation works.

```python
import logging
from collections.abc import Awaitable
from typing import override

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.core.base_plugin import BasePlugin, RegisterHandlerResult

logger = logging.getLogger(__name__)


class MyPlugin(BasePlugin):
    name: str = "Example Plugin"
    description: str = "This is the description of your plugin."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def ping(self, app: Client, message: Message) -> None:
        logger.debug("ping, pong!")
        await message.edit_text("Pong!")

    @override
    def register_handlers(self) -> RegisterHandlerResult | Awaitable[RegisterHandlerResult]:
        return RegisterHandlerResult(
            # You do not need to specify group, it's 0 by default. Advanced use case will require
            # this to other value though.
            group=0,
            handlers=[
                MessageHandler(self.ping, filters.command("ping", prefixes=self.prefixes) & filters.me),
            ],
        )
```

The plugin loader will call the method `register_handlers`, so it MUST be defined. Note that the
class `MyPlugin` must be a subclass of [`BasePlugin`](../base_plugin.py#L10-L43), as this is how the
loader knows that this class contains the `register_handler` method that needs to be called. The
name `MyPlugin` itself is arbitrary; you can name it anything you want, as long as it is a subclass
of [`BasePlugin`](../base_plugin.py:L10-L43).

## Async register_handlers

Take a look closely at the `register_handler()` method above. The return type is `-> list[Handler] |
Awaitable[list[Handler]]`, which means the method can either be regular method (sync), or async
method. This is useful if you need to perform asynchronous operations during handler registration:

```python
async def register_handlers(self) -> RegisterHandlerResult:
    # Perform async operations here if needed
    logger.info("Performing async initialization")
    await some_async_operation()
    return RegisterHandlerResult(
        handlers=[
            MessageHandler(self.ping, filters.command("ping", prefixes=self.prefixes) & filters.me),
        ],
    )
```

The plugin loader will automatically detect whether `register_handlers` is sync or async and handle
it appropriately.

## Extra base plugin goodies

The `BasePlugin` class that you inherit defines a method
[`change_global_prefix()`](../core/base_plugin.py#L37-L45):

```python
class BasePlugin:
    ...

    # Allow other plugins to change the prefix
    # TODO: add option to reload all modules and/or restart the bot
    @final
    def change_global_prefix(self, prefixes: list[str]) -> None:
        logger.info("changing global prefixes for bot to %s", prefixes)
        config = JsonDB(__name__, PERSIST_DIR)

        config.read_database()
        config.data.update({"prefixes": prefixes})
        config.write_database()

        config.close()
```

This allows you to modify the prefix plugin-wide, unless the plugin sets its own prefix instead of
`self.prefixes`. Note that the bot must be restarted for it to take effect.
