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

import logging
import random
from typing import override

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

logger: logging.Logger = logging.getLogger(__name__)
POLITE_TEXTS: tuple = (  # Source: https://gist.github.com/hakimifr/cbd17f193bae7a4874ec94ff52d1d410
    "Motherchod",
    "madarchod",
    "Bhosadike",
    "Bhenchod",
    "Betichod",
    "Bhadhava",
    "Chodu",
    "Chutiya",
    "Gaand",
    "Gaandu",
    "Gadha",
    "Bakland",
    "Lauda",
    "Lund",
    "Hijra",
    "Kuttiya",
    "Paad",
    "Randi",
    "Saala kutta",
    "Saali kutti",
    "Tatti",
    "Kamina",
    "Chut ke pasine mein talay huye bhajiye",
    "Chut ke dhakkan",
    "Chut ke gulam",
    "Chutiya ka bheja ghas khane gaya hai",
    "Choot marani ka",
    "Choot ka baal",
    "Chipkali ke jhaat ke baal",
    "Chipkali ke jhaat ke paseene",
    "Chipkali ke gaand ke pasine",
    "Chipkali ke chut ke pasine",
    "Chipkali ki bhigi chut",
    "Chinaal ke gadde ke nipple ke baal ke joon",
    "Chullu bhar muth mein doob mar",
    "Cuntmama",
    "Apni gaand mein muthi daal",
    "Apni lund choos",
    "Apni ma ko ja choos",
    "Bhen ke laude",
    "Bhen ke takke",
    "Abla naari tera buble bhaari",
    "Bhonsri",
    "Bhadwe ka awlat",
    "Bhains ki aulad",
    "Buddha Khoosat",
    "Bol teri gand kaise maru",
    "Bur ki chatani",
    "Chunni",
    "Chinaal",
    "Chudai khana",
    "Chudan chuda",
    "Chut ka pujari",
    "Chut ka bhoot",
    "Gaand ka makhan",
    "Gaand main lassan",
    "Gaand main danda",
    "Gaand main keera",
    "Gaand mein bambu",
    "Gaandfat",
    "Pote kitne bhi bade ho",
    "lund ke niche hi rehte hai",
    "Hazaar lund teri gaand main",
    "Jhat ke baal",
    "Jhaant ke pissu",
    "Kadak Mall",
    "Kali Choot Ke Safaid Jhaat",
    "Khotey ki aulda",
    "Kutte ka awlat",
    "Kutte ki jat",
    "Kutte ke tatte",
    "Kutte ke poot",
    "teri maa ki choot",
    "Lavde ke bal",
    "Lund Chus",
    "Lund Ke Pasine",
    "Meri Gand Ka Khatmal",
    "Moot",
    "Mootna",
    "Najayaz paidaish",
    "Rundi khana",
    "Sadi hui gaand",
    "Teri gaand main kute ka lund",
    "Teri maa ka bhosda",
    "Teri maa ki chut",
    "Tere gaand mein keede paday",
    "Ullu ke pathe",
    "Tatte ke saudagar",
    "Gaand ke andhe",
    "Lund fakir",
    "Chut ka chamcha",
    "Bhosdi wale",
    "Gand ka ghoda",
    "Lund ki naak",
    "Jhaat ka bawaseer",
    "Bandar ki aulad",
    "Suar ki nasal",
    "Gadhe ka lund",
    "Billi ki chut",
    "Kauwe ki jhaat",
    "Chuhe ki gaand",
    "Machhar ki jhaat",
    "Lund pe chadh",
    "Gaand phati ke",
    "Jhaat ka pandit",
    "Chut ka chowkidar",
    "Lund ka langoor",
    "Gaand ka gulla",
    "Bhosdi ka raja",
    "Tatti ka tabedar",
    "Maa chuda",
    "Apni gaand mara",
    "Lund pe baith",
    "Gaand chatwa",
    "Muh mein le",
    "Bhosdiwale ki biwi",
)


class MiscPlugin(BasePlugin):
    name: str = "Miscellaneous"
    description: str = "Stuffs that don't really fit any other plugins."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def polite_text(self, app: Client, message: Message) -> None:
        choice = random.choice(POLITE_TEXTS)  # noqa: S311
        logger.info("chosen polite text: %s", choice)
        await message.edit_text(choice)

    async def construct_sentence(self, app: Client, message: Message) -> None:
        assert message.text
        args: list[str] = message.text.split(" ")
        if len(args) < 2:
            await message.edit_text("__error: not enough args; usage: (prefix)trigger <number of polite texts>__")
            return

        try:
            polite_texts_count: int = int(args[1])
        except ValueError:
            await message.edit_text(f"__error: cannot convert '{args[1]}' to int__")
            return

        if polite_texts_count > len(POLITE_TEXTS):
            await message.edit_text(f"__too much polite texts requested: {polite_texts_count}__")
            return

        chosen: list[str] = random.choices(POLITE_TEXTS, k=int(polite_texts_count))  # noqa: S311
        await message.edit_text(", ".join(chosen))

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        return RegisterHandlersResult(
            handlers=[
                MessageHandler(
                    self.polite_text,
                    filters.command(
                        ["bepolite", "polite", "bp"],
                        prefixes=self.prefixes,
                    )
                    & filters.me,
                ),
                MessageHandler(
                    self.construct_sentence,
                    filters.command(
                        ["cs", "constructsentence", "construct_sentence"],
                        prefixes=self.prefixes,
                    )
                    & filters.me,
                ),
            ],
        )
