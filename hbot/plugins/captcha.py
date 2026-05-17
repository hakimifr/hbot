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
from datetime import datetime, timedelta
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
    -1002237651092,  # disc
    -1001754321934,  # community
    -1001309495065,  # r6
]
TIMEOUT_SECONDS = 60
TEMP_BAN_SECONDS = 21600
MAX_FAIL_BEFORE_TEMPBAN = 6
FAILURE_TRACKER_KEY = "__failures__"

logger = logging.getLogger(__name__)
db = JsonDB(__name__, PERSIST_DIR)
# Structure:
# {
#     "chat_id": {
#         "user_id": {
#             "expected": 123456,
#             "challenge_message_id": 42,
#             "expires_at": 1778400000.123,
#         },
#         ...,
#         "__failures__": {
#             "user_id": consecutive_failure_count,
#         }
#     },
# }


class CaptchaPlugin(BasePlugin):
    name: str = "Captcha Plugin"
    description: str = "Require new members to solve a 6-digit captcha."

    def __init__(self, app: Client) -> None:
        self.app = app

        loop = asyncio.get_event_loop()
        scheduled_count = 0

        for chat_id_str, users in db.data.items():
            if not chat_id_str.lstrip("-").isdigit():
                continue

            if not isinstance(users, dict):
                continue

            for user_id_str, payload in users.items():
                if user_id_str == FAILURE_TRACKER_KEY:
                    continue

                if not user_id_str.lstrip("-").isdigit():
                    continue

                if not isinstance(payload, dict):
                    continue

                if "expires_at" not in payload:
                    continue

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
                scheduled_count += 1

        logger.info("Captcha plugin initialized; restored %d pending kicker tasks", scheduled_count)

    def _get_failures_bucket(self, chat_id: int, *, create: bool = False) -> dict | None:
        chat_key = str(chat_id)
        chat = db.data.get(chat_key)

        if chat is None:
            if not create:
                return None
            db.data[chat_key] = {}
            chat = db.data[chat_key]

        if not isinstance(chat, dict):
            return None

        failures = chat.get(FAILURE_TRACKER_KEY)

        if failures is None:
            if not create:
                return None
            chat[FAILURE_TRACKER_KEY] = {}
            failures = chat[FAILURE_TRACKER_KEY]

        if not isinstance(failures, dict):
            return None

        return failures

    def _increment_consecutive_failures(self, chat_id: int, user_id: int) -> int:
        failures = self._get_failures_bucket(chat_id, create=True)
        assert failures is not None

        user_key = str(user_id)
        failures[user_key] = int(failures.get(user_key, 0)) + 1
        db.write_database()
        logger.info(
            "Incremented consecutive failures to %d for user %d in chat %d",
            failures[user_key],
            user_id,
            chat_id,
        )

        return failures[user_key]

    def _reset_consecutive_failures(self, chat_id: int, user_id: int) -> None:
        failures = self._get_failures_bucket(chat_id)
        if failures is None:
            return

        failures.pop(str(user_id), None)
        db.write_database()
        logger.info("Reset consecutive failures for user %d in chat %d", user_id, chat_id)

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
        logger.info(
            "Saved captcha record for user %d in chat %d (challenge_message_id=%d, expires_at=%.3f)",
            user_id,
            chat_id,
            challenge_message_id,
            expires_at,
        )

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
        logger.info("Deleted captcha record for user %d in chat %d", user_id, chat_id)

    async def kicker(self, after: float | int, chat_id: int, user_id: int) -> None:
        logger.info(
            "Scheduled kicker for user %d in chat %d after %.3f seconds",
            user_id,
            chat_id,
            float(after),
        )
        await asyncio.sleep(after)

        if self._get_user_record(chat_id, user_id) is None:
            logger.info(
                "Skipping kicker for user %d in chat %d because captcha record no longer exists",
                user_id,
                chat_id,
            )
            return

        try:
            member = await self.app.get_chat_member(chat_id, user_id)
            failures = self._increment_consecutive_failures(chat_id, user_id)
            logger.info(
                "Captcha timeout for user %d in chat %d; consecutive failures=%d",
                user_id,
                chat_id,
                failures,
            )

            if failures >= MAX_FAIL_BEFORE_TEMPBAN:
                until_date = datetime.now() + timedelta(seconds=TEMP_BAN_SECONDS)
                await self.app.ban_chat_member(
                    chat_id,
                    user_id,
                    until_date=until_date,
                )
                await self.app.send_message(
                    chat_id,
                    (
                        f"__temporarily banned "
                        f"[{member.user.full_name}](tg://user?id={user_id}) "
                        f"for 6 hours after {MAX_FAIL_BEFORE_TEMPBAN} consecutive failed verifications.__"
                    ),
                )
                logger.info(
                    "user %d failed captcha for MAX_FAIL_BEFORE_TEMPBAN (%d) times",
                    user_id,
                    MAX_FAIL_BEFORE_TEMPBAN,
                )
                logger.info(
                    "applied 6-hour temp ban to user %d in chat %d until %s after timeout",
                    user_id,
                    chat_id,
                    until_date,
                )
            else:
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
                logger.info(
                    "Kicked user %d from chat %d due to captcha timeout (consecutive failures=%d)",
                    user_id,
                    chat_id,
                    failures,
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
        logger.info(
            "Processing new chat members event in chat %d with %d members",
            chat_id,
            len(message.new_chat_members),
        )

        me = await app.get_chat_member(chat_id, "me")
        if me.status not in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }:
            logger.warning("Bot is not admin in chat %d", chat_id)
            return

        for user in message.new_chat_members:
            if user.is_bot:
                logger.info("Skipping captcha for bot user %d in chat %d", user.id, chat_id)
                continue

            expected = random.randint(100000, 999999)  # noqa: S311

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
            logger.info(
                "Issued captcha challenge for user %d in chat %d (challenge_message_id=%d)",
                user.id,
                chat_id,
                challenge.id,
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
            logger.info(
                "Started kicker timer for user %d in chat %d with timeout=%d",
                user.id,
                chat_id,
                TIMEOUT_SECONDS,
            )

    async def verifyhandler(self, app: Client, message: Message) -> None:
        if not message.chat or not message.from_user or not message.text:
            return

        assert message.chat.id
        chat_id = message.chat.id
        user_id = message.from_user.id
        logger.info("Received verification message from user %d in chat %d", user_id, chat_id)

        record = self._get_user_record(chat_id, user_id)
        if record is None:
            logger.info(
                "Ignoring verification message from user %d in chat %d because no captcha record exists",
                user_id,
                chat_id,
            )
            return

        if not message.reply_to_message:
            logger.info(
                "Ignoring verification message from user %d in chat %d because it is not a reply",
                user_id,
                chat_id,
            )
            return

        if message.reply_to_message.id != record["challenge_message_id"]:
            logger.info(
                "Ignoring verification message from user %d in chat %d because reply message id %d does not match challenge id %d",  # noqa: E501
                user_id,
                chat_id,
                message.reply_to_message.id,
                record["challenge_message_id"],
            )
            return

        if message.text.strip() != str(record["expected"]):
            await message.reply("__wrong code.__")
            logger.info(
                "User %d submitted wrong captcha in chat %d; retries allowed and consecutive failures unchanged",
                user_id,
                chat_id,
            )
            return

        await message.reply("__Verification successful. Welcome!__")
        logger.info("User %d solved captcha in chat %d", user_id, chat_id)

        self._reset_consecutive_failures(chat_id, user_id)
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
