Working With the Plugin System
##############################

How does the plugin system work?
================================

The plugin system is meant to be modular and simple enough for quick setup. Your custom module must
have a class that inherit from |baseplugin| (In other word, the class must be a subclass of
|baseplugin|). The class must also define a method called ``register_handler(self)``, which can
either be a normal method, or async method. The loader is capable of calling async version properly.

With this approach, you are free to have as many class as you want in your plugin, as the loader
will only look for the class that inherit |baseplugin|.

Take a look at the `Sample Plugin`_.

_`Sample Plugin`
================

.. |baseplugin| replace:: ``hbot.core.base_plugins.BasePlugin``

.. code-block:: python

    import logging
    from typing import override

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

        @override
        def register_handlers(self) -> list[Handler]:  # Note that this can be async if desired
            return [
                MessageHandler(
                    self.ping,
                    filters.command("ping", prefixes=self.prefixes) & filters.me,
                )
            ]

It may look intimidating at first, but if you remove the type annotations and the import for it,
they will look very simple.

.. toctree::
   :maxdepth: 1
   :hidden:
