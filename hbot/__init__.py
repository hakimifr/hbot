import inspect
from os import PathLike
from pathlib import Path

PLUGINS_DIR: PathLike = Path(inspect.getfile(lambda _: _)).parent
