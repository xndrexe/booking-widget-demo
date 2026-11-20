"""Записи в JSON-файле. Ключ записи — сообщение с виджетом: «chat:message»."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

ACTIVE = ("wait", "ok")  # эти статусы держат время


class SlotTaken(Exception):
    pass


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.bookings: dict[str, dict] = {}
        if path.exists():
            self.bookings = json.loads(path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.bookings, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, key: str) -> dict | None:
        return self.bookings.get(key)

    def taken(self) -> set[tuple[int, str, str]]:
        return {(b["m"], b["d"], b["t"]) for b in self.bookings.values() if b["s"] in ACTIVE}

    def book(self, key: str, user: dict, svc: int, master: int, day: str, hhmm: str) -> dict:
        if (master, day, hhmm) in self.taken():
            raise SlotTaken
        bk = {
            "s": "wait",
            "svc": svc,
            "m": master,
            "d": day,
            "t": hhmm,
            "n": f"{secrets.randbelow(9000) + 1000}",
            "user": user.get("id"),
            "name": user.get("first_name", ""),
        }
        self.bookings[key] = bk
        self._save()
        return bk

    def set_status(self, key: str, status: str) -> dict | None:
        bk = self.bookings.get(key)
        if bk is None:
            return None
        bk["s"] = status
        self._save()
        return bk
