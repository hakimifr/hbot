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
import os
import sys
import time
from base64 import b64decode
from pathlib import Path

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.errors import SessionPasswordNeeded
from pyrogram.handlers.handler import Handler
from pyrogram.sync import idle
from pyrogram.types import Message

from hbot import BOTAUTHTOKEN, BOTOWNERID, PERSIST_DIR, PHONENUMBER, PLUGINS_DIR
from hbot.core.base_plugin import BasePlugin
from hbot.core.plugins_loader import load_plugins

logger = logging.getLogger(__name__)
loaded_plugins: dict[BasePlugin, list[Handler]] = {}
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")

if api_id is None or api_hash is None:
    logger.critical("API_ID and API_HASH must be exported!")
    sys.exit(1)

if not (PERSIST_DIR.exists() and PERSIST_DIR.is_dir()):
    logger.critical("PERSIST_DIR '%s' does not exist!", PERSIST_DIR.as_posix())
    sys.exit(1)


async def get_loaded_plugins() -> dict[BasePlugin, list[Handler]]:
    return loaded_plugins


async def generate_new_session(session_file: Path) -> None:
    """Create new session and store it into session_file"""
    session_file.unlink(True)

    app: Client = Client("hbot", api_id, api_hash, phone_number=PHONENUMBER, in_memory=True)
    bot: Client = Client("authbot", api_id, api_hash, bot_token=BOTAUTHTOKEN)

    await app.connect()
    sent_code = await app.send_code(PHONENUMBER)

    await bot.start()
    await bot.send_message(int(BOTOWNERID), "enter the code sent by telegram")

    code_received: bool = False
    code: int | None = None

    @bot.on_message(filters.text, group=1)
    async def code_handler(client: Client, message: Message) -> None:
        nonlocal code_received
        nonlocal code

        if code_received:
            return

        assert message.chat
        assert message.chat.id
        if message.chat.id != int(BOTOWNERID):
            return

        assert message.text
        code = b64decode(message.text).decode().strip()
        code_received = True

    start = time.perf_counter()
    while True:
        if code_received:
            break

        elapsed = time.perf_counter() - start
        if elapsed < (5 * 60):
            await asyncio.sleep(0.3)
        else:
            logger.critical("no code were received to generate new session.")

    await bot.send_message(int(BOTOWNERID), "Enter 2fa password, or just type none")

    password_received: bool = False
    password: str | None = None

    @bot.on_message(filters.text, group=2)
    async def password_handler(client: Client, message: Message) -> None:
        nonlocal password_received
        nonlocal password

        assert message.chat
        assert message.chat.id
        if message.chat.id != int(BOTOWNERID):
            return

        assert message.text
        password = b64decode(message.text).decode().strip()
        password_received = True

    start = time.perf_counter()
    while True:
        if password_received:
            break

        elapsed = time.perf_counter() - start
        if elapsed < (5 * 60):
            await asyncio.sleep(0.3)
        else:
            try:
                raise RuntimeError("no password were received to generate new session.")
            except RuntimeError:
                logger.exception()
                raise

    try:
        await app.sign_in(PHONENUMBER, sent_code.phone_code_hash, code)
    except SessionPasswordNeeded:
        await app.check_password(password)

    with session_file.open("w", encoding="utf-8") as f:
        f.write(await app.export_session_string())

    logger.info("new session created successfully")


async def main() -> None:
    """Entry point of the bot."""
    global loaded_plugins

    session_file = Path(PERSIST_DIR).joinpath("hbot.session")
    if not session_file.exists():
        await generate_new_session(session_file)

    while True:
        with session_file.open("r", encoding="utf-8") as f:
            app = Client("hbot", api_id, api_hash, session_string=f.read())

        try:
            await app.connect()
            await app.disconnect()
            break
        except:
            logger.exception("problem with session file. generating new session.")
            await generate_new_session(session_file)

    logger.info("loading plugins from %s", PLUGINS_DIR)
    loaded_plugins = await load_plugins(app, PLUGINS_DIR)

    try:
        await app.start()
        await idle()
    except ConnectionError:  # app.start() already called by other plugins (rm6785)
        await idle()
    finally:
        await app.stop()
        sys.exit(0)
