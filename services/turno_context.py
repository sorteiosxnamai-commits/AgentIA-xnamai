"""Flags do turno atual (dry_run / persistir) — contextvars, sem secrets."""

from __future__ import annotations

from contextvars import ContextVar

_dry_run: ContextVar[bool] = ContextVar("turno_dry_run", default=False)
_persistir: ContextVar[bool] = ContextVar("turno_persistir", default=True)


def set_turno_flags(*, dry_run: bool = False, persistir: bool = True) -> None:
    _dry_run.set(bool(dry_run))
    _persistir.set(bool(persistir))


def get_dry_run() -> bool:
    return bool(_dry_run.get())


def get_persistir() -> bool:
    return bool(_persistir.get())
