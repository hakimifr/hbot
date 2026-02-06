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
from typing import cast, override

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult
from hbot.core.main import get_loaded_plugins

logger = logging.getLogger(__name__)


class MyPlugin(BasePlugin):
    name: str = "Help Plugin"
    description: str = "Return bot usage."

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def help(self, app: Client, message: Message) -> None:
        logger.info("generating help text for loaded plugins")
        loaded_plugins: dict[BasePlugin, list[Handler]] = await get_loaded_plugins()
        help_string: str = "**🤖 Bot Commands**\n\n"

        # This whole thing is very hacky because pyrogram does not provide
        # an easy way to access the bound handler/filter. I had to study the
        # pyrogram's source code just to write this.
        for plugin, handlers in loaded_plugins.items():
            logger.info("processing plugin '%s' for help text", plugin.name)
            help_string += f"**📦 {plugin.name}**\n"
            help_string += f"__{plugin.description}__\n"

            commands = []
            for h in handlers:
                a = []
                if b := getattr(h.filters, "base", None):
                    a.append(b)
                if b := getattr(h.filters, "other", None):
                    a.append(b)
                if not getattr(h.filters, "base", None) and not getattr(h.filters, "other", None):
                    a.append(h.filters)
                for x in a:  # type: ignore
                    if type(x).__name__ == "CommandFilter":
                        x.commands = cast(set, x.commands)
                        for cmd in x.commands:
                            logger.info("found command '%s' for plugin '%s'", cmd, plugin.name)
                            commands.append(f"  • `{cmd}`")

            if commands:
                help_string += "\n".join(commands) + "\n"
            else:
                help_string += "  __No commands available__\n"

            help_string += "\n"

        logger.info("help text generated successfully")
        await message.edit_text(help_string)

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        return RegisterHandlersResult(
            handlers=[
                MessageHandler(
                    self.help,
                    filters.command("help", prefixes=self.prefixes) & filters.me,
                ),
            ]
        )
