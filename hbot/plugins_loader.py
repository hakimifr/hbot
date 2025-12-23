import importlib.util
import logging
from collections.abc import Iterable
from os import PathLike
from pathlib import Path

from pyrogram.client import Client
from pyrogram.handlers.handler import Handler

from hbot import PLUGINS_DIR
from hbot.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


def load_plugins(app: Client, plugins_dir: PathLike | str = PLUGINS_DIR) -> dict[BasePlugin, list[Handler]]:
    loaded: dict[BasePlugin, list[Handler]] = {}
    plugins: Iterable[PathLike] = Path(plugins_dir).resolve().glob("*.py")

    for file in plugins:
        if file.name.startswith("_"):
            continue

        module_name = f"dynamically_loaded_plugin_{file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file)

        if spec is None or spec.loader is None:
            logger.error(f"could not load plugin '{file.name}'")
            continue

        module = importlib.util.module_from_spec(spec)  # type: ignore
        spec.loader.exec_module(module)  # type:plugins ignore

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                plugin_instance: BasePlugin = attr(app)
                handlers: list[Handler] = plugin_instance.register_handlers()

                if not isinstance(handlers, list):
                    raise ValueError("method register_handlers MUST return list[Handler]!")

                loaded.update({plugin_instance: handlers})

                logger.info(f"loaded plugin '{attr.name}'. desc: '{attr.description}'")

    return loaded
