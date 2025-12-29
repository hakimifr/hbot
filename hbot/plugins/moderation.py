import asyncio
import logging

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class ModPlugin(BasePlugin):
    name: str = "Moderation Plugin"
    description: str = "Plugin for group/channel moderation"

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def purge(self, app: Client, message: Message) -> None:
        if not message.reply_to_message:
            await message.edit_text("__reply to a message!__")
            return

        # delete 100-by-100
        for i in range(message.reply_to_message.id, message.id, 100):
            await app.delete_messages(
                chat_id=message.chat.id,  # type: ignore
                message_ids=list(range(i, min(i + 100, message.id))),
            )

        await message.edit_text("__purged! this message will auto delete in 5 seconds__")
        await asyncio.sleep(5)
        await message.delete()

    def register_handlers(self) -> list[Handler]:
        return [
            MessageHandler(self.purge, filters.command("purge", prefixes=self.prefixes) & filters.me),
        ]
