"""Каталог салона и сетка свободного времени."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

MSK = timezone(timedelta(hours=3))
LEAD = timedelta(hours=1)  # записаться можно не позже чем за час


@dataclass(frozen=True)
class Catalog:
    salon: str
    days_ahead: int
    hours: tuple[str, ...]
    services: dict[int, dict]
    masters: dict[int, dict]

    @classmethod
    def load(cls, path: Path) -> Catalog:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            salon=raw["salon"],
            days_ahead=raw["days_ahead"],
            hours=tuple(raw["hours"]),
            services={s["id"]: s for s in raw["services"]},
            masters={m["id"]: m for m in raw["masters"]},
        )

    def does(self, master: int, service: int) -> bool:
        m = self.masters.get(master)
        return m is not None and service in m["services"]


def day_id(d: date) -> str:
    return d.strftime("%m%d")


def days(cat: Catalog, now: datetime) -> list[str]:
    """Дни, на которые открыта запись: сегодня и следующие по Москве."""
    today = now.astimezone(MSK).date()
    return [day_id(today + timedelta(days=i)) for i in range(cat.days_ahead)]


def slot_start(day: str, hhmm: str, now: datetime) -> datetime | None:
    """Начало окна по Москве; день MMDD — ближайший такой от сегодня."""
    today = now.astimezone(MSK).date()
    for shift in (0, 1):  # переход через Новый год
        try:
            d = date(today.year + shift, int(day[:2]), int(day[2:]))
        except ValueError:
            return None
        if d >= today:
            return datetime(d.year, d.month, d.day, int(hhmm[:2]), int(hhmm[2:]), tzinfo=MSK)
    return None


def too_late(day: str, hhmm: str, now: datetime) -> bool:
    start = slot_start(day, hhmm, now)
    return start is None or start - now < LEAD
