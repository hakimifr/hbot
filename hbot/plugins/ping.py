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
import time
from typing import override

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

logger = logging.getLogger(__name__)


class PingPlugin(BasePlugin):
    name: str = "Ping Plugin"
    description: str = "Just a simple .ping command to check if the bot is alive."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def ping(self, app: Client, message: Message) -> None:
        logger.info("ping, pong!")

        start = time.perf_counter()
        await message.edit_text("__Pong!__")
        delta_ms = (time.perf_counter() - start) * 1000

        logger.info("latency: %f ms", delta_ms)
        await message.edit_text(f"__Pong! latency: {delta_ms:.3f} ms__")

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        return RegisterHandlersResult(
            handlers=[
                MessageHandler(
                    self.ping,
                    filters.command("ping", prefixes=self.prefixes) & filters.me,
                ),
            ]
        )
