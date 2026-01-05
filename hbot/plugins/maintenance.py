import asyncio
import logging
import os
import subprocess
import time
from typing import cast

from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.base_plugin import BasePlugin

logger = logging.getLogger(__name__)
db = JsonDB(__name__)


class MaintenancePlugin(BasePlugin):
    name: str = "Maintenance Plugin"
    description: str = "This plugin is for performing maintenance for the userbot, e.g. updating it."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def update(self, app: Client, message: Message) -> None:
        begin_time = time.time()
        await message.edit_text("__running git pull__")
        result = subprocess.run(["/bin/git", "pull", "--rebase"], capture_output=True)
        if result.returncode != 0:
            await message.edit_text(f"__error when running git pull__, {str(result.stderr.decode())}")
            return

        if result.stdout.decode() == "Already up to date.\n":
            await message.edit_text("__bot is already up to date__")
            return

        await message.edit_text("__restarting the bot__")
        db.data["begin_time"] = begin_time
        db.data["chat_id"] = message.chat.id  # type: ignore
        db.data["message_id"] = message.id
        db.data["restart"] = True
        db.data["update_changelog"] = result.stdout.decode()
        db.write_database()
        os.execl("/usr/local/bin/uv", "uv", "run", "python3", "-m", "hbot")  # noqa: S606

    async def shell(self, app: Client, message: Message) -> None:
        result = subprocess.run(  # noqa: S603
            message.text.removeprefix(".shell").strip(),  # type: ignore
            capture_output=True,
        )

        await message.edit_text(f"stdout:\n{result.stdout.decode()}\n\nstderr:\n{result.stderr.decode()}\n")

    def register_handlers(self) -> list[Handler]:
        end_time = time.time()
        db.read_database()

        loop = asyncio.get_running_loop()

        if db.data.get("restart"):
            logger.info("attempting to finish restart")
            task = loop.create_task(self.app.connect())

            def done_callback(*args, **kwargs) -> None:
                update_text = (
                    "__bot updated and restarted successfully, took "
                    f"{end_time - db.data['begin_time']:.2f}s__\n"
                    f"{db.data['update_changelog']}"
                )
                loop.create_task(
                    self.app.edit_message_text(
                        db.data["chat_id"],
                        db.data["message_id"],
                        update_text,
                    )
                )

            task.add_done_callback(done_callback)

            db.data["restart"] = False

        return [
            MessageHandler(
                self.update,
                filters.command("update", prefixes=self.prefixes) & filters.me,
            ),
            MessageHandler(
                self.shell,
                filters.command("shell", prefixes=self.prefixes) & filters.me,
            ),
        ]
