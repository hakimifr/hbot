import logging
import random
import unicodedata
from typing import override

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

logger = logging.getLogger(__name__)


class MyPlugin(BasePlugin):
    name: str = "Text Manipulation"
    description: str = "Plugin used to manipulate text. Shuffle, get unicode data, etc."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def unicode(self, app: Client, message: Message) -> None:
        assert message.reply_to_message
        assert message.reply_to_message.text

        text = message.reply_to_message.text.replace("\n", "").replace("\r", "").replace("\t", "")
        chars: list[str] = list(text)

        unicode_names: list[str] = []
        for char in chars:
            logger.info("process char '%s'", char)
            unicode_names.append(f"'{char}' -> {unicodedata.name(char)}")

        merged_lines: str = ""
        edited: bool = False
        for un in unicode_names:
            if len(merged_lines + f"{un}\n") > 4096:
                logger.info("merged_lines bigger than telegram's limit, splitting")
                if edited:
                    await message.reply_text(merged_lines)
                else:
                    await message.edit_text(merged_lines)
                    edited = True

                merged_lines = ""

            merged_lines += f"{un}\n"

        if merged_lines:
            if edited:
                await message.reply_text(merged_lines)
            else:
                await message.edit_text(merged_lines)

    async def clap(self, app: Client, message: Message) -> None:
        assert message.reply_to_message
        assert message.reply_to_message.text

        words: str = message.reply_to_message.text.replace(" ", b"\xf0\x9f\x91\x8f".decode())
        await message.edit_text(words)

    async def shuffle(self, app: Client, message: Message) -> None:
        if not message.reply_to_message:
            await message.edit_text("__please reply to a message__!")
            return

        assert message.reply_to_message.text
        words: list[str] = message.reply_to_message.text.split(" ")
        random.shuffle(words)

        joint: str = " ".join(words)
        await message.edit_text(joint)

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        return RegisterHandlersResult(
            group=0,
            handlers=[
                MessageHandler(self.unicode, filters.command("un", prefixes=self.prefixes) & filters.me),
                MessageHandler(self.clap, filters.command("clap", prefixes=self.prefixes) & filters.me),
                MessageHandler(self.shuffle, filters.command("shuf", prefixes=self.prefixes) & filters.me),
            ],
        )
