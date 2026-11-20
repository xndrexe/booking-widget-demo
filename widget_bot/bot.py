"""Бот: /start шлёт виджет записи, запросы виджета меняют запись в том же сообщении."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import aiohttp

from . import logic
from .api import Api, ApiError
from .catalog import Catalog
from .store import Store
from .widget import render

log = logging.getLogger(__name__)
UPDATES = ["message", "callback_query", "widget_query"]


def _now() -> datetime:
    return datetime.now(UTC)


class Bot:
    def __init__(
        self,
        api: Api,
        cat: Catalog,
        store: Store,
        admin_chat: int | None = None,
        autoconfirm: float = 3.0,
        now: Callable[[], datetime] = _now,
    ):
        self.api, self.cat, self.store = api, cat, store
        self.admin_chat = admin_chat
        self.autoconfirm = autoconfirm
        self.now = now
        self.html = render(cat)
        self.tasks: set[asyncio.Task] = set()

    async def on_update(self, upd: dict) -> None:
        if "widget_query" in upd:
            await self.on_widget(upd["widget_query"])
        elif "callback_query" in upd:
            await self.on_callback(upd["callback_query"])
        elif "message" in upd:
            await self.on_message(upd["message"])

    async def on_message(self, msg: dict) -> None:
        chat = msg["chat"]
        if not (msg.get("text") or "").startswith("/start"):
            return
        if chat["type"] != "private":  # в бою виджеты пока только в личке
            await self.api("sendMessage", chat_id=chat["id"], text="Записаться можно в личном чате с ботом.")
            return
        sent = await self.api(
            "sendWidget",
            chat_id=chat["id"],
            html=self.html,
            chat_data=logic.chat_data(self.cat, self.store, "", self.now()),
            allow_queries=True,
        )
        log.info("widget sent chat=%s message=%s", chat["id"], sent.get("message_id"))

    async def on_widget(self, q: dict) -> None:
        if "chat" not in q:  # инлайн и пересылки в бою закрыты
            await self.api("answerWidgetQuery", widget_query_id=q["id"], data='{"err":"Откройте бота в личке"}')
            return
        key = f"{q['chat']['id']}:{q['message_id']}"
        res = logic.handle(self.cat, self.store, key, q["from"], q.get("data", ""), self.now())
        # ответить — в пределах 15 секунд, медленное — после
        await self.api(
            "answerWidgetQuery",
            widget_query_id=q["id"],
            data=json.dumps(res.answer, ensure_ascii=False, separators=(",", ":")),
        )
        if res.changed:
            await self.push(key)
        if res.new_booking is not None:
            await self.notify(key, res.new_booking)

    async def push(self, key: str) -> None:
        chat_id, message_id = key.split(":")
        await self.api(
            "editMessageWidgetData",
            chat_id=int(chat_id),
            message_id=int(message_id),
            chat_data=logic.chat_data(self.cat, self.store, key, self.now()),
        )

    def describe(self, bk: dict) -> str:
        s, m = self.cat.services[bk["svc"]], self.cat.masters[bk["m"]]
        return f"{s['name']} у {m['name']}, {bk['d'][2:]}.{bk['d'][:2]} в {bk['t'][:2]}:{bk['t'][2:]}"

    async def notify(self, key: str, bk: dict) -> None:
        if self.admin_chat is None:  # демо без салона: подтверждаем сами через пару секунд
            task = asyncio.create_task(self._autoconfirm(key))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return
        await self.api(
            "sendMessage",
            chat_id=self.admin_chat,
            text=f"Новая запись №{bk['n']}: {self.describe(bk)}. Клиент: {bk['name']}",
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": "Подтвердить", "callback_data": f"ok|{key}"},
                        {"text": "Отклонить", "callback_data": f"no|{key}"},
                    ]
                ]
            },
        )

    async def _autoconfirm(self, key: str) -> None:
        await asyncio.sleep(self.autoconfirm)
        await self.decide(key, "ok")

    async def decide(self, key: str, status: str) -> bool:
        bk = self.store.get(key)
        if bk is None or bk["s"] != "wait":
            return False
        self.store.set_status(key, status)
        try:
            await self.push(key)
        except ApiError:
            log.exception("push failed key=%s", key)
        return True

    async def on_callback(self, cb: dict) -> None:
        msg = cb.get("message") or {}
        action, _, key = (cb.get("data") or "").partition("|")
        if self.admin_chat is None or msg.get("chat", {}).get("id") != self.admin_chat or action not in ("ok", "no"):
            await self.api("answerCallbackQuery", callback_query_id=cb["id"])
            return
        done = await self.decide(key, action)
        await self.api(
            "answerCallbackQuery",
            callback_query_id=cb["id"],
            text=("Подтверждено" if action == "ok" else "Отклонено") if done else "Запись уже изменена",
        )
        if done:
            mark = "✅ подтверждена" if action == "ok" else "❌ отклонена"
            await self.api(
                "editMessageText",
                chat_id=self.admin_chat,
                message_id=msg["message_id"],
                text=f"{msg.get('text', '')}\n\nЗапись {mark}",
            )

    async def run(self) -> None:
        offset = 0
        while True:
            try:
                updates = await self.api("getUpdates", offset=offset, timeout=30, allowed_updates=UPDATES)
            except (ApiError, aiohttp.ClientError, OSError, TimeoutError) as e:
                log.warning("getUpdates: %s", e)
                await asyncio.sleep(3)
                continue
            for upd in updates:
                offset = upd["update_id"] + 1
                try:
                    await self.on_update(upd)
                except Exception:
                    log.exception("update %s failed", upd.get("update_id"))
