import inspect
import logging
import os
from tempfile import NamedTemporaryFile
from types import FrameType
from typing import cast, override

from google import genai
from google.genai import types
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Message

from hbot.core.base_plugin import BasePlugin, RegisterHandlerResult

logger = logging.getLogger(__name__)


class Gemini(BasePlugin):
    name: str = "Gemini Plugin"
    description: str = "Plugin for Gemini"

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def _respond(self, app: Client, message: Message, text: str, edit: bool = False) -> Message:
        current_frame = inspect.currentframe()
        assert current_frame, "could not get current frame"
        frame = cast(FrameType, current_frame.f_back)

        fn_name = frame.f_code.co_name
        line_no = frame.f_lineno

        if edit:
            return await message.edit_text(f"__[{fn_name}:{line_no}] {text}__")

        return await message.reply_text(f"__[{fn_name}:{line_no}] {text}__")

    async def search_handler(self, client: Client, message: Message) -> None:
        if os.getenv(key="GEMINI_API_KEY") is None:
            await message.edit_text("api key for gemini is not set")
            logger.error("api key for gemini is not set, please export GEMINI_API_KEY")
            return

        parts = message.text.split(maxsplit=1)  # type: ignore
        if len(parts) > 1:
            prompt = parts[1]
            await message.edit("Asking..")
            try:
                # Call the async helper
                response_text = await self.ask_gemini(prompt)
                if len(response_text) > 4096:
                    await message.edit_text("response too long, sending as file")
                    with NamedTemporaryFile("w+", encoding="utf-8", suffix=".md") as f:
                        f.write(response_text)
                        f.flush()
                        await message.reply_document(f.name)
                else:
                    await message.edit_text(response_text)
            except TimeoutError as e:
                logging.exception("Gemini Error:")
                await message.edit(f"Error: {str(e)}")
        else:
            await message.edit("Please provide a search query!")

    async def ask_gemini(self, text_to_be_ask) -> str:
        api_key = os.getenv(key="GEMINI_API_KEY")
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(temperature=1.0)

        try:
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash", contents=text_to_be_ask, config=config
            )
            if response.text is None:
                raise
        except Exception:
            logger.exception("error when generating response, traceback:")
            return "error when generating response, see log for more info"

        return response.text

    @override
    def register_handlers(self) -> RegisterHandlerResult:
        return RegisterHandlerResult(
            group=1,
            handlers=[
                MessageHandler(
                    self.search_handler,
                    filters.command("ask", prefixes=self.prefixes) & filters.me,
                ),
            ],
        )
