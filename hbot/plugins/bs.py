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
import json
import logging
import random
import time
from typing import override

from anyio import NamedTemporaryFile
from jsondb.database import JsonDB
from pyrogram.client import Client
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR
from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

SCORE_INITIAL_CONSTANT = 1.0
SCORE_INCREMENT_CONSTANT = 0.15
_DB_TTL_SECONDS = 10

logger = logging.getLogger(__name__)


class BsPlugin(BasePlugin):
    name: str = "Artificial Intelligence"
    description: str = "Yo homemade AI."

    def __init__(self, app: Client) -> None:
        self.app: Client = app
        self._db_instance: JsonDB | None = None
        self._db_ttl_handle: asyncio.TimerHandle | None = None
        self._db_opening: bool = False

    # --- TTL-cached database ----------------------------------------------------
    #
    # All Pyrogram handlers run as coroutines on a single asyncio event loop.
    # Accessing `_db` from a coroutine is therefore always on that same thread,
    # so no locking is required.  We use asyncio.get_running_loop().call_later()
    # to schedule eviction — it is safe to call from within a running coroutine
    # and operates entirely within the event loop.

    def _evict_db(self) -> None:
        """Drop the cached JsonDB instance after the TTL expires."""
        logger.debug("bs: JsonDB TTL expired — evicting cached instance")
        self._db_ttl_handle = None
        if self._db_instance is not None:
            try:
                self._db_instance.close()
            except Exception:
                logger.exception("bs: error closing JsonDB during eviction")
            self._db_instance = None

    @property
    def _db(self) -> JsonDB:
        """Return the JsonDB instance, (re-)starting the 10-second eviction timer.

        - On first access (or after eviction): opens the database file.
        - On every subsequent access: cancels the pending eviction and schedules
          a fresh one, so the DB stays alive as long as it is actively used.
        - Guards against re-entrant construction: if an instance is already being
          opened, returns the in-progress instance once it is set.
        """
        if self._db_instance is None and not self._db_opening:
            logger.debug("bs: opening JsonDB (lazy / post-eviction load)")
            self._db_opening = True
            try:
                self._db_instance = JsonDB(__name__, PERSIST_DIR)
            finally:
                self._db_opening = False

        # Cancel any in-flight eviction timer and start a fresh one.
        if self._db_ttl_handle is not None:
            self._db_ttl_handle.cancel()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — this should not happen inside a Pyrogram handler,
            # but guard defensively so the property never raises unexpectedly.
            logger.warning("bs: _db accessed outside of a running event loop; TTL timer not scheduled")
        else:
            self._db_ttl_handle = loop.call_later(_DB_TTL_SECONDS, self._evict_db)

        return self._db_instance

    # --- whitelist helpers (no duplicate in-memory copy) ------------------------

    def _get_whitelist(self) -> list[int]:
        return self._db.data.get("whitelist", [])

    def _set_whitelist(self, whitelist: list[int]) -> None:
        self._db.data.update({"whitelist": whitelist})

    # --- word-score helpers (plain dict[str, float] per chat) -------------------

    def _get_scores(self, chat_id: int) -> dict[str, float]:
        """Return the word-score mapping for *chat_id* (empty dict if unseen).

        Also performs a one-time cleanup of the legacy 'word_list' key if it
        exists inside a chat's data blob, preventing TypeError crashes when
        its list value ends up mixed in with float scores.
        """
        raw: dict = dict(self._db.data.get(str(chat_id), {}))

        # One-time migration: drop the old 'word_list' key left over from the
        # pre-refactor DataEntry/WordEntry schema.
        if "word_list" in raw:
            logger.warning("chat %d: removing legacy 'word_list' key from scores dict", chat_id)
            raw.pop("word_list")
            self._db.data.update({str(chat_id): raw})

        # Defensively filter out any remaining non-numeric values so a stale DB
        # can never cause a TypeError in generate_bs.
        return {k: v for k, v in raw.items() if isinstance(v, (int, float))}

    def _set_scores(self, chat_id: int, scores: dict[str, float]) -> None:
        self._db.data.update({str(chat_id): scores})

    # --- internal update (shared by listener and train_from_history) ------------

    def _apply_text(self, scores: dict[str, float], text: str) -> None:
        """Update *scores* in-place from the words in *text*."""
        for word in text.replace("\n", " ").split(" "):
            if not word:
                continue
            if word in scores:
                logger.info(
                    "incrementing score for word %s from %f to %f",
                    word,
                    scores[word],
                    scores[word] + SCORE_INCREMENT_CONSTANT,
                )
                scores[word] += SCORE_INCREMENT_CONSTANT
            else:
                logger.info(
                    "creating new entry for word %s with score of %f",
                    word,
                    SCORE_INITIAL_CONSTANT,
                )
                scores[word] = SCORE_INITIAL_CONSTANT

    # --- handlers ---------------------------------------------------------------

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
            logger.info("chat %d is not in whitelist, ignoring", message.chat.id)
            return

        logger.info("chat %d is in whitelist, processing", message.chat.id)

        scores = self._get_scores(message.chat.id)
        self._apply_text(scores, text)
        self._set_scores(message.chat.id, scores)

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
        self._set_whitelist(whitelist)
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
        self._set_whitelist(whitelist)
        await message.reply_text("__bs is now disabled for this chat__")

    async def generate_bs(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id

        bs_word_count = random.randint(20, 50)  # noqa: S311
        scores = self._get_scores(message.chat.id)

        if not scores:
            await message.reply_text("__no data for this chat yet!__")
            return

        words, weights = zip(*scores.items(), strict=False)
        sentence_words = random.choices(list(words), list(weights), k=bs_word_count)  # noqa: S311
        sentence = " ".join(sentence_words)
        logger.info("constructed bs sentence for chat %d is: %s", message.chat.id, sentence)
        await message.reply_text(f"__{sentence}__")

    async def get_chat_bs(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id

        scores = self._get_scores(message.chat.id)

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

        logger.info(
            "--- TRAINING FROM CHAT HISTORY OF %d (limit=%d) ---",
            message.chat.id,
            limit,
        )
        limit_str = str(limit) if limit else "no limit"
        msg = await message.reply_text(f"__training from chat history (limit: {limit_str}), this may take a while!__")
        start_time = time.perf_counter()

        # Accumulate all updates in a local dict — one db write at the end.
        scores = self._get_scores(message.chat.id)
        count = 0
        async for m in app.get_chat_history(message.chat.id, limit=limit or 0):
            if m.text is None and m.caption is None:
                continue
            text = m.text or m.caption or ""
            self._apply_text(scores, text)
            count += 1

        self._set_scores(message.chat.id, scores)

        end_time = time.perf_counter()
        time_delta = end_time - start_time
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

        db_data: dict = dict(self._db.data)

        # Collect keys that look like chat IDs (integer strings) and have score data
        chat_ids: list[int] = []
        for key in db_data:
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
    def register_handlers(self) -> RegisterHandlersResult:
        # Build a filter that matches any command this plugin handles, so the
        # passive listener never ingests bot commands as training words.
        # command_filter = filters.command(
        #     [
        #         "enablebs",
        #         "disablebs",
        #         "generatebs",
        #         "gbs",
        #         "getchatbs",
        #         "gcbs",
        #         "trainfromhistory",
        #         "tfh",
        #         "lsbschat",
        #     ],
        #     prefixes=self.prefixes,
        # )
        # listener_filter = (filters.text | filters.caption) & ~command_filter
        #
        # return RegisterHandlersResult(
        #     group=5,
        #     handlers=[
        #         MessageHandler(self.enable_bs, filters.command("enablebs", prefixes=self.prefixes)),
        #         MessageHandler(
        #             self.disable_bs,
        #             filters.command("disablebs", prefixes=self.prefixes),
        #         ),
        #         MessageHandler(
        #             self.generate_bs,
        #             filters.command(["generatebs", "gbs"], prefixes=self.prefixes),
        #         ),
        #         MessageHandler(
        #             self.get_chat_bs,
        #             filters.command(["getchatbs", "gcbs"], prefixes=self.prefixes),
        #         ),
        #         MessageHandler(
        #             self.train_from_history,
        #             filters.command(["trainfromhistory", "tfh"], prefixes=self.prefixes),
        #         ),
        #         MessageHandler(
        #             self.list_bs_chats,
        #             filters.command("lsbschat", prefixes=self.prefixes),
        #         ),
        #         MessageHandler(self.listener, listener_filter),
        #         EditedMessageHandler(self.listener, listener_filter),
        #     ],
        # )
        return RegisterHandlersResult([])
