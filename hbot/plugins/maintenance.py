import asyncio
import atexit
import json
import logging
import os
import shutil
import subprocess  # noqa S404
import time
from dataclasses import dataclass
from functools import partial
from typing import cast, override

from anyio import NamedTemporaryFile, Path
from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR
from hbot.base_plugin import BasePlugin

logger = logging.getLogger(__name__)
db = JsonDB(__name__, PERSIST_DIR)
update_lock: asyncio.Lock = asyncio.Lock()


@dataclass(frozen=True)
class LogJsonPayload:
    ts: str
    level: str
    logger: str
    msg: str
    exc: str = ""


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

        # cleanup
        atexit._run_exitfuncs()

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
        command: str = cast(str, message.text).removeprefix(".shell").strip()

        partial_func = partial(
            subprocess.run,
            [sh_path, "-c", command],  # type: ignore
            capture_output=True,
        )
        result: subprocess.CompletedProcess = await asyncio.get_running_loop().run_in_executor(
            None,
            partial_func,
        )

        stdout: str = result.stdout.decode()
        stderr: str = result.stderr.decode()

        await message.edit_text(f"command: `{command}`\nstdout:```\n{stdout}```\n\nstderr:```\n{stderr}\n```")

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

        async with (
            await log_file.open("r", encoding="utf-8") as f,
            NamedTemporaryFile("a+", suffix="_parsed.log", encoding="utf-8") as pf,
        ):
            logger.info("open succeeds, uploading")
            await message.reply_document(f.wrapped.name)
            logger.info("upload done")

            logger.info("parsing JSON payload of log file into '%s'", pf.wrapped.name)
            await message.edit_text("__parsing JSON payload of log file__")
            async for line in f:
                try:
                    logger.disabled = True
                    payload_raw: dict = json.loads(line)
                    lp: LogJsonPayload = LogJsonPayload(**payload_raw)

                    prefix: str = f"[{lp.ts}] {lp.level}({lp.logger}): "
                    logmsg: str = f"{prefix}{lp.msg} {lp.exc}"
                    final: str = logmsg.replace("\n", f"\n{prefix}")
                    final: str = f"{final}\n"
                    await pf.write(final)
                except json.JSONDecodeError:
                    logger.warning("malformed log line, skipping")
                    continue
                finally:
                    logger.disabled = False

            logger.info("flushing temp file '%s'", pf.wrapped.name)
            await pf.flush()

            logger.info("uploading parsed log file")
            await message.reply_document(pf.wrapped.name)

        logger.info("finished")
        await message.edit_text("__done__")

    @override
    def register_handlers(self) -> list[Handler]:
        end_time = time.time()
        db.read_database()

        loop = asyncio.get_running_loop()

        restart_status: bool = db.data.get("restart", False)
        update_changelog: str = db.data.get("update_changelog", "")
        restart_time_delta: float = end_time - db.data.get("begin_time", 0)

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
