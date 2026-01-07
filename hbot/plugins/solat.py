import json
import logging
from dataclasses import dataclass, fields, is_dataclass
from itertools import chain, islice, repeat
from textwrap import dedent
from typing import Any

from anyio import NamedTemporaryFile
from httpx import AsyncClient
from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import ParseMode
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR
from hbot.base_plugin import BasePlugin

logger = logging.getLogger(__name__)
db: JsonDB = JsonDB(__name__, PERSIST_DIR)


@dataclass(slots=True)
class ZoneData:
    jakimCode: str  # noqa: N815
    negeri: str
    daerah: str


@dataclass(slots=True)
class _PrayerTime:
    hijri: str
    date: str
    day: str
    fajr: str
    syuruk: str
    dhuhr: str
    asr: str
    maghrib: str
    isha: str


@dataclass(slots=True)
class PrayerData:
    prayerTime: _PrayerTime  # noqa: N815
    status: str
    serverTime: str  # noqa: N815
    periodType: str  # noqa: N815
    lang: str
    zone: str
    bearing: str


def dict_to_dataclass[T](cls: type[T], data: dict[str, Any]) -> T:
    kwargs = {}

    for f in fields(cls):  # type: ignore
        value = data[f.name]

        if is_dataclass(f.type):
            kwargs[f.name] = dict_to_dataclass(f.type, value)  # type: ignore
        else:
            kwargs[f.name] = value

    return cls(**kwargs)


class SolatPlugin(BasePlugin):
    name: str = "Khusus untuk solat"
    description: str = "Buat masa ni ada pasal waktu solat je, maybe more soon."

    def __init__(self, app: Client) -> None:
        self.app: Client = app
        self.http_client: AsyncClient = AsyncClient()

        db.read_database()
        self.zones_data: list[ZoneData] = [ZoneData(**z) for z in db.data.get("zones", [])]
        self.valid_jakimcode: list[str] = self._get_valid_jakimcode()

    def _pad_list(self, iterable, size, padding=None) -> Any:
        return islice(chain(iterable, repeat(padding)), size)

    def _get_valid_jakimcode(self) -> list[str]:
        if len(self.zones_data) == 0:
            logger.warning("cannot get valid jakimcode: `len(self.zones_data)` is 0")
            return []

        return [x.jakimCode for x in self.zones_data]

    async def waktu_solat(self, app: Client, message: Message) -> None:
        if len(self.zones_data) == 0:
            logger.info("zones are not yet cached. building cache...")
            response_json = (await self.http_client.get("https://api.waktusolat.app/zones", timeout=10)).json()
            db.data["zones"] = response_json
            self.zones_data = [ZoneData(**z) for z in response_json]
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

        prayer_data: PrayerData = dict_to_dataclass(PrayerData, response.json())
        final_output_str: str = dedent(
            f"""
            **query result:**
            **Zone:** {zone}
            **Negeri:** {[x.negeri for x in self.zones_data if x.jakimCode == zone][0]}
            **Daerah:** {[x.daerah for x in self.zones_data if x.jakimCode == zone][0]}
            """
        )

        final_output_str += dedent(
            f"""
        **Day:** {prayer_data.prayerTime.day}
        **Date:** {prayer_data.prayerTime.date}
        **Hijri Date:** {prayer_data.prayerTime.hijri}
        **Server Time:** {prayer_data.serverTime}
        **Period Time:** {prayer_data.periodType}
        **Response Status:** {prayer_data.status}

        **WAKTU SOLAT**
        **SUBUH** {prayer_data.prayerTime.fajr}
        **ZOHOR** {prayer_data.prayerTime.dhuhr}
        **ASAR** {prayer_data.prayerTime.asr}
        **MAGHRIB** {prayer_data.prayerTime.maghrib}
        **ISYAK** {prayer_data.prayerTime.isha}
        --
        **SYURUK** {prayer_data.prayerTime.syuruk}
        """
        )

        await message.edit_text(final_output_str)

    async def get_zones(self, app: Client, message: Message) -> None:
        if len(self.zones_data) == 0:
            logger.info("zones are not yet cached. building cache...")
            response_json = (await self.http_client.get("https://api.waktusolat.app/zones", timeout=10)).json()
            db.data["zones"] = response_json
            self.zones_data = [ZoneData(**z) for z in response_json]
            self.valid_jakimcode = self._get_valid_jakimcode()
            db.write_database()

        async with NamedTemporaryFile("w+", suffix=".json") as f:
            await f.write(json.dumps(db.data.get("zones"), indent=2))
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
