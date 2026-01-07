import inspect
from os import getenv
from pathlib import Path

PLUGINS_DIR: Path = Path(inspect.getfile(lambda _: _)).parent.joinpath("plugins")

_persist_dir = getenv("PERSIST_DIR") or "/persist/storage"
PERSIST_DIR: Path = Path(_persist_dir)
