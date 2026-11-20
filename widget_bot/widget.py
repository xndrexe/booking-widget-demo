"""HTML виджета: шаблон + каталог салона. Пределы — из документации Bot API 10.4."""

from __future__ import annotations

import json
import zlib
from pathlib import Path

from .catalog import Catalog

TEMPLATE = Path(__file__).with_name("widget.html")
MAX_BYTES = 32768
MAX_ZLIB = 4096


def catalog_json(cat: Catalog) -> str:
    data = {
        "salon": cat.salon,
        "hours": list(cat.hours),
        "services": list(cat.services.values()),
        "masters": [{"id": m["id"], "name": m["name"], "services": m["services"]} for m in cat.masters.values()],
    }
    # </ в строках не даст закрыть <script> раньше времени
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def render(cat: Catalog) -> str:
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*CATALOG*/{}", catalog_json(cat))
    raw = html.encode()
    if len(raw) > MAX_BYTES or len(zlib.compress(raw, 9)) > MAX_ZLIB:
        raise ValueError(f"widget too large: {len(raw)} bytes, {len(zlib.compress(raw, 9))} zlib")
    return html
