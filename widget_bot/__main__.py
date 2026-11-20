"""python -m widget_bot — запуск бота (настройки из окружения или .env)."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import aiohttp

from .api import Api
from .bot import Bot
from .catalog import Catalog
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> None:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.partition("=")
            if sep and not k.startswith("#"):
                os.environ.setdefault(k.strip(), v.strip())


async def main() -> None:
    load_env(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    admin = os.environ.get("ADMIN_CHAT_ID", "").strip()
    async with aiohttp.ClientSession() as session:
        bot = Bot(
            Api(os.environ["BOT_TOKEN"], session),
            Catalog.load(ROOT / "data" / "catalog.json"),
            Store(ROOT / "data" / "bookings.json"),
            admin_chat=int(admin) if admin else None,
        )
        await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
