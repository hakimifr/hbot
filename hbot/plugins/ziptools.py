import logging
import tarfile
import time
from asyncio import AbstractEventLoop, get_running_loop
from typing import cast, override
from zipfile import ZipFile, is_zipfile

from anyio import NamedTemporaryFile, Path, TemporaryDirectory
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Document
from pyrogram.types.messages_and_media import Message

from hbot.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class MyPlugin(BasePlugin):
    name: str = "Archive Tools"
    description: str = "Plugin with various tools to work with zip and tar archives."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def progress_logger(self, current: int, total: int):
        logger.info("zip download progress: %s/%s (%s)", current, total, (current / total) * 100)

    async def unzip(self, app: Client, message: Message) -> None:
        """Unzip a file, optionally only extracting specific files."""
        if not message.reply_to_message:
            await message.edit_text("__reply to the file that you want to unzip__")
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)

        if not replied_to_message.document:
            await message.edit_text("__please reply to a zip file__")
            return

        # Parse command for specific files to extract
        command_text: str = cast(str, message.text).strip()
        parts = command_text.split(maxsplit=1)
        files_to_extract: list[str] | None = None

        if len(parts) > 1:
            # Split by whitespace to get list of files
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

            # If specific files requested, filter the namelist
            if files_to_extract:
                all_files = zipfile.namelist()
                namelist: list[Path] = []
                for requested_file in files_to_extract:
                    for zip_file in all_files:
                        if requested_file in zip_file:
                            namelist.append(Path(d).joinpath(zip_file))
                            logger.info("will extract: %s", zip_file)

                if not namelist:
                    logger.warning("no matching files found in zip")
                    await message.edit_text("__no matching files found in zip__")
                    return

                # Extract only specific files
                logger.info("extracting %d specific files", len(namelist))
                start_time = time.perf_counter()
                for p in namelist:
                    relative_path = str(p.relative_to(d))
                    await loop.run_in_executor(None, zipfile.extract, relative_path, d)
                duration_unzip = time.perf_counter() - start_time
                logger.info("selective unzip took %s seconds", duration_unzip)
            else:
                namelist: list[Path] = [Path(d).joinpath(x) for x in zipfile.namelist()]
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
        if not message.reply_to_message:
            await message.edit_text("__reply to the file that you want to view__")
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)

        if not replied_to_message.document:
            await message.edit_text("__please reply to a zip file__")
            return

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

            # Build a detailed file list
            logger.info("building detailed file list for zip")
            file_list = "**📦 Zip Contents**\n\n"
            total_size = 0
            file_count = 0
            dir_count = 0

            for info in zipfile.infolist():
                if info.is_dir():
                    dir_count += 1
                    file_list += f"📁 `{info.filename}`\n"
                else:
                    file_count += 1
                    size_kb = info.file_size / 1024
                    total_size += info.file_size
                    if size_kb < 1024:
                        size_str = f"{size_kb:.1f}KB"
                    else:
                        size_str = f"{size_kb / 1024:.1f}MB"
                    file_list += f"📄 `{info.filename}` ({size_str})\n"

            # Add summary at the top
            total_mb = total_size / (1024 * 1024)
            summary = f"**Files:** {file_count} | **Dirs:** {dir_count} | **Total Size:** {total_mb:.2f}MB\n\n"
            file_list = file_list[:20] + summary + file_list[20:]

            logger.info("zip contains %d files, %d directories, total size: %.2fMB", file_count, dir_count, total_mb)

            # Split message if too long
            max_length = 4000
            if len(file_list) <= max_length:
                await message.edit_text(file_list)
            else:
                logger.info("file list too long, uploading as text file")
                await message.edit_text("__file list too long, uploading as text file__")

                async with NamedTemporaryFile("w", suffix=".txt", encoding="utf-8") as tf:
                    plain_text = (
                        file_list.replace("**", "").replace("📁", "DIR:").replace("📄", "FILE:").replace("`", "")
                    )
                    await tf.write(plain_text)
                    await tf.flush()
                    logger.info("uploading file list to: %s", tf.wrapped.name)
                    await message.reply_document(tf.wrapped.name, caption="__zip contents__")

    async def untar(self, app: Client, message: Message) -> None:
        """Extract a tar/tar.gz/tar.bz2 file."""
        if not message.reply_to_message:
            await message.edit_text("__reply to the file that you want to extract__")
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)

        if not replied_to_message.document:
            await message.edit_text("__please reply to a tar file__")
            return

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

                    # Get list of extracted files
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
        if not message.reply_to_message:
            await message.edit_text("__reply to the file that you want to view__")
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)

        if not replied_to_message.document:
            await message.edit_text("__please reply to a tar file__")
            return

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
                    file_list = "**📦 Tar Contents**\n\n"
                    total_size = 0
                    file_count = 0
                    dir_count = 0

                    for member in tar.getmembers():
                        if member.isdir():
                            dir_count += 1
                            file_list += f"📁 `{member.name}`\n"
                        else:
                            file_count += 1
                            size_kb = member.size / 1024
                            total_size += member.size
                            if size_kb < 1024:
                                size_str = f"{size_kb:.1f}KB"
                            else:
                                size_str = f"{size_kb / 1024:.1f}MB"
                            file_list += f"📄 `{member.name}` ({size_str})\n"

                    # Add summary at the top
                    total_mb = total_size / (1024 * 1024)
                    summary = f"**Files:** {file_count} | **Dirs:** {dir_count} | **Total Size:** {total_mb:.2f}MB\n\n"
                    file_list = file_list[:20] + summary + file_list[20:]

                    logger.info(
                        "tar contains %d files, %d directories, total size: %.2fMB", file_count, dir_count, total_mb
                    )

                    # Split message if too long
                    max_length = 4000
                    if len(file_list) <= max_length:
                        await message.edit_text(file_list)
                    else:
                        logger.info("file list too long, uploading as text file")
                        await message.edit_text("__file list too long, uploading as text file__")

                        async with NamedTemporaryFile("w", suffix=".txt", encoding="utf-8") as tf:
                            plain_text = (
                                file_list.replace("**", "")
                                .replace("📁", "DIR:")
                                .replace("📄", "FILE:")
                                .replace("`", "")
                            )
                            await tf.write(plain_text)
                            await tf.flush()
                            logger.info("uploading file list to: %s", tf.wrapped.name)
                            await message.reply_document(tf.wrapped.name, caption="__tar contents__")
            except Exception as e:
                logger.error("failed to list tar contents: %s", e)
                await message.edit_text(f"__error listing tar: {e}__")

    @override
    def register_handlers(self) -> list[Handler]:
        return [
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
