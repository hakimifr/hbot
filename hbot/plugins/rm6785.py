import asyncio
import atexit
import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, cast

from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.enums import MessageEntityType
from pyrogram.handlers.handler import Handler
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types import Chat, MessageEntity, User
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR
from hbot.base_plugin import BasePlugin

type Name = str
type UserId = int
type ChatId = int
type MessageId = int
type ChannelId = int
type PostSourceChatId = int
type PostSourceMessageId = int
type PostConfirmationMessageId = int
type StickerChatId = int
type StickerMessageId = int
type StickerId = str

RM6785_CHANNEL_ID: ChannelId = -1001384382397
RM6785_STICKER_ID: StickerId = "CAACAgUAAx0EX9CqtwACBvdpYhcQ4xFR18TbqiDxMasDZ4EWOQACLwQAAt4AAXFVonEmaEmbIrYeBA"
SUPERUSERS: dict[str[UserId], Name] = {
    "1024853832": "hakimi",
    "1138003186": "samar",
}
logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthStatus:
    ok: bool
    error_string: str


VoteStatus = PostCancelStatus = AuthStatus


@dataclass(frozen=True)
class LintStatus:
    lint_ok: bool
    lint_result_string: str


class AuthUtils:
    db_auth: JsonDB = JsonDB(f"{__name__}:auth", PERSIST_DIR)
    authorised_users: dict[str[UserId], Name] = db_auth.data
    if len(authorised_users) == 0:
        authorised_users.update(SUPERUSERS)
        db_auth.data = authorised_users
        db_auth.write_database()

    @classmethod
    def authorise_user(cls, name: Name, user_id: str[UserId]) -> AuthStatus:
        if str(user_id) in cls.authorised_users:
            logger.warning(
                "user [name: '%s', id: '%s'] is already in authorised users list",
                name,
                user_id,
            )
            return AuthStatus(False, "user is already in authorised users list")

        logger.info(
            "adding user [name: '%s', id: '%s'] to authorised users list",
            name,
            user_id,
        )
        cls.authorised_users.update({str(user_id): name})
        cls.db_auth.data = cls.authorised_users
        cls.db_auth.write_database()
        return AuthStatus(True, "")

    @classmethod
    def deauthorise_user(cls, user_id: str[UserId]) -> AuthStatus:
        if str(user_id) not in cls.authorised_users:
            logger.warning(
                "user [name: '%s', id: '%s'] not in authorised users list",
                cls.authorised_users[user_id],
                user_id,
            )
            return AuthStatus(False, "user is not in authorised users list")

        logger.info(
            "removing user [name: '%s', id: '%s'] from authorised users list",
            cls.authorised_users[user_id],
            user_id,
        )
        cls.authorised_users.pop(str(user_id))
        cls.db_auth.data = cls.authorised_users
        cls.db_auth.write_database()
        return AuthStatus(True, "")

    @classmethod
    def is_superuser(cls, user_id: UserId) -> bool:
        return str(user_id) in SUPERUSERS

    @classmethod
    def get_authorised_users(cls) -> dict[str[UserId], Name]:
        return cls.authorised_users


# ruff: disable[N806]
class LintUtils:
    kernel: bool
    bold_title: bool
    bold_notes: bool
    bold_changelog: bool
    bold_bugs: bool
    bold_downloads: bool
    hashtags: list[str]

    @classmethod
    def lint_telegram_post(cls, text: str, entities: list[MessageEntity]) -> LintStatus:
        logger.info("starting linting telegram post")
        logger.info("text length: %s", len(text))
        logger.info("entity count: %s", len(entities))

        cls._reset_state()

        errors = (
            "\n"
            + cls._validate_hashtags(text)
            + cls._validate_bold(text, entities)
            + cls._validate_title(text)
            + cls._validate_build_info(text)
            + cls._validate_changelog_bugs(text)
            + cls._validate_downloads(text)
            + cls._validate_footer(text)
        )

        lint_status = not errors.strip()
        logger.info("lint completed, status: %s", lint_status)

        lint_result_string = "Seems good 🤌\nBot approves" if lint_status else f"<b>ERRORS</b>\n{errors}"

        return LintStatus(lint_status, lint_result_string)

    # ───────────────────────────────
    # internal helpers
    # ───────────────────────────────

    @classmethod
    def _reset_state(cls) -> None:
        logger.info("resetting lint state")

        cls.kernel = False
        cls.bold_title = False
        cls.bold_notes = False
        cls.bold_changelog = False
        cls.bold_bugs = False
        cls.bold_downloads = False
        cls.hashtags = []

    # ───────────────────────────────
    # validators
    # ───────────────────────────────

    @classmethod
    def _validate_hashtags(cls, text: str) -> str:
        logger.info("validating hashtags")

        error_message = ""
        cls.hashtags = [tag[1:] for tag in re.findall(r"#\w+", text)]

        logger.info("found hashtags: %s", cls.hashtags)

        if not cls.hashtags:
            logger.info("no hashtags found")
            return "Hashtags:\n• No hashtags were found."

        (
            TAG_BRAND,
            TAG_BUILD,
            TAG_RELEASE_TYPE,
            TAG_DEVICE,
            TAG_ANDROID_VER,
            TAG_RUI_VER,
            *_,
        ) = cls.hashtags + [None] * 6

        logger.info(
            "parsed hashtag values: build=%s release=%s device=%s android=%s rui=%s",
            TAG_BUILD,
            TAG_RELEASE_TYPE,
            TAG_DEVICE,
            TAG_ANDROID_VER,
            TAG_RUI_VER,
        )

        if TAG_BUILD == "KERNEL":
            cls.kernel = True
            TAG_DEVICE, TAG_RUI_VER = cls.hashtags[2], cls.hashtags[3]
            logger.info("kernel build detected")
        elif TAG_ANDROID_VER and "RMX" in TAG_ANDROID_VER:
            TAG_ANDROID_VER, TAG_RUI_VER = cls.hashtags[5], cls.hashtags[6]
            logger.info("rmx-style hashtag order detected")

        RELEASE_TYPE = {"UNOFFICIAL", "OFFICIAL"}
        BUILD_TYPE = {"ROM", "KERNEL", "RECOVERY"}
        DEVICE = {"RM6785", "RMX2001", "RMX2151", "salaa", "nemo"}
        ANDROID_VERSION = {"A10", "A11", "A12", "A13", "A14", "A15", "A16"}
        RUI_VERSION = {"RUI1", "RUI2", "RUI3"}

        if TAG_BUILD not in BUILD_TYPE:
            logger.info("invalid build type: %s", TAG_BUILD)
            error_message += "• Incorrect build type mentioned on the second hashtag. (ROM/KERNEL/RECOVERY)\n"

        if not cls.kernel and TAG_RELEASE_TYPE not in RELEASE_TYPE:
            logger.info("invalid release type: %s", TAG_RELEASE_TYPE)
            error_message += "• Incorrect release type mentioned on the third hashtag. (OFFICIAL/UNOFFICIAL)\n"

        if TAG_DEVICE not in DEVICE:
            logger.info("invalid device: %s", TAG_DEVICE)
            idx = "third" if cls.kernel else "fourth"
            error_message += f"• Incorrect device mentioned on the {idx} hashtag. (RM6785/RMX2001/RMX2151/salaa)\n"

        if not cls.kernel and TAG_ANDROID_VER not in ANDROID_VERSION:
            logger.info("invalid android version: %s", TAG_ANDROID_VER)
            error_message += (
                "• Incorrect Android version mentioned on the fifth hashtag. (A10/A11/A12/A13/A14/A15/A16)\n"
            )

        if TAG_RUI_VER not in RUI_VERSION:
            logger.info("invalid rui version: %s", TAG_RUI_VER)
            error_message += "• Incorrect RealmeUI version mentioned on the last hashtag. (RUI1/RUI2/RUI3)\n"

        return f"Hashtags:\n{error_message}" if error_message else ""

    @classmethod
    def _validate_bold(cls, text: str, entities: list[MessageEntity]) -> str:
        logger.info("validating bold entities")

        if "Notes" not in text:
            logger.info("notes section not present, skipping bold notes requirement")
            cls.bold_notes = True

        for entity in entities:
            if entity.type != MessageEntityType.BOLD:
                continue

            word = text[entity.offset : entity.offset + entity.length]
            logger.info("processing bold text: %s", word)

            if "Notes" in word:
                cls.bold_notes = True
            elif "Changelog" in word:
                cls.bold_changelog = True
            elif "Bugs" in word:
                cls.bold_bugs = True
            elif "Downloads" in word:
                cls.bold_downloads = True
            elif any(
                title in word
                for title in (
                    "for Realme 6/6i(Indian)/6s/7/Narzo/Narzo 20 Pro/Narzo 30 4G",
                    "for Realme 6/6i(Indian)/6s/Narzo ONLY",
                    "for Realme 7/Narzo 20 Pro/Narzo 30 4G ONLY",
                )
            ):
                cls.bold_title = True

        logger.info(
            "bold flags: title=%s notes=%s changelog=%s bugs=%s downloads=%s",
            cls.bold_title,
            cls.bold_notes,
            cls.bold_changelog,
            cls.bold_bugs,
            cls.bold_downloads,
        )

        return ""

    @classmethod
    def _validate_title(cls, text: str) -> str:
        logger.info("validating title")

        error_message = ""

        try:
            title = re.search(r".*\w+(?= +for).*", text).group()  # ty: ignore[possibly-missing-attribute]
            logger.info("extracted title: %s", title)
        except AttributeError:
            logger.info("no title found")
            return "Title:\n• No title found."

        if not cls.bold_title:
            logger.info("title is not bold")
            error_message += "• Missing bold format on title\n"

        if not re.search(r"(Realme 6|Realme 7|Narzo)", title):
            logger.info("title device order invalid")
            error_message += "• Missing or incorrect order of device in title.\n"

        if not re.search(r"\[([^\]]+)\]$", title):
            logger.info("title stability stage missing")
            error_message += "• Missing build's stability stage. (ALPHA/BETA/STABLE)\n"

        return f"Title:\n{error_message}" if error_message else ""

    @classmethod
    def _validate_build_info(cls, text: str) -> str:
        logger.info("validating build info")

        error_message = ""
        type_ = "Kernel" if cls.kernel else "Android"
        logger.info("build type resolved as: %s", type_)

        pattern = rf"(.+)\n• Author:(.+)?\n• {type_} version:(.+)?\n• Build date:(.+)?"

        if not re.search(pattern, text, re.I):
            logger.info("build info section missing or malformed")
            return "Build info:\n• Invalid build info section"

        if not re.search(pattern, text):
            logger.info("build info has incorrect case")
            error_message += "• Incorrect case\n"

        if not re.search(r"\n• Author: (.+)", text):
            logger.info("author info invalid")
            error_message += "• Invalid author info\n"

        if not re.search(rf"\n• {type_} version: (.+)", text):
            logger.info("%s version info invalid", type_)
            error_message += f"• Invalid {type_} version info\n"

        if not re.search(
            r"\n• Build date: (0?[1-9]|[12][0-9]|3[01])-(0?[1-9]|1[0-2])-\d{4}",
            text,
        ):
            logger.info("build date format invalid")
            error_message += "• Invalid build date info (Required format: DD-MM-YY)\n"

        return f"Build info:\n{error_message}" if error_message else ""

    @classmethod
    def _validate_changelog_bugs(cls, text: str) -> str:
        logger.info("validating changelog and bugs sections")

        error_message = ""
        pattern = r"\n\nChangelog\n(.+\n)+\nBugs\n(.+\n)+(\nNotes\n(.+\n)+)?"

        if not re.search(pattern, text, re.I):
            logger.info("changelog/bugs section missing")
            return "Changelog/Bugs:\n• Invalid Changelog/Bugs section."

        if not re.search(pattern, text):
            logger.info("changelog/bugs incorrect case")
            error_message += "• Incorrect case.\n"

        if not cls.bold_changelog:
            logger.info("changelog not bold")
            error_message += "Missing bold format on Changelog\n"
        if not cls.bold_bugs:
            logger.info("bugs not bold")
            error_message += "Missing bold format on Bugs\n"
        if not cls.bold_notes:
            logger.info("notes not bold")
            error_message += "Missing bold format on Notes\n"

        if not re.search(r"\n\nChangelog\n•", text):
            logger.info("changelog content invalid")
            error_message += "• Invalid Changelog section.\n"

        if not re.search(r"\nBugs\n•", text):
            logger.info("bugs content invalid")
            error_message += "• Invalid Bugs section.\n"

        if re.search(r"\nNote", text, re.I) and not re.search(r"\nNotes\n•", text):
            logger.info("notes section malformed")
            error_message += "• Invalid notes section.\n"

        return f"Changelog/Bugs:\n{error_message}" if error_message else ""

    @classmethod
    def _validate_downloads(cls, text: str) -> str:
        logger.info("validating downloads section")

        error_message = ""

        pattern = (
            r"\n\nDownloads\n• File size:(.+)?\n• Download\n"
            if cls.kernel
            else r"\n\nDownloads\n• Build type:(.+)?\n• File size:(.+)?\n• Download\n"
        )

        if not re.search(pattern, text, re.I):
            logger.info("downloads section missing")
            return "Downloads:\n• Invalid Downloads section."

        if not re.search(pattern, text):
            logger.info("downloads incorrect case")
            error_message += "• Incorrect case.\n"
        elif not cls.bold_downloads:
            logger.info("downloads not bold")
            error_message += "• Missing bold format on Downloads.\n"

        if not cls.kernel and not re.search(r"\n• Build type: (.+)", text):
            logger.info("build type info missing")
            error_message += "• Invalid build type\n"

        if not re.search(r"\n• File size: (.+)", text):
            logger.info("file size info missing")
            error_message += "• Invalid file size\n"

        return f"Downloads:\n{error_message}" if error_message else ""

    @classmethod
    def _validate_footer(cls, text: str) -> str:
        logger.info("validating footer")

        error_message = ""
        pattern = r"\nSources\nSupport group" if cls.kernel else r"\nSources\nScreenshots\nSupport group"

        if not re.search(pattern, text, re.I):
            logger.info("footer section missing or malformed")
            return f"Footer:\n• Invalid footer section.\n  Should be written exactly like this:{pattern}"

        if not re.search(pattern, text):
            logger.info("footer incorrect case")
            error_message += "• Incorrect case.\n"
            error_message += f"Correct usage:{pattern}"

        return f"Footer:\n{error_message}" if error_message else ""


# ruff: enable[N806]


class VoteUtils:
    db_vote: JsonDB = JsonDB(f"{__name__}:vote", PERSIST_DIR)
    db_vote.read_database()

    @classmethod
    def vote(cls, user_id: UserId, replied_message_id: MessageId) -> VoteStatus:
        users_voted: list[UserId] = cast(list[UserId], cls.db_vote.data.get(str(replied_message_id), []))
        if user_id in users_voted:
            logger.warning(
                "cannot increment vote count, [user: %s] has already voted for [message: %s]",
                user_id,
                replied_message_id,
            )
            return VoteStatus(False, "user has already voted")

        users_voted.append(user_id)
        cls.db_vote.data.update({str(replied_message_id): users_voted})
        cls.db_vote.write_database()

        return VoteStatus(True, "")

    @classmethod
    def remove_vote(cls, user_id: UserId, replied_message_id: MessageId) -> VoteStatus:
        users_voted: list[UserId] = cast(list[UserId], cls.db_vote.data.get(str(replied_message_id), []))
        if user_id not in users_voted:
            logger.warning(
                "cannot decrement vote count, [user: %s] has never voted for [message: %s]",
                user_id,
                replied_message_id,
            )
            return VoteStatus(False, "user never voted")

        users_voted.remove(user_id)
        cls.db_vote.data.update({str(replied_message_id): users_voted})
        cls.db_vote.write_database()

        return VoteStatus(True, "")

    @classmethod
    def get_vote_count(cls, replied_message_id) -> int:
        return len(cls.db_vote.data.get(str(replied_message_id), []))


@dataclass
class UnfinishedPostData:
    post_source_chat_id: PostSourceChatId
    post_source_message_id: PostSourceMessageId
    post_confirmation_message_id: PostConfirmationMessageId  # shares same chat id as post source
    sticker_chat_id: StickerChatId
    sticker_message_id: StickerMessageId


@dataclass
class PostData(UnfinishedPostData):
    task: asyncio.Task


class PostUtils:
    db_post: JsonDB = JsonDB(f"{__name__}:post", PERSIST_DIR)
    db_post.read_database()
    posts: list[PostData] = []

    @classmethod
    def cleanup(cls) -> None:
        logger.info("cleaning up")
        logger.info("%s", cls.posts)
        unfinished_posts: list[dict[str, Any]] = []
        for post_data in cls.posts:
            if not post_data.task.done():
                logger.info("found unfinished post")
                post_data.task.cancel()
                up = asdict(
                    UnfinishedPostData(
                        post_data.post_source_chat_id,
                        post_data.post_source_message_id,
                        post_data.post_confirmation_message_id,
                        post_data.sticker_chat_id,
                        post_data.sticker_message_id,
                    )
                )
                logger.info("iter: %s", up)
                unfinished_posts.append(up)
                logger.info("saving unfinished post %s", up)

        cls.db_post.data.update({"unfinished_posts": unfinished_posts})
        cls.db_post.write_database()

    @classmethod
    async def _on_start(cls, app: Client):
        unfinished_posts: list[UnfinishedPostData] = [
            UnfinishedPostData(**u) for u in cls.db_post.data.get("unfinished_posts", [])
        ]
        logger.info("unfinished posts loaded")
        logger.info("restoring unfinished posts")

        try:
            await app.start()
        except ConnectionError:
            pass

        for p in unfinished_posts:
            logger.info("restoring %s", asdict(p))
            post_confirmation: Message = cast(
                Message, await app.get_messages(p.post_source_chat_id, p.post_confirmation_message_id)
            )
            source_post: Message = cast(
                Message, await app.get_messages(p.post_source_chat_id, p.post_source_message_id)
            )
            await app.delete_messages(p.sticker_chat_id, p.sticker_message_id)
            await cls.post(app, post_confirmation, source_post)

    @staticmethod
    async def _run_delayed(reply_to_message: Message, delay_in_minutes: float = 5):
        try:
            await asyncio.sleep(delay_in_minutes * 60)
            await reply_to_message.copy(RM6785_CHANNEL_ID)
        except asyncio.CancelledError:
            raise

    @classmethod
    async def post(cls, app: Client, confirmation_message: Message, reply_to_message: Message) -> None:
        msg = await app.send_sticker(RM6785_CHANNEL_ID, RM6785_STICKER_ID)
        msg = cast(Message, msg)
        chat = cast(Chat, msg.chat)

        task = asyncio.create_task(cls._run_delayed(reply_to_message))
        cls.posts.append(
            PostData(
                post_source_chat_id=cast(int, cast(Chat, reply_to_message.chat).id),
                post_source_message_id=cast(int, reply_to_message.id),
                post_confirmation_message_id=confirmation_message.id,  # shares same chat id as post source
                sticker_chat_id=cast(int, chat.id),
                sticker_message_id=msg.id,
                task=task,
            )
        )
        logger.info("%s", cls.posts)
        start_time = time.perf_counter()
        while time.perf_counter() - start_time < 5 * 60:
            if task.cancelled():
                await confirmation_message.edit_text("__post cancelled__")
                return
            await confirmation_message.edit_text(f"__time remaining: {5 - (time.perf_counter() - start_time) / 60}__")
            await asyncio.sleep(2)

        if task.done():
            await confirmation_message.edit_text("__posted__")

    @classmethod
    async def cancel(cls, app: Client, reply_to_message: Message) -> PostCancelStatus:
        for post_data in cls.posts:
            if post_data.post_source_message_id == reply_to_message.id:
                post_data.task.cancel()
                await app.delete_messages(post_data.sticker_chat_id, post_data.sticker_message_id)
                return PostCancelStatus(True, "")

        return PostCancelStatus(False, "message was not posted")


atexit.register(PostUtils.cleanup)


class RM6785Plugin(BasePlugin):
    name: str = "RM6785 Plugin"
    description: str = "A plugin to handle RM6785 ROM posts."

    def __init__(self, app: Client) -> None:
        self.app: Client = app
        self.authorised_users: dict[UserId, MessageId] = AuthUtils.get_authorised_users()
        self.prefixes: list[str] = [".", "/", ",", "!"]

    async def _respond(self, app: Client, message: Message, text: str) -> Message:
        user: User = cast(User, message.from_user)
        if user.id == (await app.get_me()).id:
            await message.edit_text(text)
            return message

        reply_message = await message.reply_text(text)
        return reply_message

    async def auth(self, app: Client, message: Message) -> None:
        user: User = cast(User, message.from_user)
        if not AuthUtils.is_superuser(user.id):
            await self._respond(app, message, "__You must be a superuser to do this__")
            return

        if not message.reply_to_message:
            await self._respond(app, message, "__reply to a message__")
            return

        replied_to_user: User = cast(User, message.reply_to_message.from_user)
        status: AuthStatus = AuthUtils.authorise_user(replied_to_user.full_name, str(replied_to_user.id))
        if not status.ok:
            await self._respond(
                app,
                message,
                f"__cannot auth user, error: {status.error_string}__",
            )
        else:
            await self._respond(
                app,
                message,
                "__user is now authorised__",
            )

    async def deauth(self, app: Client, message: Message) -> None:
        user: User = cast(User, message.from_user)
        if not AuthUtils.is_superuser(user.id):
            await self._respond(app, message, "__You must be a superuser to do this__")
            return

        if not message.reply_to_message:
            await self._respond(app, message, "__reply to a message__")
            return

        replied_to_user: User = cast(User, message.reply_to_message.from_user)
        status: AuthStatus = AuthUtils.deauthorise_user(str(replied_to_user.id))
        if not status.ok:
            await self._respond(
                app,
                message,
                f"__cannot deauthorise user, error: {status.error_string}__",
            )
        else:
            await self._respond(
                app,
                message,
                "__user is now deauthorised__",
            )

    async def lint(self, app: Client, message: Message) -> None:
        if not message.reply_to_message:
            await self._respond(app, message, "__please reply to a message__")
            return

        if not message.reply_to_message.caption:
            await self._respond(app, message, "__missing banner image__")
            return

        reply_to_message = cast(Message, message.reply_to_message)
        caption = cast(str, reply_to_message.caption)
        caption_entities = cast(list[MessageEntity], reply_to_message.caption_entities)
        status: LintStatus = LintUtils.lint_telegram_post(caption, caption_entities)

        await self._respond(app, message, status.lint_result_string)

        if status.lint_ok:
            logger.info("lint OK, adding vote as the bot itself")
            VoteUtils.vote(0, reply_to_message.id)
        else:
            logger.info("lint failed, removing vote as the bot itself")
            VoteUtils.remove_vote(0, reply_to_message.id)

        vote_count = VoteUtils.get_vote_count(reply_to_message.id)
        await message.reply_text(f"__approval count: {vote_count}/3__")

    async def vote(self, app: Client, message: Message) -> None:
        user = cast(User, message.from_user)

        if not AuthUtils.get_authorised_users().get(str(user.id)):
            await self._respond(app, message, "__you are not authorised__")
            return

        if not message.reply_to_message:
            await self._respond(app, message, "__reply to a message please__")
            return

        reply_to_message = cast(Message, message.reply_to_message)
        status = VoteUtils.vote(user.id, reply_to_message.id)

        if status.ok:
            vote_count = VoteUtils.get_vote_count(reply_to_message.id)
            await self._respond(app, message, f"__approved. approval count: {vote_count}/3__")
        else:
            await self._respond(app, message, f"__approval failed, LintUtils reason: {status.error_string}__")

    async def remove_vote(self, app: Client, message: Message) -> None:
        user = cast(User, message.from_user)

        if not AuthUtils.get_authorised_users().get(str(user.id)):
            await self._respond(app, message, "__you are not authorised__")
            return

        if not message.reply_to_message:
            await self._respond(app, message, "__reply to a message please__")
            return

        reply_to_message = cast(Message, message.reply_to_message)
        status = VoteUtils.remove_vote(user.id, reply_to_message.id)

        if status.ok:
            vote_count = VoteUtils.get_vote_count(reply_to_message.id)
            await self._respond(app, message, f"__approval removed. approval count: {vote_count}/3__")
        else:
            await self._respond(app, message, f"__approval removal failed, LintUtils reason: {status.error_string}__")

    async def post(self, app: Client, message: Message) -> None:
        user = cast(User, message.from_user)

        if not AuthUtils.get_authorised_users().get(str(user.id)):
            await self._respond(app, message, "__you are not authorised__")
            return

        if not message.reply_to_message:
            await self._respond(app, message, "__reply to a message please__")
            return

        reply_to_message = cast(Message, message.reply_to_message)
        vote_count = VoteUtils.get_vote_count(reply_to_message.id)

        if vote_count < 3:
            await self._respond(app, message, "__not enough approvals__")
            return

        confirmation_message = await self._respond(app, message, "__please wait__")
        asyncio.create_task(PostUtils.post(app, confirmation_message, message.reply_to_message))

    async def cancel(self, app: Client, message: Message) -> None:
        user = cast(User, message.from_user)

        if not AuthUtils.get_authorised_users().get(user.id):
            await self._respond(app, message, "__you are not authorised__")
            return

        if not message.reply_to_message:
            await self._respond(app, message, "__reply to a message please__")
            return

        confirmation_message = await self._respond(app, message, "__please wait__")
        status = await PostUtils.cancel(app, message.reply_to_message)

        if status.ok:
            await confirmation_message.edit_text("__post cancelled__")
        else:
            await confirmation_message.edit_text(f"__error: PostUtil: {status.error_string}__")

    def register_handlers(self) -> list[Handler]:
        asyncio.get_running_loop().create_task(PostUtils._on_start(self.app))
        return [
            MessageHandler(
                self.auth,
                filters.command("auth", prefixes=self.prefixes),
            ),
            MessageHandler(
                self.deauth,
                filters.command("deauth", prefixes=self.prefixes),
            ),
            MessageHandler(
                self.lint,
                filters.command("lint", prefixes=self.prefixes),
            ),
            MessageHandler(
                self.vote,
                filters.command(["approve", "1"], prefixes=[*self.prefixes, "+"]),
            ),
            MessageHandler(
                self.remove_vote,
                filters.command(["disapprove", "1"], prefixes=[*self.prefixes, "-"]),
            ),
            MessageHandler(
                self.post,
                filters.command("post", prefixes=self.prefixes),
            ),
            MessageHandler(
                self.cancel,
                filters.command("cancel", prefixes=self.prefixes),
            ),
        ]
