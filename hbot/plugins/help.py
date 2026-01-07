import logging
from typing import cast

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.base_plugin import BasePlugin
from hbot.main import get_loaded_plugins

logger = logging.getLogger(__name__)


class MyPlugin(BasePlugin):
    name: str = "Help Plugin"
    description: str = "Return bot usage."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def help(self, app: Client, message: Message) -> None:
        loaded_plugins: dict[BasePlugin, list[Handler]] = await get_loaded_plugins()
        help_string: str = ""

        # This whole thing is very hacky because pyrogram does not provide
        # an easy way to access the bound handler/filter. I had to study the
        # pyrogram's source code just to write this.
        for plugin, handlers in loaded_plugins.items():
            help_string += f"**Plugin: {plugin.name}**\n"
            for h in handlers:
                for x in (h.filters.base, h.filters.other):  # type: ignore
                    if type(x).__name__ == "CommandFilter":
                        x.commands = cast(set, x.commands)
                        help_string += "\n".join(x.commands) + "\n"

            help_string += "\n"

        await message.edit_text(help_string)

    def register_handlers(self) -> list[Handler]:
        return [MessageHandler(self.help, filters.command("help", prefixes=self.prefixes) & filters.me)]
