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
import random
import time
from typing import override

from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import ChatMemberStatus, MessageServiceType
from pyrogram.handlers import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR
from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

CHAT_WHITELIST: list[int] = [
    -1001267207006,  # photography group
]
TIMEOUT_SECONDS = 30

logger = logging.getLogger(__name__)
db = JsonDB(__name__, PERSIST_DIR)
# Structure:
# {
#     "chat_id": {
#         "user_id": {
#             "expected": 123456,
#             "challenge_message_id": 42,
#             "expires_at": 1778400000.123,
#         }
#     }
# }


class CaptchaPlugin(BasePlugin):
    name: str = "Captcha Plugin"
    description: str = "Require new members to solve a 6-digit captcha."

    def __init__(self, app: Client) -> None:
        self.app = app

        loop = asyncio.get_event_loop()

        for chat_id_str, users in db.data.items():
            for user_id_str, payload in users.items():
                remaining = payload["expires_at"] - time.time()

                if remaining < 0:
                    remaining = 0

                loop.create_task(
                    self.kicker(
                        remaining,
                        int(chat_id_str),
                        int(user_id_str),
                    )
                )

    def _get_user_record(self, chat_id: int, user_id: int) -> dict | None:
        return db.data.get(str(chat_id), {}).get(str(user_id))

    def _save_user_record(
        self,
        chat_id: int,
        user_id: int,
        *,
        expected: int,
        challenge_message_id: int,
        expires_at: float,
    ) -> None:
        chat_key = str(chat_id)
        user_key = str(user_id)

        if chat_key not in db.data:
            db.data[chat_key] = {}

        db.data[chat_key][user_key] = {
            "expected": expected,
            "challenge_message_id": challenge_message_id,
            "expires_at": expires_at,
        }

        db.write_database()

    def _delete_user_record(self, chat_id: int, user_id: int) -> None:
        chat_key = str(chat_id)
        user_key = str(user_id)

        chat = db.data.get(chat_key)
        if not chat:
            return

        chat.pop(user_key, None)

        if not chat:
            db.data.pop(chat_key, None)

        db.write_database()

    async def kicker(self, after: float | int, chat_id: int, user_id: int) -> None:
        await asyncio.sleep(after)

        # User may have solved captcha while we were sleeping.
        if self._get_user_record(chat_id, user_id) is None:
            return

        try:
            member = await self.app.get_chat_member(chat_id, user_id)

            await self.app.ban_chat_member(chat_id, user_id)
            await self.app.unban_chat_member(chat_id, user_id)

            await self.app.send_message(
                chat_id,
                (
                    f"__kicked "
                    f"[{member.user.full_name}](tg://user?id={user_id}) "
                    f"for failing to complete the captcha in time.__"
                ),
            )

        except Exception:
            logger.exception(
                "Failed to kick user %d from chat %d",
                user_id,
                chat_id,
            )

        finally:
            self._delete_user_record(chat_id, user_id)

    async def joinhandler(self, app: Client, message: Message) -> None:
        if message.service != MessageServiceType.NEW_CHAT_MEMBERS:
            return

        if not message.chat or not message.new_chat_members:
            return

        assert message.chat.id
        chat_id = message.chat.id

        if chat_id not in CHAT_WHITELIST:
            return

        me = await app.get_chat_member(chat_id, "me")
        if me.status not in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }:
            logger.warning("Bot is not admin in chat %d", chat_id)
            return

        for user in message.new_chat_members:
            if user.is_bot:
                continue

            expected = random.randint(100000, 999999)

            challenge = await app.send_message(
                chat_id,
                (
                    f"Welcome, "
                    f"[{user.full_name}](tg://user?id={user.id})!\n\n"
                    f"Please reply to this message with:\n\n"
                    f"{expected}\n\n"
                    f"You have {TIMEOUT_SECONDS} seconds before you're kicked."
                ),
            )

            expires_at = time.time() + TIMEOUT_SECONDS

            self._save_user_record(
                chat_id,
                user.id,
                expected=expected,
                challenge_message_id=challenge.id,
                expires_at=expires_at,
            )

            asyncio.create_task(
                self.kicker(
                    TIMEOUT_SECONDS,
                    chat_id,
                    user.id,
                )
            )

    async def verifyhandler(self, app: Client, message: Message) -> None:
        if not message.chat or not message.from_user or not message.text:
            return

        assert message.chat.id
        chat_id = message.chat.id
        user_id = message.from_user.id

        record = self._get_user_record(chat_id, user_id)
        if record is None:
            return

        if not message.reply_to_message:
            return

        if message.reply_to_message.id != record["challenge_message_id"]:
            return

        if message.text.strip() != str(record["expected"]):
            await message.reply("__wrong code.__")
            return

        await message.reply("__Verification successful. Welcome!__")

        self._delete_user_record(chat_id, user_id)

        logger.info(
            "User %d successfully completed captcha in chat %d",
            user_id,
            chat_id,
        )

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        return RegisterHandlersResult(
            group=6,
            handlers=[
                MessageHandler(self.joinhandler, filters.service),
                MessageHandler(self.verifyhandler, filters.text),
            ],
        )
