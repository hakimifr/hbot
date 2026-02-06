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

import importlib.util
import inspect
import logging
from collections.abc import Iterable
from os import PathLike
from pathlib import Path
from typing import cast

from pyrogram.client import Client
from pyrogram.handlers.handler import Handler

from hbot import PLUGINS_DIR
from hbot.core.base_plugin import BasePlugin, RegisterHandlersResult

logger = logging.getLogger(__name__)


async def load_plugins(app: Client, plugins_dir: PathLike | str = PLUGINS_DIR) -> dict[BasePlugin, list[Handler]]:
    """This function loads every plugin under hbot/plugins/* (:ref:`PLUGINS_DIR`) directory.

    Note that this loader will look for classes that inherits the :ref:`BasePlugin` abstract class,
    and calls the :py:meth:`hbot.core.base_plugin.BasePlugin.register_handlers` method.

    Args:
        app: The :ref:`Client` instance of pyrogram.
        plugins_dir: :ref:`PathLike` object of the directory containing plugins to load.
            Defaults to :py:attr:`hbot.PLUGINS_DIR`.

    Returns:
        A dictionary where the instance of the subclass of :ref:`BasePlugin` is the key, and the
        list of the handlers returned by the :py:meth:`hbot.core.base_plugin.BasePlugin.register_handlers`
        method is the value.

    Raises:
        ValueError: When the :py:meth:`hbot.core.base_plugin.BasePlugin.register_handlers` method does not
        return list of handlers.
    """
    loaded: dict[BasePlugin, list[Handler]] = {}
    plugins: Iterable[PathLike] = Path(plugins_dir).resolve().glob("*.py")

    for file in plugins:
        if file.name.startswith("_"):
            continue

        logger.info("loading: '%s'", file.name)

        module_name = f"plugin_{file.stem}"
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
                    reg_handlers_result: RegisterHandlersResult = cast(RegisterHandlersResult, await handlers_or_coro)
                else:
                    logger.info("register_handlers is sync for plugin '%s'", attr.name)
                    reg_handlers_result: RegisterHandlersResult = cast(RegisterHandlersResult, handlers_or_coro)

                handlers = reg_handlers_result.handlers

                if not isinstance(handlers, list):
                    raise ValueError(
                        "method register_handlers MUST return RegisterHandlerResult.handlers with type list[Handler]!"
                    )

                logger.info("registering %d handler(s) for plugin '%s'", len(handlers), attr.name)
                for h in handlers:
                    app.add_handler(h, group=reg_handlers_result.group)

                loaded.update({plugin_instance: handlers})

                logger.info("loaded plugin '%s'. desc: '%s'", attr.name, attr.description)

    return loaded
