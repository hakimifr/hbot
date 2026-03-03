import datetime
import logging
import random
from dataclasses import asdict, dataclass
from typing import Literal, override

from jsondb.database import JsonDB
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.handlers.message_handler import MessageHandler
from pyrogram.types.messages_and_media import Message

from hbot import PERSIST_DIR
from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

RAND_PERCENT_MIN: int = 0
RAND_PERCENT_MAX: int = 200

logger = logging.getLogger(__name__)
db: JsonDB = JsonDB(__name__, PERSIST_DIR)


@dataclass
class UserData:
    sexiness_percentage: int
    gayness_percentage: int
    date: str


class ToysPlugin(BasePlugin):
    name: str = "Toys Plugin"
    description: str = "Silly stuffs."
    prefixes: list[str] = BasePlugin.prefixes.copy()
    prefixes.append("/")

    def __init__(self, app: Client) -> None:
        self.app: Client = app

    async def random_percentage(self, app: Client, message: Message) -> None:
        msg: Message = message if not message.reply_to_message else message.reply_to_message
        assert msg.from_user

        assert message.text
        type_raw = message.text.split(" ")[0][1:]
        if type_raw == "gay":
            type_: Literal["gay"] = "gay"
        else:
            type_: Literal["sexy"] = "sexy"

        m = await msg.reply_text(f"Calculating {type_} level percentage...")

        logger.info("calculating, type: %s, userid: %s", type_, msg.from_user.id)
        data_raw = db.data.get(str(msg.from_user.id))
        if not data_raw:
            epoch = datetime.datetime.fromtimestamp(0, datetime.UTC).isoformat()
            data_raw = asdict(UserData(0, 0, epoch))
            logger.info("user had no prior data, setting to %s", data_raw)

        data = UserData(**data_raw)
        if datetime.datetime.now(datetime.UTC).date() != datetime.datetime.fromisoformat(data.date).date():
            logger.info("user data expired, regenerating")
            data.date = datetime.datetime.now(datetime.UTC).isoformat()
            data.gayness_percentage = random.randint(RAND_PERCENT_MIN, RAND_PERCENT_MAX)  # noqa: S311
            data.sexiness_percentage = random.randint(RAND_PERCENT_MIN, RAND_PERCENT_MAX)  # noqa: S311

        logger.info("user data is %s", data)
        db.data[str(msg.from_user.id)] = asdict(data)
        percentage = data.gayness_percentage if type_ == "gay" else data.sexiness_percentage
        resets_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
        user_full_name = msg.from_user.full_name
        user_id = msg.from_user.id
        await m.edit_text(
            f"__Today [{user_full_name}](tg://user?id={user_id}) is **{percentage}% {type_}**. "
            f"Resets at {resets_at.date()} UTC(+0).__"
        )

    @override
    def register_handlers(self) -> RegisterHandlersResult:
        return RegisterHandlersResult(
            handlers=[
                MessageHandler(self.random_percentage, filters.command(["sexy", "gay"], prefixes=self.prefixes)),
            ],
        )
