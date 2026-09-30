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

"""Shared utility helpers used across multiple plugins."""

import typing
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from _typeshed import DataclassInstance


def _get_list_inner_type(t: Any) -> type | None:
    """Returns the inner type of list[X], or None if not a list generic."""
    origin = typing.get_origin(t)
    if origin is list:
        args = typing.get_args(t)
        if args:
            return args[0]
    return None


def from_dict[T: "DataclassInstance"](cls: type[T], data: Mapping[str, Any]) -> T:
    """Recursively convert a plain dict into a dataclass instance.

    Supports nested dataclasses and ``list[SomeDataclass]`` fields.
    This is a superset of the ``dict_to_dataclass`` helper that previously
    existed in ``solat.py`` -- it has been consolidated here so every plugin
    can share a single, well-tested implementation.
    """
    hints: dict[str, Any] = typing.get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        value: Any = data[f.name]
        actual_type: Any = hints[f.name]

        if is_dataclass(actual_type) and isinstance(actual_type, type):
            value = from_dict(actual_type, value)
        else:
            inner: type | None = _get_list_inner_type(actual_type)
            if inner is not None and is_dataclass(inner):
                value = [from_dict(inner, item) for item in value]

        kwargs[f.name] = value
    return cls(**kwargs)
