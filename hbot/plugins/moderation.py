import asyncio
import logging

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

    async def add(self, app: Client, message: Message) -> None:
        # Parse username from command
        text_parts = message.text.split()  # type: ignore

        if len(text_parts) < 2:
            await message.edit_text("__usage: .add <username>__")
            return

        username = text_parts[1].lstrip("@")

        try:
            await message.edit_text(f"__adding @{username}...__")
            await app.add_chat_members(message.chat.id, username)  # type: ignore
            await message.edit_text(f"__added @{username}__")
        except (ValueError, RuntimeError, OSError) as e:
            logger.error("failed to add user: %s", e)
            await message.edit_text(f"__failed to add user: {str(e)}__")

    async def get_id(self, app: Client, message: Message) -> None:
        info_text = f"**Chat ID:** `{message.chat.id}`\n"

        if message.reply_to_message:
            replied = message.reply_to_message
            if replied.from_user:
                info_text += f"**User ID:** `{replied.from_user.id}`\n"
                info_text += f"**Username:** @{replied.from_user.username or 'N/A'}\n"
        else:
            if message.from_user:
                info_text += f"**Your ID:** `{message.from_user.id}`\n"

        await message.edit_text(info_text)

    async def get_info(self, app: Client, message: Message) -> None:
        if not message.reply_to_message or not message.reply_to_message.from_user:
            # Get chat info
            chat = await app.get_chat(message.chat.id)  # type: ignore
            info_text = "**Chat Information**\n\n"
            info_text += f"**Title:** {chat.title or 'N/A'}\n"
            info_text += f"**Type:** {chat.type}\n"
            info_text += f"**ID:** `{chat.id}`\n"
            if chat.username:
                info_text += f"**Username:** @{chat.username}\n"
            if chat.members_count:
                info_text += f"**Members:** {chat.members_count}\n"
            if chat.description:
                info_text += f"**Description:** {chat.description}\n"
        else:
            # Get user info
            user = message.reply_to_message.from_user
            info_text = "**User Information**\n\n"
            info_text += f"**Name:** {user.first_name}"
            if user.last_name:
                info_text += f" {user.last_name}"
            info_text += "\n"
            info_text += f"**ID:** `{user.id}`\n"
            if user.username:
                info_text += f"**Username:** @{user.username}\n"
            if user.is_bot:
                info_text += "**Is Bot:** Yes\n"
            if user.is_premium:
                info_text += "**Premium:** Yes\n"

        await message.edit_text(info_text)

    def register_handlers(self) -> list[Handler]:
        base = filters.me
        return [
            MessageHandler(self.purge, filters.command("purge", prefixes=self.prefixes) & base),
            MessageHandler(self.ban, filters.command("ban", prefixes=self.prefixes) & base),
            MessageHandler(self.unban, filters.command("unban", prefixes=self.prefixes) & base),
            MessageHandler(self.add, filters.command("add", prefixes=self.prefixes) & base),
            MessageHandler(self.get_id, filters.command("id", prefixes=self.prefixes) & base),
            MessageHandler(self.get_info, filters.command("info", prefixes=self.prefixes) & base),
        ]
