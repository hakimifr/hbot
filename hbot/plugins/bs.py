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
import json
import logging
import random
import time
from dataclasses import asdict, dataclass
from typing import override

from anyio import NamedTemporaryFile
from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.edited_message_handler import EditedMessageHandler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message
from pyrogram.types.user_and_chats import Chat, User

from hbot import PERSIST_DIR
from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult
from hbot.core.utils import from_dict

SCORE_INITIAL_CONSTANT = 1.0
SCORE_INCREMENT_CONSTANT = 0.15

logger = logging.getLogger(__name__)
db = JsonDB(__name__, PERSIST_DIR)


@dataclass
class WordEntry:
    word: str
    score: float


@dataclass
class DataEntry:
    word_list: list[WordEntry]


class BsPlugin(BasePlugin):
    name: str = "Artificial Intelligence"
    description: str = "Yo homemade AI."

    def __init__(self, app: Client) -> None:
        self.app: Client = app
        self.whitelist: list[int] = db.data.get("whitelist", [])

    async def ping(self, app: Client, message: Message) -> None:
        logger.debug("ping, pong!")
        await message.edit_text("Pong!")

    async def listener(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id

        if message.caption:
            assert message.caption
            text = message.caption
        else:
            assert message.text
            text = message.text

        if message.chat.id not in self.whitelist:
            logger.info("chat %d is not in whitelist, ignoring", message.chat.id)
            return

        logger.info("chat %d is in whitelist, processing", message.chat.id)

        dbentry: DataEntry = from_dict(DataEntry, db.data.get(str(message.chat.id), asdict(DataEntry([]))))
        words = text.replace("\n", " ").split(" ")

        for word in words:
            for w in dbentry.word_list:
                if word == w.word:
                    logger.info(
                        "incrementing score for word %s from %f to %f",
                        w.word,
                        w.score,
                        w.score + SCORE_INCREMENT_CONSTANT,
                    )
                    w.score += SCORE_INCREMENT_CONSTANT
                    break
            else:
                logger.info("creating new entry for word %s with score of %f", word, SCORE_INITIAL_CONSTANT)
                dbentry.word_list.append(WordEntry(word, SCORE_INITIAL_CONSTANT))

        db.data.update({str(message.chat.id): asdict(dbentry)})

    async def enable_bs(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id
        assert message.from_user
        assert app.me

        if message.from_user.id != app.me.id and not await self.is_user_admin(app, message.chat, message.from_user):
            await message.reply_text("__you need to be admin!__")
            return

        if message.chat.id in self.whitelist:
            logger.info("will not enable bs for chat %d; already enabled", message.chat.id)
            await message.reply_text("__already enabled for this chat__")
            return

        logger.info("enabling bs for chat %d", message.chat.id)
        self.whitelist.append(message.chat.id)
        db.data.update({"whitelist": self.whitelist})
        await message.reply_text("__bs is now enabled for this chat__")

    async def disable_bs(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id
        assert message.from_user
        assert app.me

        if message.from_user.id != app.me.id and not await self.is_user_admin(app, message.chat, message.from_user):
            await message.reply_text("__you need to be admin!__")
            return

        if message.chat.id not in self.whitelist:
            logger.info("will not disable bs for chat %d; already disabled", message.chat.id)
            await message.reply_text("__already disabled for this chat__")
            return

        logger.info("disabling bs for chat %d", message.chat.id)
        self.whitelist.remove(message.chat.id)
        db.data.update({"whitelist": self.whitelist})
        await message.reply_text("__bs is now disabled for this chat__")

    async def generate_bs(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id

        bs_word_count = random.randint(20, 50)  # noqa: S311
        dbentry: DataEntry = from_dict(DataEntry, db.data.get(str(message.chat.id), asdict(DataEntry([]))))

        words = []
        weights = []

        for word in dbentry.word_list:
            words.append(word.word)
            weights.append(word.score)

        sentence_words = random.choices(words, weights, k=bs_word_count)  # noqa: S311
        sentence = " ".join(sentence_words)
        logger.info("constructed bs sentence for chat %d is: %s", message.chat.id, sentence)
        await message.reply_text(f"__{sentence}__")

    async def get_chat_bs(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id

        dbentry: dict = db.data.get(str(message.chat.id), asdict(DataEntry([])))

        async with NamedTemporaryFile("w+", suffix=".json") as f:
            await f.write(json.dumps(dbentry, indent=2))
            await f.flush()
            await message.reply_document(f.wrapped.name)

    async def train_from_history(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.chat.id
        assert message.from_user
        assert app.me

        if message.from_user.id != app.me.id and not await self.is_user_admin(app, message.chat, message.from_user):
            await message.reply_text("__you need to be admin!__")
            return

        logger.info("--- TRAINING FROM THE WHOLE CHAT HISTORY OF %d ---", message.chat.id)
        msg = await message.reply_text("__training from the whole chat history, this may take a while!__")
        start_time = time.perf_counter()

        async for m in app.get_chat_history(message.chat.id):
            if all((m.text is None, m.caption is None)):
                continue
            await self.listener(app, m)

        end_time = time.perf_counter()
        time_delta = end_time - start_time
        logger.info("--- TRAINING DONE ---\ntook %f seconds", time_delta)
        await msg.edit_text(f"__training done. took {time_delta} seconds__")

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        return RegisterHandlersResult(
            group=5,
            handlers=[
                MessageHandler(self.enable_bs, filters.command("enablebs", prefixes=self.prefixes)),
                MessageHandler(self.disable_bs, filters.command("disablebs", prefixes=self.prefixes)),
                MessageHandler(self.generate_bs, filters.command(["generatebs", "gbs"], prefixes=self.prefixes)),
                MessageHandler(self.get_chat_bs, filters.command(["getchatbs", "gcbs"], prefixes=self.prefixes)),
                MessageHandler(
                    self.train_from_history, filters.command(["trainfromhistory", "tfh"], prefixes=self.prefixes)
                ),
                MessageHandler(self.listener, filters.text),
                EditedMessageHandler(self.listener, filters.text),
            ],
        )
