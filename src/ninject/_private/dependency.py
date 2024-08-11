from __future__ import annotations

from contextvars import ContextVar
from weakref import WeakKeyDictionary


def get_dependency_name(anno: type) -> str:
    return get_dependency_var(anno).name


def is_dependency_type(anno: type) -> bool:
    return anno in _VARS_BY_DEPENDENCY_TYPE


def add_dependency_type(name: str, anno: type) -> None:
    _VARS_BY_DEPENDENCY_TYPE[anno] = ContextVar(name)


def get_dependency_var(anno: type) -> ContextVar:
    return _VARS_BY_DEPENDENCY_TYPE.setdefault(anno, ContextVar(anno.__name__))


_VARS_BY_DEPENDENCY_TYPE: WeakKeyDictionary[type, ContextVar] = WeakKeyDictionary()
