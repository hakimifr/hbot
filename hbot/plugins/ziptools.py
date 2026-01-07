import logging
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

    def register_handlers(self) -> list[Handler]:
        return [
            MessageHandler(
                self.unzip,
                filters.command("unzip", prefixes=self.prefixes) & filters.me,
            ),
        ]
