import asyncio
import logging
import os
import shutil
import subprocess
import time
from functools import partial

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
            loop = asyncio.get_running_loop()

            # Get git diff before update
            partial_func_diff = partial(
                subprocess.run,
                [git_path, "diff", "HEAD", "origin/HEAD"],
                capture_output=True,
            )
            diff_result: subprocess.CompletedProcess = await loop.run_in_executor(None, partial_func_diff)
            git_diff = diff_result.stdout.decode()

            # unfortunately, asyncio.create_subprocess_exec cannot be used here because this bot
            # uses uvloop, and the aforementioned function is broken with uvloop. we have to resort
            # to this workaround, which work just as well
            partial_func = partial(
                subprocess.run,
                [git_path, "pull", "--rebase"],
                capture_output=True,
            )
            result: subprocess.CompletedProcess = await loop.run_in_executor(
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
            db.data["git_diff"] = git_diff
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

        output = f"stdout:\n{result.stdout.decode()}\n\nstderr:\n{result.stderr.decode()}\n"

        # If output is too long (>4096 chars), upload as file
        if len(output) > 4096:
            async with NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
                await f.write(output)
                temp_path = f.wrapped.name
            try:
                await message.reply_document(temp_path, caption="__shell output (too long for message)__")
                await message.edit_text("__command executed, output uploaded as file__")
            finally:
                await Path(temp_path).unlink(missing_ok=True)
        else:
            await message.edit_text(output)

    async def getlog(self, app: Client, message: Message) -> None:
        # Parse optional head/tail parameter
        text_parts = message.text.split()  # type: ignore
        lines = None
        mode = "full"

        if len(text_parts) > 1:
            try:
                lines = int(text_parts[1])
                if lines == 0:
                    await message.edit_text("__parameter cannot be 0__")
                    return
                # Negative number means tail, positive means head
                if lines < 0:
                    mode = "tail"
                    lines = abs(lines)
                else:
                    mode = "head"
            except ValueError:
                await message.edit_text(
                    "__invalid parameter, use .getlog [number] where negative=tail, positive=head__"
                )
                return

        await message.edit_text("__preparing log__")

        logger.info("opening log file")
        log_file: Path = Path("bot.log")

        logger.info("checking log file existence")
        if not await log_file.exists():
            logger.warning("log file does not exist")
            await message.edit_text("__cannot locate log file!__")
            return

        logger.info("log file exists")

        if lines is not None:
            # Read specific lines
            async with await log_file.open("r", encoding="utf-8") as f:
                content = await f.read()
                log_lines = content.split("\n")

                if mode == "head":
                    filtered_lines = log_lines[:lines]
                else:  # tail
                    filtered_lines = log_lines[-lines:]

                filtered_content = "\n".join(filtered_lines)

                # Write to temp file
                async with NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
                    await tf.write(filtered_content)
                    temp_path = tf.wrapped.name

                logger.info("uploading filtered log")
                try:
                    await message.reply_document(temp_path, caption=f"__{mode} {lines} lines__")
                finally:
                    await Path(temp_path).unlink(missing_ok=True)
        else:
            # Upload full log
            async with await log_file.open("r", encoding="utf-8") as f:
                logger.info("open succeeds, uploading")
                await message.reply_document(f.wrapped.name)

        logger.info("finished")
        await message.edit_text("__done__")

    async def deletelog(self, app: Client, message: Message) -> None:
        await message.edit_text("__deleting log file__")

        log_file: Path = Path("bot.log")

        if not await log_file.exists():
            await message.edit_text("__log file does not exist!__")
            return

        await log_file.unlink()
        logger.info("log file deleted")
        await message.edit_text("__log file deleted__")

    async def trimlog(self, app: Client, message: Message) -> None:
        # Parse parameter for number of lines to keep
        text_parts = message.text.split()  # type: ignore
        lines_to_keep = 1000  # default

        if len(text_parts) > 1:
            try:
                lines_to_keep = int(text_parts[1])
            except ValueError:
                await message.edit_text("__invalid parameter, use .trimlog [number]__")
                return

        await message.edit_text(f"__trimming log to last {lines_to_keep} lines__")

        log_file: Path = Path("bot.log")

        if not await log_file.exists():
            await message.edit_text("__log file does not exist!__")
            return

        async with await log_file.open("r", encoding="utf-8") as f:
            content = await f.read()
            log_lines = content.split("\n")

            if len(log_lines) <= lines_to_keep:
                await message.edit_text(f"__log already has {len(log_lines)} lines, no trimming needed__")
                return

            # Keep only the last N lines
            trimmed_lines = log_lines[-lines_to_keep:]

        async with await log_file.open("w", encoding="utf-8") as f:
            await f.write("\n".join(trimmed_lines))

        logger.info("log file trimmed to %s lines", lines_to_keep)
        await message.edit_text(f"__log trimmed from {len(log_lines)} to {lines_to_keep} lines__")

    def register_handlers(self) -> list[Handler]:
        end_time = time.time()
        db.read_database()

        loop = asyncio.get_running_loop()

        restart_status: bool = db.data.get("restart", False)
        update_changelog: str = db.data.get("update_changelog", "")
        git_diff: str = db.data.get("git_diff", "")
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

                async def send_update_message():
                    await self.app.edit_message_text(
                        db.data["chat_id"],
                        db.data["message_id"],
                        update_text,
                    )

                    # Upload git diff if available and not empty
                    if git_diff and git_diff.strip():
                        async with NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
                            await f.write(git_diff)
                            diff_path = f.wrapped.name
                        try:
                            await self.app.send_document(
                                db.data["chat_id"], diff_path, caption="__git diff from update__"
                            )
                        finally:
                            await Path(diff_path).unlink(missing_ok=True)

                loop.create_task(send_update_message())

            task.add_done_callback(done_callback)

            db.data["update_changelog"] = ""
            db.data["git_diff"] = ""
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
            MessageHandler(
                self.deletelog,
                filters.command("deletelog", prefixes=self.prefixes) & filters.me,
            ),
            MessageHandler(
                self.trimlog,
                filters.command("trimlog", prefixes=self.prefixes) & filters.me,
            ),
        ]
