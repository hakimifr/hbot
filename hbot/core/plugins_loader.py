import importlib.util
import inspect
import logging
from collections.abc import Iterable
from os import PathLike
from pathlib import Path

from pyrogram.client import Client
from pyrogram.handlers.handler import Handler

from hbot import PLUGINS_DIR
from hbot.core.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


async def load_plugins(app: Client, plugins_dir: PathLike | str = PLUGINS_DIR) -> dict[BasePlugin, list[Handler]]:
    loaded: dict[BasePlugin, list[Handler]] = {}
    plugins: Iterable[PathLike] = Path(plugins_dir).resolve().glob("*.py")

    for file in plugins:
        if file.name.startswith("_"):
            continue

        logger.info("loading: '%s'", file.name)

        module_name = f"dynamically_loaded_plugin_{file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file)

        if spec is None or spec.loader is None:
            logger.error("could not load plugin '%s'", file.name)
            continue

        module = importlib.util.module_from_spec(spec)  # type: ignore
        spec.loader.exec_module(module)  # type:plugins ignore

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, BasePlugin) and attr is not BasePlugin:
                logger.info("instantiating plugin class '%s'", attr.name)
                plugin_instance: BasePlugin = attr(app)

                logger.info("calling register_handlers for plugin '%s'", attr.name)
                handlers_or_coro = plugin_instance.register_handlers()

                # Check if the result is a coroutine and handle accordingly
                if inspect.iscoroutine(handlers_or_coro):
                    logger.info("register_handlers is async for plugin '%s', awaiting it", attr.name)
                    handlers: list[Handler] = await handlers_or_coro  # type: ignore
                else:
                    logger.info("register_handlers is sync for plugin '%s'", attr.name)
                    handlers: list[Handler] = handlers_or_coro  # type: ignore

                if not isinstance(handlers, list):
                    raise ValueError("method register_handlers MUST return list[Handler]!")

                logger.info("registering %d handler(s) for plugin '%s'", len(handlers), attr.name)
                for h in handlers:
                    app.add_handler(h)

                loaded.update({plugin_instance: handlers})

                logger.info("loaded plugin '%s'. desc: '%s'", attr.name, attr.description)

    return loaded
