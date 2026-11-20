import json
import re
import zlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from widget_bot import logic
from widget_bot.bot import Bot
from widget_bot.catalog import Catalog, days, too_late
from widget_bot.store import Store
from widget_bot.widget import render

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)  # 12:00 по Москве
USER = {"id": 42, "first_name": "Ира"}


@pytest.fixture
def cat():
    return Catalog.load(ROOT / "data" / "catalog.json")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "b.json")


class FakeApi:
    def __init__(self):
        self.calls = []

    async def __call__(self, method, **params):
        self.calls.append((method, params))
        return {"message_id": 7} if method.startswith("send") else True

    def names(self):
        return [c[0] for c in self.calls]


# --- сетка и разбор запросов


def test_days_and_lead(cat):
    assert days(cat, NOW) == ["1120", "1121", "1122"]
    assert too_late("1120", "1200", NOW)  # уже идёт
    assert too_late("1120", "1259", NOW)  # меньше часа
    assert not too_late("1120", "1300", NOW)


def test_days_cross_new_year(cat):
    dec31 = datetime(2026, 12, 31, 7, 0, tzinfo=UTC)
    assert days(cat, dec31) == ["1231", "0101", "0102"]
    assert not too_late("0101", "1000", dec31)


def test_book_and_slot_taken(cat, store):
    r = logic.handle(cat, store, "1:1", USER, "b:1:1:1121:1400", NOW)
    assert r.answer == {"ok": 1} and r.changed and r.new_booking["s"] == "wait"
    other = logic.handle(cat, store, "2:5", {"id": 7}, "b:2:1:1121:1400", NOW)
    assert other.answer["err"] == "Это время только что заняли"
    assert "1400" in other.answer["busy"]["1:1121"]


def test_book_rejects_bad_input(cat, store):
    bad = ["b:1:3:1121:1400", "b:9:1:1121:1400", "b:1:1:1201:1400", "b:1:1:1121:0930", "b:1:1:1120:1200", "b:x", "zz"]
    for data in bad:
        assert "err" in logic.handle(cat, store, "1:1", USER, data, NOW).answer, data
    assert store.bookings == {}


def test_one_active_booking_per_message(cat, store):
    logic.handle(cat, store, "1:1", USER, "b:1:1:1121:1400", NOW)
    again = logic.handle(cat, store, "1:1", USER, "b:1:1:1121:1500", NOW)
    assert again.answer == {"err": "Вы уже записаны"}


def test_cancel_frees_slot_and_rebook(cat, store):
    logic.handle(cat, store, "1:1", USER, "b:1:1:1121:1400", NOW)
    assert logic.handle(cat, store, "1:1", {"id": 999}, "x", NOW).answer == {"err": "Записи нет"}
    assert logic.handle(cat, store, "1:1", USER, "x", NOW).changed
    assert "1:1121" not in logic.busy(cat, store, NOW)
    assert logic.handle(cat, store, "1:1", USER, "b:1:1:1121:1500", NOW).answer == {"ok": 1}


def test_store_survives_restart(cat, store):
    logic.handle(cat, store, "1:1", USER, "b:1:1:1121:1400", NOW)
    again = Store(store.path)
    assert again.get("1:1")["t"] == "1400"


def test_today_past_hours_busy(cat, store):
    b = logic.busy(cat, store, NOW)
    assert b["1:1120"] == ["1000", "1100", "1200"]


# --- пределы Bot API 10.4


def test_chat_data_fits_when_all_taken(cat, store):
    i = 0
    for d in days(cat, NOW):
        for m in cat.masters:
            for h in cat.hours:
                store.bookings[f"k{i}"] = {"s": "ok", "m": m, "d": d, "t": h.replace(":", ""), "user": 1}
                i += 1
    store.bookings["1:1"] = {"s": "ok", "svc": 1, "m": 1, "d": "1121", "t": "1400", "n": "1234", "user": 42}
    text = logic.chat_data(cat, store, "1:1", NOW)
    assert len(text.encode()) <= 1024
    assert json.loads(text)["bk"]["n"] == "1234"


def test_requests_fit_64_bytes(cat):
    longest = f"b:{max(cat.services)}:{max(cat.masters)}:1231:1800"
    assert len(longest.encode()) <= 64


def test_widget_size_limits(cat):
    raw = render(cat).encode()
    assert len(raw) <= 32768
    assert len(zlib.compress(raw, 9)) <= 4096


def test_widget_uses_only_profile_1(cat):
    """То, что приложения Telegram вырезают (профиль 1), в шаблон не попадает."""
    html = render(cat)
    forbidden = [
        r"<(input|select|textarea|option|iframe|link|meta|template|form)\b",
        r"<script[^>]+src=",
        r"\bfetch\(|XMLHttpRequest|WebSocket",
        r"\d+vh\b",
        r":has\(|:focus|:checked|position:\s*sticky|overflow:\s*(auto|scroll)",
        r"text-shadow|clip-path|oklch\(|color-mix\(|@font-face|@import",
        r"\balert\(|\bconfirm\(|\bprompt\(|location\.|history\.",
        r"touchstart|keydown|keyup|wheel",
    ]
    for pat in forbidden:
        assert not re.search(pat, html), pat


def test_catalog_cannot_close_script(tmp_path):
    raw = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
    raw["salon"] = "</script><b>x"
    p = tmp_path / "c.json"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    assert "</script><b>" not in render(Catalog.load(p))


# --- бот целиком на подменном Bot API


async def test_start_sends_widget(cat, store):
    api = FakeApi()
    bot = Bot(api, cat, store, now=lambda: NOW)
    await bot.on_update({"message": {"chat": {"id": 42, "type": "private"}, "text": "/start"}})
    method, p = api.calls[0]
    assert method == "sendWidget" and p["allow_queries"] is True
    assert json.loads(p["chat_data"])["days"] == ["1120", "1121", "1122"]


async def test_group_gets_text_not_widget(cat, store):
    api = FakeApi()
    await Bot(api, cat, store).on_update({"message": {"chat": {"id": -5, "type": "group"}, "text": "/start"}})
    assert api.names() == ["sendMessage"]


def wq(data, qid="q1"):
    return {
        "widget_query": {"id": qid, "from": USER, "chat": {"id": 42, "type": "private"}, "message_id": 7, "data": data}
    }


async def test_book_answers_first_then_pushes_and_autoconfirms(cat, store):
    api = FakeApi()
    bot = Bot(api, cat, store, autoconfirm=0, now=lambda: NOW)
    await bot.on_update(wq("b:1:2:1121:1400"))
    assert api.names() == ["answerWidgetQuery", "editMessageWidgetData"]
    assert json.loads(api.calls[1][1]["chat_data"])["bk"]["s"] == "wait"
    for t in list(bot.tasks):
        await t
    assert api.names()[-1] == "editMessageWidgetData"
    assert json.loads(api.calls[-1][1]["chat_data"])["bk"]["s"] == "ok"


async def test_admin_confirms_and_only_admin(cat, store):
    api = FakeApi()
    bot = Bot(api, cat, store, admin_chat=100, now=lambda: NOW)
    await bot.on_update(wq("b:3:3:1121:1600"))
    method, p = api.calls[-1]
    assert method == "sendMessage" and p["chat_id"] == 100
    ok_btn = p["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    stranger = {"id": "c0", "data": ok_btn, "message": {"message_id": 9, "chat": {"id": 555}}}
    await bot.on_update({"callback_query": stranger})
    assert store.get("42:7")["s"] == "wait"
    cb = {"id": "c1", "data": ok_btn, "message": {"message_id": 9, "chat": {"id": 100}, "text": "Новая запись"}}
    await bot.on_update({"callback_query": cb})
    assert store.get("42:7")["s"] == "ok"
    assert "editMessageText" in api.names()
    api.calls.clear()
    await bot.on_update({"callback_query": {**cb, "id": "c2"}})  # второй раз — без изменений
    assert api.names() == ["answerCallbackQuery"]


async def test_refresh_does_not_touch_state(cat, store):
    api = FakeApi()
    await Bot(api, cat, store, now=lambda: NOW).on_update(wq("r"))
    assert api.names() == ["answerWidgetQuery"]
    assert "busy" in json.loads(api.calls[0][1]["data"])


async def test_answer_fits_1024(cat, store):
    api = FakeApi()
    await Bot(api, cat, store, now=lambda: NOW).on_update(wq("r"))
    assert len(api.calls[0][1]["data"].encode()) <= 1024
