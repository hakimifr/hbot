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
import heapq
import json
import logging
import random
import time
from typing import Any, override

from anyio import NamedTemporaryFile
from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.edited_message_handler import EditedMessageHandler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR
from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

SCORE_INITIAL_CONSTANT = 1.0
SCORE_INCREMENT_CONSTANT = 0.15
MAX_WORD_LENGTH = 40
MAX_WORDS_PER_CHAT = 50_000
PRUNE_TARGET = 45_000
FLUSH_INTERVAL_SECONDS = 300

logger = logging.getLogger(__name__)
db: JsonDB = JsonDB(__name__, PERSIST_DIR)


class BsPlugin(BasePlugin):
    name: str = "Artificial Intelligence"
    description: str = "Yo homemade AI."

    def __init__(self, app: Client) -> None:
        super().__init__(app)
        self._dirty: bool = False
        self._flush_task: asyncio.Task[None] | None = None

        if self._cleanup_db():
            db.write_database()

    @staticmethod
    def _prune(scores: dict[str, float]) -> None:
        """Drop the lowest-scored words until *scores* is down to PRUNE_TARGET.

        heapq.nsmallest is stable, so among equal scores the oldest entries
        (first inserted) are dropped first.
        """
        excess = len(scores) - PRUNE_TARGET
        for word, _score in heapq.nsmallest(excess, scores.items(), key=lambda item: item[1]):
            del scores[word]

    def _cleanup_db(self) -> bool:
        """One-time cleanup: drop the legacy 'word_list' key and non-numeric values.

        Returns True if anything was changed.
        """
        changed = False

        for key in list(db.data):
            if key == "whitelist":
                continue

            chat: dict[str, Any] = db.data.get(key)
            if not isinstance(chat, dict):
                continue

            if "word_list" in chat:
                logger.warning("chat %s: removing legacy 'word_list' key from scores dict", key)
                del chat["word_list"]
                changed = True

            for word in list(chat):
                if not isinstance(chat[word], int | float):
                    del chat[word]
                    changed = True

            if len(chat) > MAX_WORDS_PER_CHAT:
                self._prune(chat)
                changed = True

        return changed

    def _get_whitelist(self) -> list[int]:
        whitelist: list[int] = db.data.setdefault("whitelist", [])
        return whitelist

    def _apply_text(self, chat_id: int, text: str) -> None:
        scores: dict[str, float] = db.data.setdefault(str(chat_id), {})
        for word in text.replace("\n", " ").split(" "):
            if not word or len(word) > MAX_WORD_LENGTH:
                continue

            if word in scores:
                scores[word] += SCORE_INCREMENT_CONSTANT
            else:
                scores[word] = SCORE_INITIAL_CONSTANT

        self._dirty = True

        if len(scores) > MAX_WORDS_PER_CHAT:
            self._prune(scores)

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
            if self._dirty:
                db.write_database()
                self._dirty = False

    async def listener(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id

        text: str
        if message.caption:
            text = message.caption
        elif message.text:
            text = message.text
        else:
            return

        if message.chat.id not in self._get_whitelist():
            return

        self._apply_text(message.chat.id, text)

    async def enable_bs(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id
        assert message.from_user
        assert app.me

        if message.from_user.id != app.me.id and not await self.is_user_admin(app, message.chat, message.from_user):
            await message.reply_text("__you need to be admin!__")
            return

        whitelist = self._get_whitelist()
        if message.chat.id in whitelist:
            logger.info("will not enable bs for chat %d; already enabled", message.chat.id)
            await message.reply_text("__already enabled for this chat__")
            return

        logger.info("enabling bs for chat %d", message.chat.id)
        whitelist.append(message.chat.id)
        db.write_database()
        self._dirty = False
        await message.reply_text("__bs is now enabled for this chat__")

    async def disable_bs(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id
        assert message.from_user
        assert app.me

        if message.from_user.id != app.me.id and not await self.is_user_admin(app, message.chat, message.from_user):
            await message.reply_text("__you need to be admin!__")
            return

        whitelist = self._get_whitelist()
        if message.chat.id not in whitelist:
            logger.info("will not disable bs for chat %d; already disabled", message.chat.id)
            await message.reply_text("__already disabled for this chat__")
            return

        logger.info("disabling bs for chat %d", message.chat.id)
        whitelist.remove(message.chat.id)
        db.write_database()
        self._dirty = False
        await message.reply_text("__bs is now disabled for this chat__")

    async def generate_bs(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id

        bs_word_count = random.randint(20, 50)  # noqa: S311
        scores: dict[str, float] = db.data.get(str(message.chat.id), {})

        if not scores:
            await message.reply_text("__no data for this chat yet!__")
            return

        sentence_words = random.choices(list(scores), weights=list(scores.values()), k=bs_word_count)  # noqa: S311
        sentence = " ".join(sentence_words)
        logger.info("constructed bs sentence for chat %d is: %s", message.chat.id, sentence)
        await message.reply_text(f"__{sentence}__")

    async def get_chat_bs(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id

        scores: dict[str, float] = db.data.get(str(message.chat.id), {})

        async with NamedTemporaryFile("w+", suffix=".json") as f:
            await f.write(json.dumps(scores, indent=2))
            await f.flush()
            await message.reply_document(f.wrapped.name)

    async def train_from_history(self, app: Client, message: Message, limit: int = 0) -> None:
        """Train from the chat's message history.

        Args:
            app: The Pyrogram client.
            message: The triggering message.
            limit: Maximum number of historical messages to process.
                0 (default) means no limit — process the entire history.
        """
        assert message.chat
        assert message.chat.id
        assert message.from_user
        assert app.me

        if message.from_user.id != app.me.id and not await self.is_user_admin(app, message.chat, message.from_user):
            await message.reply_text("__you need to be admin!__")
            return

        # Parse optional inline limit: e.g. "/tfh 5000"
        if message.text:
            parts = message.text.strip().split()
            if len(parts) >= 2:
                try:
                    limit = int(parts[1])
                except ValueError:
                    pass

        logger.info("--- TRAINING FROM CHAT HISTORY OF %d (limit=%d) ---", message.chat.id, limit)
        limit_str = str(limit) if limit else "no limit"
        msg = await message.reply_text(f"__training from chat history (limit: {limit_str}), this may take a while!__")
        start_time = time.perf_counter()

        count = 0
        async for m in app.get_chat_history(message.chat.id, limit=limit or 0):
            if m.text is None and m.caption is None:
                continue
            self._apply_text(message.chat.id, m.text or m.caption or "")
            count += 1

        db.write_database()
        self._dirty = False

        time_delta = time.perf_counter() - start_time
        logger.info("--- TRAINING DONE ---\ntook %f seconds (%d messages)", time_delta, count)
        await msg.edit_text(f"__training done. processed {count} messages in {time_delta:.2f}s__")

    async def list_bs_chats(self, app: Client, message: Message) -> None:
        """List all chats that have stored bs data in the JsonDB."""
        assert message.chat
        assert message.chat.id
        assert message.from_user
        assert app.me

        if message.from_user.id != app.me.id and not await self.is_user_admin(app, message.chat, message.from_user):
            await message.reply_text("__you need to be admin!__")
            return

        chat_ids: list[int] = []
        for key in db.data:
            if key == "whitelist":
                continue
            try:
                chat_ids.append(int(key))
            except ValueError:
                continue

        if not chat_ids:
            await message.reply_text("__no chats with bs data found!__")
            return

        lines: list[str] = ["**Chats with bs data:**\n"]
        for chat_id in chat_ids:
            try:
                chat = await app.get_chat(chat_id)
            except Exception:
                logger.warning("list_bs_chats: could not fetch chat info for %d", chat_id)
                lines.append(f"• Unknown (ID: `{chat_id}`) — could not fetch info")
                continue

            title: str = getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(chat_id)
            username: str | None = getattr(chat, "username", None)

            if username:
                link = f"t.me/{username}"
            else:
                # Strip leading minus for supergroup/channel IDs in t.me links
                tme_id = str(chat_id).lstrip("-")
                # Supergroup/channel IDs prefixed with 100 — strip that prefix
                if tme_id.startswith("100"):
                    tme_id = tme_id[3:]
                link = f"t.me/c/{tme_id}/1"

            lines.append(f"• **{title}** | ID: `{chat_id}` | {link}")

        await message.reply_text("\n".join(lines))

    @override
    async def register_handlers(self) -> RegisterHandlersResult:
        self._flush_task = asyncio.create_task(self._flush_loop())

        command_filter = filters.command(
            [
                "enablebs",
                "disablebs",
                "generatebs",
                "gbs",
                "getchatbs",
                "gcbs",
                "trainfromhistory",
                "tfh",
                "lsbschat",
            ],
            prefixes=self.prefixes,
        )
        listener_filter = (filters.text | filters.caption) & ~command_filter

        return RegisterHandlersResult(
            group=5,
            handlers=[
                MessageHandler(self.enable_bs, filters.command("enablebs", prefixes=self.prefixes)),
                MessageHandler(self.disable_bs, filters.command("disablebs", prefixes=self.prefixes)),
                MessageHandler(self.generate_bs, filters.command(["generatebs", "gbs"], prefixes=self.prefixes)),
                MessageHandler(self.get_chat_bs, filters.command(["getchatbs", "gcbs"], prefixes=self.prefixes)),
                MessageHandler(
                    self.train_from_history,
                    filters.command(["trainfromhistory", "tfh"], prefixes=self.prefixes),
                ),
                MessageHandler(self.list_bs_chats, filters.command("lsbschat", prefixes=self.prefixes)),
                MessageHandler(self.listener, listener_filter),
                EditedMessageHandler(self.listener, listener_filter),
            ],
        )
