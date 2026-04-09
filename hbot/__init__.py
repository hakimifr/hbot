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

import inspect
from os import getenv
from pathlib import Path


def getenv_nofail(env_var: str) -> str:
    var = getenv(env_var)
    if var is None:
        raise ValueError(f"variable {env_var} is not set")

    return var


def gentenv_bool(env_var: str) -> bool:
    var = getenv(env_var, False)
    return bool(var)


PLUGINS_DIR: Path = Path(inspect.getfile(lambda _: _)).parent.joinpath("plugins")

_persist_dir = getenv("PERSIST_DIR") or "/persist/storage"
PERSIST_DIR: Path = Path(_persist_dir)

BOTAUTHTOKEN: str = getenv_nofail("BOTAUTHTOKEN")
BOTOWNERID: str = getenv_nofail("BOTOWNERID")
PHONENUMBER: str = getenv_nofail("PHONENUMBER")
LOCALRUN: bool = gentenv_bool("LOCALRUN")

if any((BOTAUTHTOKEN is None, BOTOWNERID is None, PHONENUMBER is None)):
    raise RuntimeError("some environment variable aren't set")
