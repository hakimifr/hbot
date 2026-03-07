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
import time
import traceback
from typing import cast, override

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import ChatMemberStatus, ParseMode
from pyrogram.errors import FloodWait, RPCError
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Chat, ChatAdministratorRights, ChatMember
from pyrogram.types.messages_and_media import Message

from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

logger = logging.getLogger(__name__)


class ModPlugin(BasePlugin):
    name: str = "Moderation Plugin"
    description: str = "Plugin for group/channel moderation"

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def _is_admin(self, app: Client, chat_id: int) -> bool:
        logger.info("checking admin status")
        admin_status: bool | None = (await app.get_chat(chat_id)).is_admin

        # it can also be None is it's private chat, for the sake of simplicity,
        # we return True
        logger.info("admin status: %s", admin_status)
        if admin_status or admin_status is None:
            return True
        return False

    async def _respond(self, app: Client, message: Message, text: str) -> Message:
        assert message.from_user
        assert app.me
        if message.from_user.id == app.me.id:
            return await message.edit_text(text)
        else:
            return await message.reply_text(text)

    async def purge(self, app: Client, message: Message) -> None:
        assert message.from_user
        assert message.chat

        member = await message.chat.get_member(message.from_user.id)
        if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
            await message.reply_text("__you're not admin in this chat!__")
            return

        assert message.text
        silent: bool = False
        if message.text[1:].startswith("sp"):
            silent = True
            logger.info("purging silently")

        if not message.reply_to_message:
            await self._respond(app, message, "__reply to a message!__")
            return

        chat = cast(Chat, message.chat)
        message.text = cast(str, message.text)

        if chat.is_forum and "--force" not in message.text:
            await self._respond(
                app,
                message,
                "__using this command in topic-enabled chat is a bad idea, use --force to do it anyway.__",
            )
            return

        logger.info("purging messages")

        start_time = time.perf_counter()

        # delete 100-by-100
        for i in range(message.reply_to_message.id, message.id, 100):
            chat_id = message.chat.id
            message_ids = list(range(i, min(i + 100, message.id)))

            logger.info("deleting messages: %s", message_ids)
            await app.delete_messages(
                chat_id,  # type: ignore
                message_ids,
            )

        time_delta = time.perf_counter() - start_time

        if not silent:
            assert app.me
            if message.from_user.id != app.me.id:
                app.loop.create_task(message.delete())
            amount_of_msgs = len(range(message.reply_to_message.id, message.id)) + 1
            await self._respond(app, message, f"__purged! {amount_of_msgs} messages purged in {time_delta} seconds__")
        else:
            await message.delete()

    async def add(self, app: Client, message: Message) -> None:
        """Add a user to the current chat."""
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.edit_text("__reply to a user message!__")
            return

        logger.info("attempting to add user to chat")
        target_user_id: int = message.reply_to_message.from_user.id
        target_full_name: str = message.reply_to_message.from_user.full_name

        try:
            await message.edit_text(f"__adding {target_full_name} to chat...__")
            logger.info("adding user %s (%s) to chat %s", target_full_name, target_user_id, message.chat.id)
            await app.add_chat_members(message.chat.id, target_user_id)  # type: ignore
            logger.info("user added successfully")
            await message.edit_text(f"__added {target_full_name} to chat__")
            await asyncio.sleep(5)
            await message.delete()
        except Exception as e:
            logger.error("failed to add user: %s", e)
            await message.edit_text(f"__failed to add user: {e}__")

    async def id(self, app: Client, message: Message) -> None:
        """Get the ID of a user or current chat."""
        logger.info("getting ID information")

        if message.reply_to_message and message.reply_to_message.from_user:
            user = message.reply_to_message.from_user
            logger.info("getting user ID for %s", user.full_name)
            result = "**User ID Information**\n\n"
            result += f"**Name:** {user.full_name}\n"
            result += f"**ID:** `{user.id}`\n"
            if user.username:
                result += f"**Username:** @{user.username}\n"
        else:
            logger.info("getting chat ID for current chat")
            chat = message.chat
            result = "**Chat ID Information**\n\n"
            result += f"**Title:** {chat.title or 'Private Chat'}\n"
            result += f"**ID:** `{chat.id}`\n"
            if chat.username:
                result += f"**Username:** @{chat.username}\n"

        logger.info("ID information retrieved successfully")
        await message.edit_text(result)

    async def info(self, app: Client, message: Message) -> None:
        """Get comprehensive information about a user."""
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.edit_text("__reply to a user message to get their info!__")
            return

        logger.info("fetching comprehensive user information")
        user_id = message.reply_to_message.from_user.id

        try:
            # Get full user information
            logger.info("fetching full user data for user ID: %s", user_id)
            user = await app.get_users(user_id)

            # Build info string
            info_text = "**👤 User Information**\n\n"
            info_text += f"**ID:** `{user.id}`\n"
            info_text += f"**First Name:** {user.first_name}\n"

            if user.last_name:
                info_text += f"**Last Name:** {user.last_name}\n"

            info_text += f"**Full Name:** {user.full_name}\n"

            if user.username:
                info_text += f"**Username:** @{user.username}\n"

            info_text += f"**Is Bot:** {'Yes' if user.is_bot else 'No'}\n"
            info_text += f"**Is Verified:** {'Yes' if user.is_verified else 'No'}\n"
            info_text += f"**Is Restricted:** {'Yes' if user.is_restricted else 'No'}\n"
            info_text += f"**Is Scam:** {'Yes' if user.is_scam else 'No'}\n"
            info_text += f"**Is Fake:** {'Yes' if user.is_fake else 'No'}\n"
            info_text += f"**Is Premium:** {'Yes' if user.is_premium else 'No'}\n"

            if user.status:
                info_text += f"**Status:** {str(user.status).replace('UserStatus.', '')}\n"

            if user.dc_id:
                info_text += f"**DC ID:** {user.dc_id}\n"

            if user.phone_number:
                info_text += f"**Phone:** +{user.phone_number}\n"

            if user.photo:
                info_text += "**Has Profile Photo:** Yes\n"

            # Get bio if available (requires fetching chat info)
            try:
                logger.info("attempting to fetch bio for user %s", user_id)
                chat = await app.get_chat(user_id)
                if chat.bio:
                    info_text += f"\n**Bio:**\n{chat.bio}\n"
                    logger.info("bio retrieved successfully")
            except Exception as e:
                logger.warning("could not fetch bio: %s", e)

            # Try to get common chats count
            try:
                logger.info("attempting to get common chats count for user %s", user_id)
                common_chats = await app.get_common_chats(user_id)
                info_text += f"\n**Common Chats:** {len(common_chats)}\n"
                logger.info("common chats count: %d", len(common_chats))
            except Exception as e:
                logger.warning("could not get common chats: %s", e)

            logger.info("user information compiled successfully")
            await message.edit_text(info_text)

        except Exception as e:
            logger.error("failed to get user info: %s", e)
            await message.edit_text(f"__failed to get user info: {e}__")

    # TODO: check if this is PM and forbid this command from running
    async def kick(self, app: Client, message: Message) -> None:
        if not self._is_admin(app, message.chat.id):  # type: ignore
            await message.edit_text("__you are not an admin!__")
            return

        # TODO: allow passing the user's id
        if not message.reply_to_message:
            await message.edit_text("__please reply to a message__")
            return

        assert message.chat is not None
        assert message.chat.id is not None
        assert message.reply_to_message.from_user is not None

        target_chat_id: int = message.chat.id
        target_user_id: int = message.reply_to_message.from_user.id
        target_full_name: str = message.reply_to_message.from_user.full_name

        await message.edit_text(f"__kicking {target_full_name}...__")

        logger.info(
            "ban chat_id: %s, user_id: %s, username: %s",
            target_chat_id,
            target_user_id,
            target_full_name,
        )
        await self.app.ban_chat_member(target_chat_id, target_user_id)

        logger.info(
            "unban chat_id: %s, user_id: %s, username: %s",
            target_chat_id,
            target_user_id,
            target_full_name,
        )
        await self.app.unban_chat_member(target_chat_id, target_user_id)

        await message.edit_text(f"__kicked {target_full_name}__")

    async def ban(self, app: Client, message: Message) -> None:
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.edit_text("__reply to a user message!__")
            return

        await app.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)  # type: ignore
        await message.edit_text("__banned__")
        await asyncio.sleep(5)
        await message.delete()

    async def unban(self, app: Client, message: Message) -> None:
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.edit_text("__reply to a user message!__")
            return

        await app.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)  # type: ignore
        await message.edit_text("__unbanned__")
        await asyncio.sleep(5)
        await message.delete()

    async def deleted_users(self, app: Client, message: Message) -> None:
        chat = cast(Chat, message.chat)

        if not chat.is_admin:
            await message.delete()
            return

        logger.info("removing deleted accounts")
        await message.edit_text("__removing deleted accounts__")

        deleted_members: list[ChatMember] = []
        async for member in chat.get_members():
            if member.user.is_deleted:
                deleted_members.append(member)

        if len(deleted_members) == 0:
            await message.edit_text("__no deleted member(s) found__")
            return

        final_msg = "**Deleted Accounts Removal Status:**\n"
        i = 0
        while i < len(deleted_members):
            member = deleted_members[i]
            i += 1
            try:
                logger.info("remove: %d", member.user.id)
                await chat.ban_member(member.user.id)
                await chat.unban_member(member.user.id)
                await asyncio.sleep(0.2)
                final_msg += f"__removed: {member.user.id}__\n"
            except FloodWait as e:
                logger.warning("received floodwait: %d seconds", e.value)
                await asyncio.sleep(e.value)  # type: ignore
                i -= 1
            except Exception as e:
                logger.warning("cannot remove %d, reason: %s", member.user.id, str(e))
                final_msg += f"__failed to remove: {member.user.id}, reason: {e}__\n"

        await message.edit_text(final_msg)

    async def promote(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.from_user

        member = await message.chat.get_member(message.from_user.id)
        if not member.privileges.can_promote_members:
            await message.edit_text("__not enough rights to promote members__")
            return

        if not message.reply_to_message:
            await message.edit_text("__reply to a user to promote__")
            return

        assert message.reply_to_message
        assert message.reply_to_message.from_user
        try:
            member.privileges.can_promote_members = False
            member.privileges.is_anonymous = False
            await message.chat.promote_member(message.reply_to_message.from_user.id, privileges=member.privileges)
            await message.edit_text("__promoted!__")
        except RPCError:
            tb = traceback.format_exc()
            await message.edit_text(f"__promote failed!__\n```\n{tb}```", parse_mode=ParseMode.MARKDOWN)
            raise

    async def demote(self, app: Client, message: Message) -> None:
        assert message.chat
        assert message.from_user
        assert message.reply_to_message
        assert message.reply_to_message.from_user

        member = await message.chat.get_member(message.from_user.id)
        replied_member = await message.chat.get_member(message.reply_to_message.from_user.id)
        if member.status == ChatMemberStatus.ADMINISTRATOR and replied_member.promoted_by != message.from_user:
            await message.edit_text("__you cannot edit the rights of this admin__")
            return

        try:
            await message.chat.promote_member(
                message.reply_to_message.from_user.id, privileges=ChatAdministratorRights(can_manage_chat=False)
            )
            await message.edit_text("__demoted!__")
        except RPCError:
            tb = traceback.format_exc()
            await message.edit_text(f"__demote failed!__\n```\n{tb}```", parse_mode=ParseMode.MARKDOWN)
            raise

    async def relayfban(self, app: Client, message: Message) -> None:
        assert message.from_user
        assert message.chat

        member = await message.chat.get_member(message.from_user.id)

        if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
            await message.reply_text("__you're not admin in this chat!__")
            return

        assert message.text
        args = message.text.split(" ")

        if args[0][1:].startswith("rf") or args[0][1:].startswith("relayfban"):
            cmd = "fban"
        else:
            cmd = "unfban"

        args.pop(0)

        if message.reply_to_message:
            assert message.reply_to_message.from_user
            user_id = message.reply_to_message.from_user.id
        else:
            if len(args) < 1:
                await message.reply_text("__no user id provided, and you did not reply to anyone!__")
                return
            user_id = args[0]
            args.pop(0)

        fban_reason = " ".join(args)

        msg = await app.send_message(-1001754321934, f"!{cmd} {user_id} {fban_reason}")
        await message.reply_text(msg.link)

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        base = filters.me
        return RegisterHandlersResult(
            handlers=[
                MessageHandler(self.purge, filters.command(["purge", "p"], prefixes=self.prefixes)),
                MessageHandler(self.purge, filters.command(["spurge", "sp"], prefixes=self.prefixes)),
                MessageHandler(self.ban, filters.command("ban", prefixes=self.prefixes) & base),
                MessageHandler(self.unban, filters.command("unban", prefixes=self.prefixes) & base),
                MessageHandler(self.relayfban, filters.command(["relayfban", "rf"], prefixes=self.prefixes)),
                MessageHandler(self.relayfban, filters.command(["relayunfban", "ruf"], prefixes=self.prefixes)),
                MessageHandler(self.kick, filters.command("kick", prefixes=self.prefixes) & base),
                MessageHandler(self.add, filters.command("add", prefixes=self.prefixes) & base),
                MessageHandler(self.id, filters.command("id", prefixes=self.prefixes) & base),
                MessageHandler(self.info, filters.command("info", prefixes=self.prefixes) & base),
                MessageHandler(self.deleted_users, filters.command("du", prefixes=self.prefixes) & base),
                MessageHandler(self.promote, filters.command("promote", prefixes=self.prefixes) & base),
                MessageHandler(self.demote, filters.command("demote", prefixes=self.prefixes) & base),
            ]
        )
