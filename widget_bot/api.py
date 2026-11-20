"""Сырые запросы к Bot API: в aiogram методов виджетов (Bot API 10.4) пока нет."""

from __future__ import annotations

import logging

import aiohttp

log = logging.getLogger(__name__)


class ApiError(Exception):
    pass


class Api:
    def __init__(self, token: str, session: aiohttp.ClientSession, base: str = "https://api.telegram.org"):
        self.url = f"{base}/bot{token}/"
        self.session = session

    async def __call__(self, method: str, **params):
        params = {k: v for k, v in params.items() if v is not None}
        timeout = aiohttp.ClientTimeout(total=params.get("timeout", 0) + 20)
        async with self.session.post(self.url + method, json=params, timeout=timeout) as resp:
            body = await resp.json()
        if not body.get("ok"):
            log.warning("%s failed: %s", method, body.get("description"))
            raise ApiError(body.get("description", "error"))
        return body["result"]
