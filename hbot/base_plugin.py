from pyrogram.client import Client
from pyrogram.handlers.handler import Handler


class BasePlugin:
    name: str = "Unnamed Plugin"
    description: str = "No description"

    def __init__(self, app: Client) -> None:
        self.app: Client = app
        self.register_handlers()

    def register_handlers(self) -> list[Handler]:
        raise NotImplementedError("a plugin must implement this method")
