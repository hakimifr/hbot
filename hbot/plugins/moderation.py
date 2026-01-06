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

        for i in range(message.reply_to_message.id, message.id, 100):
            await app.delete_messages(
                chat_id=message.chat.id,  # type: ignore
                message_ids=list(range(i, min(i + 100, message.id))),
            )

        await message.edit_text("__purged! this message will auto delete in 5 seconds__")
        await asyncio.sleep(5)
        await message.delete()

    async def ban(self, app: Client, message: Message) -> None:
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.edit_text("__reply to a user message!__")
            return

        await app.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)  # type: ignore
        await message.edit_text("__banned__")
        await asyncio.sleep(5)
        await message.delete()

    async def unban(self, app: Client, message: Message) -> None:
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.edit_text("__reply to a user message!__")
            return

        await app.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)  # type: ignore
        await message.edit_text("__unbanned__")
        await asyncio.sleep(5)
        await message.delete()

    def register_handlers(self) -> list[Handler]:
        base = filters.me
        return [
            MessageHandler(self.purge, filters.command("purge", prefixes=self.prefixes) & base),
            MessageHandler(self.ban, filters.command("ban", prefixes=self.prefixes) & base),
            MessageHandler(self.unban, filters.command("unban", prefixes=self.prefixes) & base),
        ]
