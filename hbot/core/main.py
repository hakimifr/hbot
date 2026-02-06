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
import os
import sys

from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.sync import idle

from hbot import PERSIST_DIR, PLUGINS_DIR
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


async def main() -> None:
    """Entry point of the bot."""
    global loaded_plugins
    app = Client("hbot", api_id, api_hash)

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
