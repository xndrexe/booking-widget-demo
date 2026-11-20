"""Разбор запросов виджета и состояние, которое бот кладёт в сообщение.

Запрос виджета — до 64 байт:
  r                      — обновить занятое время;
  b:<услуга>:<мастер>:<MMDD>:<HHMM> — записаться;
  x                      — отменить свою запись.
Ответ и состояние — JSON, до 1024 байт.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from .catalog import Catalog, days, too_late
from .store import SlotTaken, Store

LIMIT = 1024


@dataclass
class Result:
    answer: dict  # уйдёт виджету в answerWidgetQuery
    changed: bool = False  # нужно переписать chat_data сообщения
    new_booking: dict | None = None  # уведомить салон


def busy(cat: Catalog, store: Store, now: datetime) -> dict[str, list[str]]:
    """Занятое и уже недоступное время: {"мастер:MMDD": ["HHMM", …]}."""
    taken = store.taken()
    out: dict[str, list[str]] = {}
    for d in days(cat, now):
        for m in cat.masters:
            hh = [
                h.replace(":", "")
                for h in cat.hours
                if (m, d, h.replace(":", "")) in taken or too_late(d, h.replace(":", ""), now)
            ]
            if hh:
                out[f"{m}:{d}"] = hh
    return out


def chat_data(cat: Catalog, store: Store, key: str, now: datetime) -> str:
    bk = store.get(key)
    state: dict = {"days": days(cat, now), "busy": busy(cat, store, now)}
    if bk is not None:
        state["bk"] = {k: bk[k] for k in ("s", "svc", "m", "d", "t", "n")}
    text = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode()) > LIMIT:  # сетка не влезла — отдаём хотя бы запись
        state["busy"] = {}
        text = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    return text


def handle(cat: Catalog, store: Store, key: str, user: dict, data: str, now: datetime) -> Result:
    if data == "r":
        return Result({"busy": busy(cat, store, now), "days": days(cat, now)})
    if data == "x":
        bk = store.get(key)
        if bk is None or bk["s"] not in ("wait", "ok") or bk["user"] != user.get("id"):
            return Result({"err": "Записи нет"})
        store.set_status(key, "cancel")
        return Result({"ok": 1}, changed=True)
    if data.startswith("b:"):
        return _book(cat, store, key, user, data, now)
    return Result({"err": "Не понял запрос"})


def _book(cat: Catalog, store: Store, key: str, user: dict, data: str, now: datetime) -> Result:
    parts = data.split(":")
    if len(parts) != 5 or not all(p.isdigit() for p in parts[1:]):
        return Result({"err": "Не понял запрос"})
    svc, master, day, hhmm = int(parts[1]), int(parts[2]), parts[3], parts[4]
    hours = {h.replace(":", "") for h in cat.hours}
    if svc not in cat.services or not cat.does(master, svc):
        return Result({"err": "Этот мастер не делает такую услугу"})
    if day not in days(cat, now) or hhmm not in hours or too_late(day, hhmm, now):
        return Result({"err": "На это время уже не записаться", "busy": busy(cat, store, now)})
    old = store.get(key)
    if old is not None and old["s"] in ("wait", "ok"):
        return Result({"err": "Вы уже записаны"})
    try:
        bk = store.book(key, user, svc, master, day, hhmm)
    except SlotTaken:
        return Result({"err": "Это время только что заняли", "busy": busy(cat, store, now)})
    return Result({"ok": 1}, changed=True, new_booking=bk)
