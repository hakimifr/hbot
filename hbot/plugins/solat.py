import json
import logging
from itertools import chain, islice, repeat
from textwrap import dedent
from typing import Any, cast

from anyio import NamedTemporaryFile
from httpx import AsyncClient
from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import ParseMode
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.base_plugin import BasePlugin

logger = logging.getLogger(__name__)
db: JsonDB = JsonDB(__name__)


class SolatPlugin(BasePlugin):
    name: str = "Khusus untuk solat"
    description: str = "Buat masa ni ada pasal waktu solat je, maybe more soon."

    def __init__(self, app: Client) -> None:
        self.app: Client = app
        self.http_client: AsyncClient = AsyncClient()

        db.read_database()
        self.zones_data: dict | None = db.data.get("zones")
        self.valid_jakimcode: list[str] = self._get_valid_jakimcode()

    def _pad_list(self, iterable, size, padding=None) -> Any:
        return islice(chain(iterable, repeat(padding)), size)

    def _get_valid_jakimcode(self) -> list[str]:
        if self.zones_data is None:
            logger.warning("cannot get valid jakimcode: `self.zones` is `None`")
            return []

        return [x.get("jakimCode") for x in self.zones_data]

    async def waktu_solat(self, app: Client, message: Message) -> None:
        if self.zones_data is None:
            logger.info("zones are not yet cached. building cache...")
            self.zones_data = db.data["zones"] = (
                await self.http_client.get("https://api.waktusolat.app/zones", timeout=10)
            ).json()
            self.valid_jakimcode = self._get_valid_jakimcode()
            db.write_database()

        splitmsg: list[str] = message.text.split(" ")  # type: ignore
        if len(splitmsg) < 3:
            await message.edit_text("__syntax: .ws <zone> <day> [month] [year]__", parse_mode=ParseMode.MARKDOWN)
            return

        args: list[str] = self._pad_list(splitmsg[1:], 4, None)
        await message.edit_text("__loading...__")

        zone, day, month, year = args

        if zone not in self.valid_jakimcode:
            await message.edit_text(f"invalid zone: {zone}, please refer .getzones")
            return

        extra_data = {}
        if month:
            extra_data.update({"month": month})
        if year:
            extra_data.update({"year": year})
        response = await self.http_client.get(
            f"https://api.waktusolat.app/solat/{zone}/{day}",
            params=extra_data,
        )

        if not response.is_success:
            await message.edit_text(
                f"__api call failed, status code {response.status_code}\n{response.json()}__",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        solat_data: dict = response.json().get("prayerTime")
        final_output_str: str = (
            "**query result:**\n"
            f"**Zone:** {zone}\n"
            f"**Negeri:** {[x.get('negeri') for x in self.zones_data if x.get('jakimCode') == zone][0]}\n"  # type: ignore
            f"**Daerah:** {[x.get('daerah') for x in self.zones_data if x.get('jakimCode') == zone][0]}\n\n"  # type: ignore
        )

        self.zones_data = cast(dict, self.zones_data)
        final_output_str: str = dedent(
            f"""
            **query result:**
            **Zone:** {zone}
            **Negeri:** {[x.get("negeri") for x in self.zones_data if x.get("jakimCode") == zone][0]}
            **Daerah:** {[x.get("daerah") for x in self.zones_data if x.get("jakimCode") == zone][0]}

            """
        )
        for key, value in solat_data.items():
            final_output_str += f"__{key}:__ {value}\n"

        await message.edit_text(final_output_str)

    async def get_zones(self, app: Client, message: Message) -> None:
        if self.zones_data is None:
            logger.info("zones are not yet cached. building cache...")
            self.zones_data = db.data["zones"] = (
                await self.http_client.get("https://api.waktusolat.app/zones", timeout=10)
            ).json()
            self.valid_jakimcode = self._get_valid_jakimcode()
            db.write_database()

        async with NamedTemporaryFile("w+", suffix=".json") as f:
            await f.write(json.dumps(self.zones_data, indent=2))
            await f.flush()
            await message.reply_document(f.wrapped.name)
            await message.delete()

    def register_handlers(self) -> list[Handler]:
        return [
            MessageHandler(
                self.waktu_solat,
                filters.command(["waktusolat", "waktu_solat", "ws"], prefixes=self.prefixes) & filters.me,
            ),
            MessageHandler(
                self.get_zones,
                filters.command("getzones", prefixes=self.prefixes) & filters.me,
            ),
        ]
