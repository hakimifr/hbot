import logging
import random
from typing import override

from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.errors import FileReferenceExpired
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR
from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

type FileId = str
type FileUniqueId = str
type ChatId = int

KOMARU_CHANNEL_ID: ChatId = -1002033198247

logger = logging.getLogger(__name__)
komaru_db: JsonDB = JsonDB(__name__, PERSIST_DIR)


class MyPlugin(BasePlugin):
    name: str = "Example Plugin"
    description: str = "This is the description of your plugin."
    prefixes: list[str] = BasePlugin.prefixes.copy()
    prefixes.append("/")

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def _respond(self, app: Client, message: Message, text: str) -> Message:
        assert message.from_user
        assert app.me
        if message.from_user.id == app.me.id:
            return await message.edit_text(text)
        else:
            return await message.reply_text(text)

    async def komaru(self, app: Client, message: Message) -> None:
        komaru_gifs: list[FileId] | None = komaru_db.data.get("komaru_gifs")

        if not komaru_gifs:
            await self._respond(app, message, "__no gifs available. run /scan to scan/rescan komaru GIFs channel__")
            return

        try:
            chosen_gif: FileId = random.choice(komaru_gifs)  # noqa: S311
            await message.reply_animation(chosen_gif)
        except FileReferenceExpired:
            logger.warning("file reference expired! rescanning automatically")
            await self._respond(app, message, "__file reference expired, rescanning__")
            await self.scan(app, message)
            await self.komaru(app, message)

    async def scan(self, app: Client, message: Message) -> None:
        logger.info("clearing komaru_gifs list")
        komaru_db.data["komaru_gifs"] = []

        komaru_gifs_raw: dict[FileUniqueId, FileId] = {}
        duplicates: int = 0

        msg = await self._respond(app, message, "__**scanner:** scanning komaru GIFs channel__")
        msg_ch = await app.send_message(KOMARU_CHANNEL_ID, "__scanning this channel__")

        async for m in app.get_chat_history(KOMARU_CHANNEL_ID):
            if m.animation and m.animation.file_id and m.animation.file_unique_id:
                if m.animation.file_unique_id in komaru_gifs_raw:
                    duplicates += 1
                    continue

                komaru_gifs_raw.update({m.animation.file_unique_id: m.animation.file_id})

        komaru_db.data["komaru_gifs"] = list(komaru_gifs_raw.values())
        komaru_db.write_database()
        await msg_ch.delete()
        await msg.edit_text(
            f"__**scanner:** {len(komaru_gifs_raw) + duplicates} komaru GIFs with "
            f"{duplicates} duplicate(s) found, "
            f"a total of {len(komaru_gifs_raw)} unique GIFs after deduplication__"
        )

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        return RegisterHandlersResult(
            handlers=[
                MessageHandler(self.komaru, filters.command(["komaru", "km"], prefixes=self.prefixes)),
                MessageHandler(self.scan, filters.command(["scan", "sc"], prefixes=self.prefixes)),
            ],
        )
