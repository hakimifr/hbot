import asyncio
import logging
from typing import override

from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot.base_plugin import BasePlugin

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

    async def purge(self, app: Client, message: Message) -> None:
        if not message.reply_to_message:
            await message.edit_text("__reply to a message!__")
            return

        logger.info("purging messages")

        # delete 100-by-100
        for i in range(message.reply_to_message.id, message.id, 100):
            chat_id = message.chat.id  # type: ignore
            message_ids = list(range(i, min(i + 100, message.id)))

            logger.info("deleting messages: %s", message_ids)
            await app.delete_messages(
                chat_id,  # type: ignore
                message_ids,
            )

        confirmation_text: str = "__purged! this message will auto delete in 5 seconds__"

        if not await self._is_admin(app, message.chat.id):  # type: ignore
            logger.info("user was NOT admin, only their messages are deleted")
            confirmation_text += "\n__warning: you are not an admin, only your messages are purged__"

        logger.info("confirmation text sent, deleting in 5 seconds")
        await message.edit_text(confirmation_text)
        await asyncio.sleep(5)
        await message.delete()
        logger.info("confirmation text deleted")

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

    @override
    def register_handlers(self) -> list[Handler]:
        base = filters.me
        return [
            MessageHandler(self.purge, filters.command("purge", prefixes=self.prefixes) & base),
            MessageHandler(self.ban, filters.command("ban", prefixes=self.prefixes) & base),
            MessageHandler(self.unban, filters.command("unban", prefixes=self.prefixes) & base),
            MessageHandler(self.kick, filters.command("kick", prefixes=self.prefixes) & base),
            MessageHandler(self.add, filters.command("add", prefixes=self.prefixes) & base),
            MessageHandler(self.id, filters.command("id", prefixes=self.prefixes) & base),
            MessageHandler(self.info, filters.command("info", prefixes=self.prefixes) & base),
        ]
