import logging

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class PingPlugin(BasePlugin):
    name: str = "Unnamed Plugin"
    description: str = "No description"

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def ping(self, app: Client, message: Message) -> None:
        logger.debug("ping, pong!")
        await message.edit_text("Pong!")

    def register_handlers(self) -> list[Handler]:
        return [
            MessageHandler(
                self.ping,
                filters.command("ping", prefixes=self.prefixes) & filters.me,
            ),
        ]
