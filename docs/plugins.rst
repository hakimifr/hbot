Working With the Plugin System
##############################

The plugin system is so great, such that you can just delete all of my plugins under the
hbot/plugins/* folder, put your own plugins there. The bot will work fine provided that you did not
mess up the plugins, but if it ever crash, it is guaranteed to not be caused by the core of the bot,
but rather your plugins.

How does the plugin system work?
================================

The plugin system is meant to be modular and simple enough for quick setup. Your custom module must
have a class that inherit from |baseplugin| (In other word, the class must be a subclass of
|baseplugin|). The class must also define a method called ``register_handlers(self)``, which can
either be a normal method, or async method. The loader is capable of calling async version properly.

With this approach, you are free to have as many class as you want in your plugin, as the loader
will only look for the class that inherit |baseplugin|.

.. |baseplugin| replace:: ``hbot.core.base_plugins.BasePlugin``

Take a look at the `Sample Plugin`_.

_`Sample Plugin`
================

.. code-block:: python

    import logging
    from typing import override

    from pyrogram import filters
    from pyrogram.client import Client
    from pyrogram.handlers.handler import Handler
    from pyrogram.handlers.message_handler import MessageHandler
    from pyrogram.types.messages_and_media import Message

    from hbot.base_plugin import BasePlugin, RegisterHandlerResult

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
        def register_handlers(self) -> RegisterHandlerResult:  # Note that this can be async if desired
            return RegisterHandlerResult(
                # This group set to 0 by default, you don't really need to specify this unless you
                # have an advanced use case that requires a different value for this
                group=0,
                handlers=[
                    MessageHandler(
                        self.ping,
                        filters.command("ping", prefixes=self.prefixes) & filters.me,
                    )
                ],
            )

It may look intimidating at first, but if you remove the type annotations and the import for it,
they will look very simple.

.. toctree::
   :maxdepth: 1
   :hidden:
