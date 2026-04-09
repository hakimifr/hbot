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

import fnmatch
import logging
import tarfile
import time
from asyncio import AbstractEventLoop, get_running_loop
from typing import cast, override
from zipfile import ZipFile, is_zipfile

from anyio import NamedTemporaryFile, Path, TemporaryDirectory
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Document
from pyrogram.types.messages_and_media import Message

from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

logger = logging.getLogger(__name__)

_MAX_MSG_LENGTH = 4000


class MyPlugin(BasePlugin):
    name: str = "Archive Tools"
    description: str = "Plugin with various tools to work with zip and tar archives."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def progress_logger(self, current: int, total: int):
        logger.info("zip download progress: %s/%s (%s)", current, total, (current / total) * 100)

    # -------------------------------------------------------------------------
    # Shared private helpers
    # -------------------------------------------------------------------------

    async def _require_document_reply(self, message: Message, prompt: str) -> bool:
        """Return ``True`` if the pre-conditions for an archive command are met.

        Sends the appropriate error message and returns ``False`` when:
        - there is no reply-to message, or
        - the replied-to message does not have a document attached.

        This consolidates the identical guard blocks that previously appeared
        at the top of every archive handler (unzip, unzipl, untar, untarl).
        """
        if not message.reply_to_message:
            await message.edit_text(f"__reply to the file that you want to {prompt}__")
            return False
        if not message.reply_to_message.document:
            await message.edit_text(f"__please reply to a {prompt} file__")
            return False
        return True

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Return a human-readable size string (KB or MB)."""
        size_kb = size_bytes / 1024
        if size_kb < 1024:
            return f"{size_kb:.1f}KB"
        return f"{size_kb / 1024:.1f}MB"

    @staticmethod
    def _build_archive_listing(entries: list[tuple[bool, str, int]], archive_type: str) -> str:
        """Build a Telegram-formatted file listing string for an archive.

        Args:
            entries: A list of ``(is_dir, name, size_bytes)`` tuples.
            archive_type: Label shown in the heading, e.g. ``"Zip"`` or ``"Tar"``.

        This eliminates the near-identical listing loops in unzipl() and untarl().
        """
        file_list = f"**\U0001f4e6 {archive_type} Contents**\n\n"
        total_size = 0
        file_count = 0
        dir_count = 0

        for is_dir, name, size in entries:
            if is_dir:
                dir_count += 1
                file_list += f"\U0001f4c1 `{name}`\n"
            else:
                file_count += 1
                total_size += size
                file_list += f"\U0001f4c4 `{name}` ({MyPlugin._format_size(size)})\n"

        total_mb = total_size / (1024 * 1024)
        summary = f"**Files:** {file_count} | **Dirs:** {dir_count} | **Total Size:** {total_mb:.2f}MB\n\n"
        file_list = file_list[:20] + summary + file_list[20:]
        return file_list

    async def _send_or_upload_text(
        self,
        message: Message,
        text: str,
        filename_suffix: str,
        caption: str,
    ) -> None:
        """Send *text* as a Telegram message, or upload it as a file if too long.

        Consolidates the ``len(x) <= max_length / else upload`` pattern that
        previously appeared independently in unzipl() and untarl().
        """
        if len(text) <= _MAX_MSG_LENGTH:
            await message.edit_text(text)
        else:
            logger.info("text too long (%d chars), uploading as file", len(text))
            await message.edit_text("__file list too long, uploading as text file__")
            async with NamedTemporaryFile("w", suffix=filename_suffix, encoding="utf-8") as tf:
                plain_text = (
                    text.replace("**", "").replace("\U0001f4c1", "DIR:").replace("\U0001f4c4", "FILE:").replace("`", "")
                )
                await tf.write(plain_text)
                await tf.flush()
                await message.reply_document(tf.wrapped.name, caption=caption)

    # -------------------------------------------------------------------------
    # Command handlers
    # -------------------------------------------------------------------------

    async def unzip(self, app: Client, message: Message) -> None:
        """Unzip a file, optionally only extracting specific files."""
        if not await self._require_document_reply(message, "unzip"):
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)

        command_text: str = cast(str, message.text).strip()
        parts = command_text.split(maxsplit=1)
        files_to_extract: list[str] | None = None

        if len(parts) > 1:
            files_to_extract = parts[1].split()
            logger.info("extracting only specific files: %s", files_to_extract)

        loop: AbstractEventLoop = get_running_loop()
        document: Document = cast(Document, replied_to_message.document)

        async with NamedTemporaryFile("w+b", suffix=".zip") as f, TemporaryDirectory() as d:
            logger.info("downloading zip to temp file, name = '%s'", f.wrapped.name)
            await app.download_media(document, f.wrapped.name, progress=self.progress_logger)

            logger.info("checking zip file validity")
            if not await loop.run_in_executor(None, is_zipfile, f.wrapped.name):
                logger.info("zip file is invalid")
                await message.edit_text("__the file provided is not a zip file__")
                return

            await message.edit_text("__unzipping__")

            zipfile: ZipFile = ZipFile(f.wrapped.name)

            if files_to_extract:
                all_files = zipfile.namelist()
                namelist: list[Path] = []
                matched_files: set[str] = set()

                for requested_pattern in files_to_extract:
                    for zip_file in all_files:
                        if fnmatch.fnmatch(zip_file, requested_pattern) and zip_file not in matched_files:
                            namelist.append(Path(d).joinpath(zip_file))
                            matched_files.add(zip_file)
                            logger.info("will extract: %s (matched pattern: %s)", zip_file, requested_pattern)

                if not namelist:
                    logger.warning("no matching files found in zip for patterns: %s", files_to_extract)
                    await message.edit_text("__no matching files found in zip__")
                    return

                logger.info("extracting %d specific files", len(namelist))
                start_time = time.perf_counter()
                for p in namelist:
                    relative_path = str(p.relative_to(d))
                    await loop.run_in_executor(None, zipfile.extract, relative_path, d)
                duration_unzip = time.perf_counter() - start_time
                logger.info("selective unzip took %s seconds", duration_unzip)
            else:
                namelist = [Path(d).joinpath(x) for x in zipfile.namelist()]
                logger.info("zip file name list (with temp dir): %s", namelist)
                logger.info("extracting zip file, dir = '%s'", d)

                start_time = time.perf_counter()
                await loop.run_in_executor(None, zipfile.extractall, d)
                duration_unzip = time.perf_counter() - start_time
                logger.info("unzip took %s seconds", duration_unzip)

            for file in namelist:
                if await file.is_dir():
                    logger.info("skip uploading '%s' because it is a folder", file.as_posix())
                    continue

                logger.info("uploading '%s'", file.as_posix())
                await message.reply_document(file.as_posix())

            duration_unzip_and_upload = time.perf_counter() - start_time
            logger.info("unzip + upload took %s seconds", duration_unzip_and_upload)
            await message.edit_text(f"__unzip finished, took {duration_unzip_and_upload:.3f}s__")

    async def unzipl(self, app: Client, message: Message) -> None:
        """List contents of a zip file with detailed information."""
        if not await self._require_document_reply(message, "view"):
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)
        loop: AbstractEventLoop = get_running_loop()
        document: Document = cast(Document, replied_to_message.document)

        async with NamedTemporaryFile("w+b", suffix=".zip") as f:
            logger.info("downloading zip to temp file, name = '%s'", f.wrapped.name)
            await app.download_media(document, f.wrapped.name, progress=self.progress_logger)

            logger.info("checking zip file validity")
            if not await loop.run_in_executor(None, is_zipfile, f.wrapped.name):
                logger.info("zip file is invalid")
                await message.edit_text("__the file provided is not a zip file__")
                return

            zipfile: ZipFile = ZipFile(f.wrapped.name)
            logger.info("building detailed file list for zip")

            entries = [(info.is_dir(), info.filename, info.file_size) for info in zipfile.infolist()]
            file_list = self._build_archive_listing(entries, "Zip")
            logger.info("zip listing built (%d entries)", len(entries))
            await self._send_or_upload_text(message, file_list, ".txt", "__zip contents__")

    async def untar(self, app: Client, message: Message) -> None:
        """Extract a tar/tar.gz/tar.bz2 file."""
        if not await self._require_document_reply(message, "extract"):
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)
        loop: AbstractEventLoop = get_running_loop()
        document: Document = cast(Document, replied_to_message.document)

        async with NamedTemporaryFile("w+b", suffix=".tar") as f, TemporaryDirectory() as d:
            logger.info("downloading tar to temp file, name = '%s'", f.wrapped.name)
            await app.download_media(document, f.wrapped.name, progress=self.progress_logger)

            logger.info("checking tar file validity")
            try:
                is_tar = await loop.run_in_executor(None, tarfile.is_tarfile, f.wrapped.name)
                if not is_tar:
                    logger.info("tar file is invalid")
                    await message.edit_text("__the file provided is not a tar file__")
                    return
            except Exception as e:
                logger.error("failed to check tar file: %s", e)
                await message.edit_text(f"__error checking tar file: {e}__")
                return

            await message.edit_text("__extracting tar file__")

            try:
                with tarfile.open(f.wrapped.name, "r:*") as tar:
                    logger.info("extracting tar file, dir = '%s'", d)
                    start_time = time.perf_counter()
                    await loop.run_in_executor(None, tar.extractall, d)
                    duration_extract = time.perf_counter() - start_time
                    logger.info("tar extraction took %s seconds", duration_extract)

                    namelist: list[Path] = [Path(d).joinpath(x.name) for x in tar.getmembers()]
                    logger.info("extracted %d items from tar", len(namelist))

                for file in namelist:
                    if await file.is_dir():
                        logger.info("skip uploading '%s' because it is a folder", file.as_posix())
                        continue

                    logger.info("uploading '%s'", file.as_posix())
                    await message.reply_document(file.as_posix())

                duration_total = time.perf_counter() - start_time
                logger.info("tar extract + upload took %s seconds", duration_total)
                await message.edit_text(f"__extraction finished, took {duration_total:.3f}s__")
            except Exception as e:
                logger.error("failed to extract tar file: %s", e)
                await message.edit_text(f"__error extracting tar: {e}__")

    async def untarl(self, app: Client, message: Message) -> None:
        """List contents of a tar file."""
        if not await self._require_document_reply(message, "view"):
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)
        loop: AbstractEventLoop = get_running_loop()
        document: Document = cast(Document, replied_to_message.document)

        async with NamedTemporaryFile("w+b", suffix=".tar") as f:
            logger.info("downloading tar to temp file, name = '%s'", f.wrapped.name)
            await app.download_media(document, f.wrapped.name, progress=self.progress_logger)

            logger.info("checking tar file validity")
            try:
                is_tar = await loop.run_in_executor(None, tarfile.is_tarfile, f.wrapped.name)
                if not is_tar:
                    logger.info("tar file is invalid")
                    await message.edit_text("__the file provided is not a tar file__")
                    return
            except Exception as e:
                logger.error("failed to check tar file: %s", e)
                await message.edit_text(f"__error checking tar file: {e}__")
                return

            try:
                with tarfile.open(f.wrapped.name, "r:*") as tar:
                    logger.info("building detailed file list for tar")
                    entries = [(member.isdir(), member.name, member.size) for member in tar.getmembers()]
                    file_list = self._build_archive_listing(entries, "Tar")
                    logger.info("tar listing built (%d entries)", len(entries))
                    await self._send_or_upload_text(message, file_list, ".txt", "__tar contents__")
            except Exception as e:
                logger.error("failed to list tar contents: %s", e)
                await message.edit_text(f"__error listing tar: {e}__")

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        return RegisterHandlersResult(
            handlers=[
                MessageHandler(
                    self.unzip,
                    filters.command("unzip", prefixes=self.prefixes) & filters.me,
                ),
                MessageHandler(
                    self.unzipl,
                    filters.command("unzipl", prefixes=self.prefixes) & filters.me,
                ),
                MessageHandler(
                    self.untar,
                    filters.command("untar", prefixes=self.prefixes) & filters.me,
                ),
                MessageHandler(
                    self.untarl,
                    filters.command("untarl", prefixes=self.prefixes) & filters.me,
                ),
            ]
        )
