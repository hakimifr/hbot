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
from abc import ABC, abstractmethod
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import final

from jsondb.database import JsonDB
from pyrogram.client import Client
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.handlers.handler import Handler
from pyrogram.types import Chat, User
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR

logger = logging.getLogger(__name__)


@dataclass
class RegisterHandlersResult:
    """The dataclass that your plugin's :ref:`register_handlers()` method must return."""

    handlers: list[Handler]
    group: int = 0


class BasePlugin(ABC):
    """The core to every plugins in this bot.

    When :py:meth:`load_plugins()` is called to load plugins, it finds plugin in the plugins/ directory,
    and calls the :py:meth:`register_handler()` method in any class that inherit this class. If you do
    not inherit this class, the loader will assume it as an ordinary class that should not be
    touched. :py:meth:`issubclass()` is used to determine if a class inherits this class.

    Attributes:
        name: (class attribute) The name of the plugin.
        description: (class attribute) The description of the attribute.
        config: (class attribute) The jsondb config attached, this is used to store global prefixes.
        app: The app (pyrogram ``Client``) instance.
    """

    name: str = "Base Plugin"
    description: str = "Not supposed to be instantiated."

    # There is no need to change the prefixes in the subclasses. This way, consistency is maintained
    # for every plugins. Unless there's a valid reason of doing so.
    config = JsonDB(__name__, PERSIST_DIR)

    config.read_database()
    if isinstance(config.data.get("prefixes"), list):
        prefixes: list[str] = config.data.get("prefixes")  # type: ignore
    else:
        prefixes: list[str] = ["."]

    # Allow other plugins to change the prefix
    config.close()

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    # Allow other plugins to change the prefix
    # TODO: add option to reload all modules and/or restart the bot
    @final
    def change_global_prefix(self, prefixes: list[str]) -> None:
        """This method is used to change the global prefixes for commands of the bot."""
        logger.info("changing global prefixes for bot to %s", prefixes)
        config = JsonDB(__name__, PERSIST_DIR)

        config.read_database()
        config.data.update({"prefixes": prefixes})
        config.write_database()

        config.close()

    # -------------------------------------------------------------------------
    # Shared helpers -- available to every plugin that inherits BasePlugin
    # -------------------------------------------------------------------------

    async def respond(
        self,
        app: Client,
        message: Message,
        text: str,
        parse_mode: ParseMode | None = None,
    ) -> Message:
        """Reply to *message* or edit it if the sender is the bot itself.

        This consolidates the ``_respond`` helpers that previously existed
        independently in ``moderation.py``, ``rm6785.py``, and ``gemini.py``.

        Args:
            app: The Pyrogram client.
            message: The incoming message to respond to.
            text: The text content of the response.
            parse_mode: Optional parse mode (e.g. ``ParseMode.MARKDOWN``).
                If ``None`` the Pyrogram default is used.

        Returns:
            The sent or edited :class:`~pyrogram.types.Message`.
        """
        assert message.from_user
        assert app.me
        kwargs = {} if parse_mode is None else {"parse_mode": parse_mode}
        if message.from_user.id == app.me.id:
            return await message.edit_text(text, **kwargs)
        return await message.reply_text(text, **kwargs)

    async def is_user_admin(self, app: Client, chat: Chat, user: User) -> bool:
        """Return ``True`` if *user* is an administrator or the owner of *chat*.

        This consolidates the identical ``_is_user_admin`` methods that
        previously existed in both ``moderation.py`` and ``bs.py``.
        """
        member = await chat.get_member(user.id)
        return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}

    @abstractmethod
    def register_handlers(self) -> RegisterHandlersResult | Awaitable[RegisterHandlersResult]:
        """This is the abstract method that must be implemented by subclasses for the bot to work.

        The plugin loader will call this method. The default implementation will raise
        NotImplementedError exception.

        Raises:
            NotImplementedError: This is abstract method. Please provide your own implementation.
        """
        raise NotImplementedError("a plugin must implement this method")
