import logging
import tarfile
import time
from asyncio import AbstractEventLoop, get_running_loop
from typing import cast
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
    name: str = "Zip Tools"
    description: str = "Plugin with various tools to work with zip files."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def progress_logger(self, current: int, total: int):
        logger.info("zip download progress: %s/%s (%s)", current, total, (current / total) * 100)

    async def unzip(self, app: Client, message: Message) -> None:
        if not message.reply_to_message:
            await message.edit_text("__reply to the file that you want to unzip__")
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)

        if not replied_to_message.document:
            await message.edit_text("__please reply to a zip file__")
            return

        # Parse optional file filters from command
        text_parts = message.text.split(maxsplit=1)  # type: ignore
        file_filters = []
        if len(text_parts) > 1:
            file_filters = text_parts[1].split()

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
            try:
                # Filter files if specified
                if file_filters:
                    all_names = zipfile.namelist()
                    filtered_names = [
                        name for name in all_names if any(filter_str in name for filter_str in file_filters)
                    ]
                    if not filtered_names:
                        await message.edit_text("__no files matched the specified filters__")
                        return
                else:
                    filtered_names = zipfile.namelist()

                logger.info("zip file name list: %s", filtered_names)
                logger.info("extracting zip file, dir = '%s'", d)

                start_time = time.perf_counter()
                if file_filters:
                    # Extract only filtered files
                    for name in filtered_names:
                        await loop.run_in_executor(None, zipfile.extract, name, d)
                else:
                    await loop.run_in_executor(None, zipfile.extractall, d)
                duration_unzip = time.perf_counter() - start_time
                logger.info("unzip took %s seconds", duration_unzip)

                # Convert to Path objects for file operations
                namelist: list[Path] = [Path(d).joinpath(x) for x in filtered_names]
                for file in namelist:
                    if await file.is_dir():
                        logger.info("skip uploading '%s' because it is a folder", file.as_posix())
                        continue

                    logger.info("uploading '%s'", file.as_posix())
                    await message.reply_document(file.as_posix())

                duration_unzip_and_upload = time.perf_counter() - start_time
                logger.info("unzip + upload took %s seconds", duration_unzip_and_upload)
                await message.edit_text(f"__unzip finished, took {duration_unzip_and_upload:.3f}s__")
            finally:
                zipfile.close()

    async def unzipl(self, app: Client, message: Message) -> None:
        if not message.reply_to_message:
            await message.edit_text("__reply to the archive file__")
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)

        if not replied_to_message.document:
            await message.edit_text("__please reply to a zip file__")
            return

        loop: AbstractEventLoop = get_running_loop()
        document: Document = cast(Document, replied_to_message.document)

        async with NamedTemporaryFile("w+b", suffix=".zip") as f:
            logger.info("downloading archive to temp file, name = '%s'", f.wrapped.name)
            await app.download_media(document, f.wrapped.name, progress=self.progress_logger)

            logger.info("checking archive validity")
            if await loop.run_in_executor(None, is_zipfile, f.wrapped.name):
                zipfile: ZipFile = ZipFile(f.wrapped.name)
                try:
                    entries = zipfile.namelist()

                    list_text = f"**Zip Contents ({len(entries)} entries)**\n\n"
                    for entry in entries:
                        info = zipfile.getinfo(entry)
                        size_mb = info.file_size / (1024 * 1024)
                        list_text += f"`{entry}` - {size_mb:.2f} MB\n"

                    # Split if too long
                    if len(list_text) > 4096:
                        async with NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
                            await tf.write(list_text)
                            temp_path = tf.wrapped.name
                        try:
                            await message.reply_document(temp_path, caption="__zip contents__")
                            await message.edit_text("__list uploaded as file (too long for message)__")
                        finally:
                            await Path(temp_path).unlink(missing_ok=True)
                    else:
                        await message.edit_text(list_text)
                finally:
                    zipfile.close()
            else:
                await message.edit_text("__the file provided is not a zip file__")

    async def untar(self, app: Client, message: Message) -> None:
        if not message.reply_to_message:
            await message.edit_text("__reply to the tar file__")
            return

        replied_to_message: Message = cast(Message, message.reply_to_message)

        if not replied_to_message.document:
            await message.edit_text("__please reply to a tar file__")
            return

        # Parse optional file filters
        text_parts = message.text.split(maxsplit=1)  # type: ignore
        file_filters = []
        if len(text_parts) > 1:
            file_filters = text_parts[1].split()

        loop: AbstractEventLoop = get_running_loop()
        document: Document = cast(Document, replied_to_message.document)

        async with NamedTemporaryFile("w+b", suffix=".tar") as f, TemporaryDirectory() as d:
            logger.info("downloading tar to temp file, name = '%s'", f.wrapped.name)
            await app.download_media(document, f.wrapped.name, progress=self.progress_logger)

            logger.info("checking tar file validity")
            try:
                if not await loop.run_in_executor(None, tarfile.is_tarfile, f.wrapped.name):
                    await message.edit_text("__the file provided is not a tar file__")
                    return
            except (OSError, tarfile.TarError) as e:
                logger.error("error checking tar file: %s", e)
                await message.edit_text(f"__error: {str(e)}__")
                return

            await message.edit_text("__extracting tar__")

            tararchive = await loop.run_in_executor(None, tarfile.open, f.wrapped.name)
            try:
                # Filter files if specified
                if file_filters:
                    all_names = tararchive.getnames()
                    filtered_names = [
                        name for name in all_names if any(filter_str in name for filter_str in file_filters)
                    ]
                    if not filtered_names:
                        await message.edit_text("__no files matched the specified filters__")
                        return
                else:
                    filtered_names = tararchive.getnames()

                logger.info("tar file name list: %s", filtered_names)
                logger.info("extracting tar file, dir = '%s'", d)

                start_time = time.perf_counter()
                if file_filters:
                    for name in filtered_names:
                        await loop.run_in_executor(None, tararchive.extract, name, d)
                else:
                    await loop.run_in_executor(None, tararchive.extractall, d)
                duration_extract = time.perf_counter() - start_time
                logger.info("extraction took %s seconds", duration_extract)

                # Convert to Path objects for file operations
                namelist: list[Path] = [Path(d).joinpath(x) for x in filtered_names]
                for file in namelist:
                    if await file.is_dir():
                        logger.info("skip uploading '%s' because it is a folder", file.as_posix())
                        continue

                    logger.info("uploading '%s'", file.as_posix())
                    await message.reply_document(file.as_posix())

                duration_total = time.perf_counter() - start_time
                logger.info("extract + upload took %s seconds", duration_total)
                await message.edit_text(f"__extraction finished, took {duration_total:.3f}s__")
            finally:
                tararchive.close()

    async def untarl(self, app: Client, message: Message) -> None:
        if not message.reply_to_message:
            await message.edit_text("__reply to the tar file__")
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
                if await loop.run_in_executor(None, tarfile.is_tarfile, f.wrapped.name):
                    tararchive = await loop.run_in_executor(None, tarfile.open, f.wrapped.name)
                    try:
                        entries = tararchive.getnames()

                        list_text = f"**Tar Contents ({len(entries)} entries)**\n\n"
                        for entry in entries:
                            member = tararchive.getmember(entry)
                            size_mb = member.size / (1024 * 1024)
                            list_text += f"`{entry}` - {size_mb:.2f} MB\n"

                        # Split if too long
                        if len(list_text) > 4096:
                            async with NamedTemporaryFile("w", encoding="utf-8", delete=False) as tf:
                                await tf.write(list_text)
                                temp_path = tf.wrapped.name
                            try:
                                await message.reply_document(temp_path, caption="__tar contents__")
                                await message.edit_text("__list uploaded as file (too long for message)__")
                            finally:
                                await Path(temp_path).unlink(missing_ok=True)
                        else:
                            await message.edit_text(list_text)
                    finally:
                        tararchive.close()
                else:
                    await message.edit_text("__the file provided is not a tar file__")
            except (OSError, tarfile.TarError) as e:
                logger.error("error reading tar file: %s", e)
                await message.edit_text(f"__error: {str(e)}__")

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
