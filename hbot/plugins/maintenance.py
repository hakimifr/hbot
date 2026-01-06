import asyncio
import logging
import os
import shutil
import subprocess
import time
from functools import partial

from anyio import Path
from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.base_plugin import BasePlugin

logger = logging.getLogger(__name__)
db = JsonDB(__name__)
update_lock: asyncio.Lock = asyncio.Lock()


class MaintenancePlugin(BasePlugin):
    name: str = "Maintenance Plugin"
    description: str = "This plugin is for performing maintenance for the userbot, e.g. updating it."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    def _perform_restart(self, message: Message) -> None:
        begin_time = time.time()
        db.data["begin_time"] = begin_time
        db.data["chat_id"] = message.chat.id  # type: ignore
        db.data["message_id"] = message.id
        db.data["restart"] = True
        db.write_database()

        uv_path: str = shutil.which("uv") or "/usr/bin/uv"  # fallback to hardcoded path
        os.execl(uv_path, "uv", "run", "python3", "-m", "hbot")  # noqa: S606

    async def restart(self, app: Client, message: Message) -> None:
        if update_lock.locked():
            logger.warning("[restart] cannot acquire lock, will not restart")
            await message.edit_text("__cannot restart because an update process is running__")
            return

        async with update_lock:
            await message.edit_text("__restarting bot__")
            self._perform_restart(message)

    async def update(self, app: Client, message: Message) -> None:
        if update_lock.locked():
            logger.warning("[update] cannot acquire lock, will not update")
            await message.edit_text("__another update is already running__")
            return

        async with update_lock:
            await message.edit_text("__running git pull__")

            git_path: str = shutil.which("git") or "/usr/bin/git"  # fallback to hardcoded path

            # unfortunately, asyncio.create_subprocess_exec cannot be used here because this bot
            # uses uvloop, and the aforementioned function is broken with uvloop. we have to resort
            # to this workaround, which work just as well
            partial_func = partial(
                subprocess.run,
                [git_path, "pull", "--rebase"],
                capture_output=True,
            )
            result: subprocess.CompletedProcess = await asyncio.get_running_loop().run_in_executor(
                None,
                partial_func,
            )
            if result.returncode != 0:
                await message.edit_text(f"__error when running git pull__, {str(result.stderr.decode())}")
                return

            if result.stdout.decode() == "Already up to date.\n":
                await message.edit_text("__bot is already up to date__")
                return

            await message.edit_text("__restarting the bot__")
            db.data["update_changelog"] = result.stdout.decode()
            self._perform_restart(message)

    async def shell(self, app: Client, message: Message) -> None:
        sh_path: str = shutil.which("sh") or "/usr/bin/sh"  # fallback to hardcoded path

        partial_func = partial(
            subprocess.run,
            [sh_path, "-c", message.text.removeprefix(".shell").strip()],  # type: ignore
            capture_output=True,
        )
        result: subprocess.CompletedProcess = await asyncio.get_running_loop().run_in_executor(
            None,
            partial_func,
        )

        await message.edit_text(f"stdout:\n{result.stdout.decode()}\n\nstderr:\n{result.stderr.decode()}\n")

    async def getlog(self, app: Client, message: Message) -> None:
        await message.edit_text("__uploading log__")

        logger.info("opening log file")
        log_file: Path = Path("bot.log")

        logger.info("checking log file existence")
        if not await log_file.exists():
            logger.warning("log file does not exist")
            await message.edit_text("__cannot locate log file!__")
            return

        logger.info("log file exists")

        async with await log_file.open("r", encoding="utf-8") as f:
            logger.info("open succeeds, uploading")
            await message.reply_document(f.wrapped.name)

        logger.info("finished")
        await message.edit_text("__done__")

    def register_handlers(self) -> list[Handler]:
        end_time = time.time()
        db.read_database()

        loop = asyncio.get_running_loop()

        restart_status: bool = db.data.get("restart", False)
        update_changelog: str = db.data.get("update_changelog", "")
        restart_time_delta: float = end_time - db.data["begin_time"]

        if restart_status:
            logger.info("attempting to finish restart")
            task = loop.create_task(self.app.connect())

            def done_callback(*args, **kwargs) -> None:
                update_text = (
                    f"__bot{' updated and ' if update_changelog else ' '}restarted successfully, took "
                    f"{restart_time_delta:.2f}s__\n"
                    f"{update_changelog}"
                )
                loop.create_task(
                    self.app.edit_message_text(
                        db.data["chat_id"],
                        db.data["message_id"],
                        update_text,
                    )
                )

            task.add_done_callback(done_callback)

            db.data["update_changelog"] = ""
            db.data["restart"] = False

        return [
            MessageHandler(
                self.update,
                filters.command("update", prefixes=self.prefixes) & filters.me,
            ),
            MessageHandler(
                self.restart,
                filters.command("restart", prefixes=self.prefixes) & filters.me,
            ),
            MessageHandler(
                self.shell,
                filters.command("shell", prefixes=self.prefixes) & filters.me,
            ),
            MessageHandler(
                self.getlog,
                filters.command("getlog", prefixes=self.prefixes) & filters.me,
            ),
        ]
