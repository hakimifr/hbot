# SPDX-License-Identifier: GPL-3.0-only
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# Copyright (c) 2026, Firdaus Hakimi <hakimifirdaus944@gmail.com>

import asyncio
import atexit
import gc
import logging
import os
import resource
import shutil
import subprocess  # noqa S404
import time
from dataclasses import dataclass
from functools import partial
from typing import Never, cast, override

from anyio import NamedTemporaryFile, Path
from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR
from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

logger = logging.getLogger(__name__)
db = JsonDB(__name__, PERSIST_DIR)
update_lock: asyncio.Lock = asyncio.Lock()

# Configuration constants
LOG_TRIM_LINES = 1000  # Number of lines to keep when trimming log file


@dataclass(frozen=True)
class LogJsonPayload:
    ts: str
    level: str
    logger: str
    lineno: int
    funcname: str
    msg: str
    exc: str = ""


class MaintenancePlugin(BasePlugin):
    name: str = "Maintenance Plugin"
    description: str = "This plugin is for performing maintenance for the userbot, e.g. updating it."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    def _perform_restart(self, message: Message) -> Never:
        begin_time = time.time()
        db.data["begin_time"] = begin_time
        db.data["chat_id"] = message.chat.id  # type: ignore
        db.data["message_id"] = message.id
        db.data["restart"] = True
        db.write_database()

        # cleanup
        atexit._run_exitfuncs()

        python_path: str | None = shutil.which("python3")
        if not python_path:
            raise RuntimeError("cannot find python3 executable")
        os.execl(python_path, "python3", "-m", "hbot")  # noqa: S606

    async def _run_subprocess(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run *cmd* in a thread-pool executor and return the completed process.

        This eliminates the repeated ``partial(subprocess.run, ...) +
        run_in_executor`` boilerplate that previously appeared in both
        ``update()`` and ``shell()``.
        """
        partial_func = partial(subprocess.run, cmd, capture_output=True)
        return await asyncio.get_running_loop().run_in_executor(None, partial_func)

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

            result = await self._run_subprocess([git_path, "pull", "--rebase"])
            if result.returncode != 0:
                logger.error("git pull failed with return code %d: %s", result.returncode, result.stderr.decode())
                await message.edit_text(f"__error when running git pull__, {str(result.stderr.decode())}")
                return

            if result.stdout.decode() == "Already up to date.\n":
                logger.info("bot is already up to date")
                await message.edit_text("__bot is already up to date__")
                return

            # Get git diff before restarting
            logger.info("getting git diff after update")

            check_result = await self._run_subprocess([git_path, "rev-parse", "--verify", "HEAD@{1}"])

            if check_result.returncode == 0:
                diff_result = await self._run_subprocess([git_path, "diff", "HEAD@{1}", "HEAD"])
                git_diff = diff_result.stdout.decode() if diff_result.returncode == 0 else "Could not get diff"
                logger.info("git diff retrieved, length: %d bytes", len(git_diff))
            else:
                logger.warning("reflog not available or HEAD@{1} does not exist, skipping diff")
                git_diff = "Git diff not available (reflog disabled or first commit)"

            await message.edit_text("__restarting the bot__")
            db.data["update_changelog"] = result.stdout.decode()
            db.data["git_diff"] = git_diff
            self._perform_restart(message)

    async def shell(self, app: Client, message: Message) -> None:
        sh_path: str = shutil.which("sh") or "/usr/bin/sh"  # fallback to hardcoded path
        command: str = cast(str, message.text).removeprefix(".shell").strip()

        logger.info("executing shell command: %s", command)
        result = await self._run_subprocess([sh_path, "-c", command])

        stdout: str = result.stdout.decode()
        stderr: str = result.stderr.decode()

        output = f"command: `{command}`\nstdout:```\n{stdout}```\n\nstderr:```\n{stderr}\n```"

        max_length = 4000
        logger.info("command output length: %d characters", len(output))

        if len(output) <= max_length:
            logger.info("output fits in single message")
            await message.edit_text(output)
        else:
            logger.info("output too long, uploading as file")
            await message.edit_text("__output too long, uploading as file__")

            async with NamedTemporaryFile("w", suffix=".txt", encoding="utf-8") as f:
                await f.write(f"Command: {command}\n\n")
                await f.write(f"=== STDOUT ===\n{stdout}\n\n")
                await f.write(f"=== STDERR ===\n{stderr}\n")
                await f.flush()

                logger.info("uploading shell output to file: %s", f.wrapped.name)
                await message.reply_document(f.wrapped.name, caption=f"__output of:__ `{command}`")
                logger.info("shell output file uploaded successfully")

    async def getlog(self, app: Client, message: Message) -> None:
        """Get log file with optional head/tail parameters."""
        command_text: str = cast(str, message.text).strip()
        parts = command_text.split()

        head_lines: int | None = None
        tail_lines: int | None = None

        i = 1
        while i < len(parts):
            if parts[i] == "--head" and i + 1 < len(parts):
                try:
                    head_lines = int(parts[i + 1])
                    logger.info("head parameter set to %d lines", head_lines)
                    i += 2
                except ValueError:
                    logger.warning("invalid head parameter: %s", parts[i + 1])
                    i += 1
            elif parts[i] == "--tail" and i + 1 < len(parts):
                try:
                    tail_lines = int(parts[i + 1])
                    logger.info("tail parameter set to %d lines", tail_lines)
                    i += 2
                except ValueError:
                    logger.warning("invalid tail parameter: %s", parts[i + 1])
                    i += 1
            else:
                i += 1

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
            logger.info("open succeeds, reading log file")

            if head_lines or tail_lines:
                logger.info("reading all lines for head/tail processing")
                all_lines = await f.readlines()

                if head_lines:
                    all_lines = all_lines[:head_lines]
                    logger.info("keeping first %d lines", head_lines)
                elif tail_lines:
                    all_lines = all_lines[-tail_lines:]
                    logger.info("keeping last %d lines", tail_lines)

                async with NamedTemporaryFile("w", suffix="_filtered.log", encoding="utf-8") as ff:
                    for line in all_lines:
                        await ff.write(line)
                    await ff.flush()
                    logger.info("uploading filtered log file")
                    await message.reply_document(ff.wrapped.name)
            else:
                logger.info("uploading full log file")
                await message.reply_document(f.wrapped.name)

        logger.info("finished")
        await message.edit_text("__done__")

    async def dellog(self, app: Client, message: Message) -> None:
        """Delete or trim the log file."""
        command_text: str = cast(str, message.text).strip()

        trim_mode = "--trim" in command_text

        log_file: Path = Path("bot.log")

        logger.info("checking log file existence for deletion/trimming")
        if not await log_file.exists():
            logger.warning("log file does not exist")
            await message.edit_text("__log file does not exist!__")
            return

        if trim_mode:
            logger.info("trimming log file (keeping last %d lines)", LOG_TRIM_LINES)
            await message.edit_text("__trimming log file...__")

            try:
                async with await log_file.open("r", encoding="utf-8") as f:
                    all_lines = await f.readlines()

                lines_to_keep = all_lines[-LOG_TRIM_LINES:] if len(all_lines) > LOG_TRIM_LINES else all_lines
                logger.info("keeping %d lines out of %d", len(lines_to_keep), len(all_lines))

                async with await log_file.open("w", encoding="utf-8") as f:
                    await f.writelines(lines_to_keep)

                logger.info("log file trimmed successfully")
                await message.edit_text(f"__log file trimmed, kept {len(lines_to_keep)} lines__")
            except Exception as e:
                logger.error("failed to trim log file: %s", e)
                await message.edit_text(f"__failed to trim log: {e}__")
        else:
            logger.info("deleting log file")
            await message.edit_text("__deleting log file...__")

            try:
                await log_file.unlink()
                logger.info("log file deleted successfully")
                await message.edit_text("__log file deleted__")
            except Exception as e:
                logger.error("failed to delete log file: %s", e)
                await message.edit_text(f"__failed to delete log: {e}__")

    async def triggergc(self, app: Client, message: Message) -> None:
        logger.info("calling garbage collector")
        await message.edit_text("calling garbage collector")

        ram_usage_before_mb: float = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        collected: int = gc.collect()
        ram_usage_after_mb: float = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

        logger.info(
            "done. ram_usage_before_mb=%d, ram_usage_after_mb=%d, collected(unreachable objects)=%d",
            ram_usage_before_mb,
            ram_usage_after_mb,
            collected,
        )
        await message.edit_text(f"done. {ram_usage_before_mb=}, {ram_usage_after_mb=}, {collected=}")

    @override
    def register_handlers(self) -> RegisterHandlersResult:
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

                async def send_update_info():
                    logger.info("sending restart completion message")
                    await self.app.edit_message_text(
                        db.data["chat_id"],
                        db.data["message_id"],
                        update_text,
                    )

                    if git_diff and len(git_diff) > 0:
                        logger.info("uploading git diff file after update")
                        try:
                            async with NamedTemporaryFile("w", suffix=".diff", encoding="utf-8") as f:
                                await f.write(git_diff)
                                await f.flush()
                                logger.info("uploading diff file: %s", f.wrapped.name)
                                await self.app.send_document(
                                    db.data["chat_id"], f.wrapped.name, caption="__git diff after update__"
                                )
                                logger.info("diff file uploaded successfully")
                        except Exception as e:
                            logger.error("failed to upload git diff: %s", e)

                loop.create_task(send_update_info())

            task.add_done_callback(done_callback)

            db.data["update_changelog"] = ""
            db.data["git_diff"] = ""
            db.data["restart"] = False

        return RegisterHandlersResult(
            handlers=[
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
                    self.dellog,
                    filters.command("dellog", prefixes=self.prefixes) & filters.me,
                ),
                MessageHandler(
                    self.triggergc,
                    filters.command("triggergc", prefixes=self.prefixes) & filters.me,
                ),
            ]
        )
