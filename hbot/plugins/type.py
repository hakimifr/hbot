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
import logging
from dataclasses import dataclass
from itertools import batched
from typing import override

from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.errors.exceptions import MessageNotModified
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR
from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

logger = logging.getLogger(__name__)
block_db: JsonDB = JsonDB(f"{__name__}:block", PERSIST_DIR)


@dataclass
class BlockEntry:
    chat_id: int
    blocked_stickers: list[str]
    blocked_packs: list[str]
    blocked_gifs: list[str]


async def deleter_helper(msg: Message, delete_after: float = 3) -> None:
    await asyncio.sleep(delete_after)
    await msg.delete()


async def deleter(msg: Message, delete_after: float = 3) -> None:
    await asyncio.create_task(deleter_helper(msg, delete_after))


class ModPlugin(BasePlugin):
    name: str = "Moderation Plugin"
    description: str = "Plugin for group/channel moderation"

    def __init__(self, app: Client) -> None:
        super().__init__(app)

    async def edit(self, app: Client, message: Message) -> None:
        assert message.text
        logger.info("original text: %s", message.text)
        args: list[str] = message.text.split(" ")
        logger.info("args list: %s", args)
        args.pop(0)
        logger.info("after cleared: %s", args)

        new_msg = " ".join(args)
        logger.info("after joined: %s", new_msg)
        for i in range(2, len(new_msg) + 2, 2):
            t = "".join(next(batched(new_msg, n=i, strict=False)))
            logger.info("typed text: %s", t)
            try:
                await message.edit_text(t)
            except MessageNotModified:
                pass
            await asyncio.sleep(0.4)

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        base = filters.me
        return RegisterHandlersResult(
            group=3,
            handlers=[
                MessageHandler(self.edit, filters.command(["type"], prefixes=self.prefixes) & base),
            ],
        )
