"""Прогон виджета в браузере и снимки для витрины.

Виджет живёт в iframe внутри макета чата Telegram. Вместо приложения Telegram —
подмена TelegramWidget из документации (core.telegram.org/bots/widgets,
«A first look in a browser»), а запросы виджета уходят в настоящую логику бота
(widget_bot.logic) — тот же разбор, те же записи и то же состояние сообщения.

/home/deploy/pw-venv/bin/python tools/shoot.py [папка_снимков]
Выход с кодом 1, если в консоли виджета были ошибки или сценарий не дошёл до конца.
"""

from __future__ import annotations

import html as H
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from widget_bot import logic  # noqa: E402
from widget_bot.catalog import Catalog  # noqa: E402
from widget_bot.store import Store  # noqa: E402
from widget_bot.widget import render  # noqa: E402

NOW = datetime(2026, 11, 20, 6, 30, tzinfo=UTC)  # 09:30 по Москве
KEY = "42:7"
USER = {"id": 42, "first_name": "Ира"}

THEMES = {
    "light": dict(
        page="#d9e3ea",
        head="#fff",
        bubble="#fff",
        out="#effdde",
        text="#000",
        hint="#707579",
        link="#3390ec",
        button="#3390ec",
        btext="#fff",
        second="#f1f1f4",
        destr="#e53935",
    ),
    "dark": dict(
        page="#0e1621",
        head="#17212b",
        bubble="#182533",
        out="#2b5278",
        text="#f5f5f5",
        hint="#7f91a4",
        link="#6ab3f3",
        button="#5288c1",
        btext="#fff",
        second="#232e3c",
        destr="#ec3942",
    ),
}

STANDIN = """<script>
(function(){try{localStorage.clear()}catch(e){}const h={};
window.TelegramWidget={profile:1,isProfileAtLeast:n=>n<=1,colorScheme:'%(scheme)s',
themeParams:{},isActive:true,isPreview:false,isForward:false,chatType:'private',viewer:{id:42,first_name:'Ира'},
chatData:%(chat)s,publicData:null,HapticFeedback:{selectionChanged(){return this},impactOccurred(){return this},
notificationOccurred(){return this}},onEvent:(e,f)=>(h[e]=h[e]||[]).push(f),offEvent(){},ready(){},
setResizeAnchor(){},watchPublicData(){},unwatchPublicData(){},openLink(){},openTelegramLink(){},copyText(){},
request:d=>parent.botRequest(d).then(r=>{if(r.chat!==null)window.__push(r.chat);return{result:r.answer}})};
window.__push=c=>{TelegramWidget.chatData=c;setTimeout(()=>(h.chatDataChanged||[]).forEach(f=>f()),0)};})();
</script>"""


def theme_vars(t: dict) -> str:
    return (
        f":root{{--tg-theme-bg-color:{t['bubble']};--tg-theme-text-color:{t['text']};"
        f"--tg-theme-hint-color:{t['hint']};--tg-theme-link-color:{t['link']};"
        f"--tg-theme-button-color:{t['button']};--tg-theme-button-text-color:{t['btext']};"
        f"--tg-theme-secondary-bg-color:{t['second']};--tg-theme-destructive-text-color:{t['destr']};"
        f"color:{t['text']};background:{t['bubble']}}}"
    )


def page_html(widget: str, chat: str, theme: str) -> str:
    t = THEMES[theme]
    inner = f"<style>{theme_vars(t)}</style>" + STANDIN % {"scheme": theme, "chat": json.dumps(chat)} + widget
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:{t["page"]};font:15px system-ui;color:{t["text"]}}}
.sheet{{width:390px;padding-bottom:14px;background:{t["page"]}}}
.top{{display:flex;align-items:center;gap:10px;padding:10px 14px;background:{t["head"]}}}
.av{{width:38px;height:38px;border-radius:50%;background:linear-gradient(#b59cf0,#8a6ad8);color:#fff;
display:flex;align-items:center;justify-content:center;font-weight:600}}
.nm{{font-weight:600}} .bt{{font-size:13px;color:{t["hint"]}}}
.out{{margin:12px 12px 8px auto;width:max-content;background:{t["out"]};border-radius:14px 14px 4px 14px;
padding:6px 10px}}
.in{{margin:0 auto 0 8px;width:350px;background:{t["bubble"]};border-radius:14px 14px 14px 4px;overflow:hidden}}
iframe{{border:0;width:100%;display:block}}
.tm{{font-size:12px;color:{t["hint"]};text-align:right;padding:0 10px 6px}}
</style></head><body><div class="sheet">
<div class="top"><div class="av">Л</div><div><div class="nm">Лаванда · запись</div><div class="bt">бот</div></div></div>
<div class="out">/start</div>
<div class="in"><iframe id="w" srcdoc="{H.escape(inner, quote=True)}"></iframe><div class="tm">9:31</div></div>
</div></body></html>"""


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screens"
    out.mkdir(parents=True, exist_ok=True)
    cat = Catalog.load(ROOT / "data" / "catalog.json")
    widget = render(cat)
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in ("light", "dark"):
            store = Store(Path(tmp) / f"{theme}.json")
            # чужие записи — чтобы в сетке было занятое время
            for i, (m, d, t) in enumerate(
                [
                    (2, "1121", "1100"),
                    (2, "1121", "1500"),
                    (2, "1121", "1600"),
                    (1, "1121", "1300"),
                    (2, "1122", "1200"),
                ]
            ):
                store.bookings[f"o:{i}"] = {"s": "ok", "svc": 1, "m": m, "d": d, "t": t, "n": "1", "user": 1}

            def bot_request(data: str, store=store) -> dict:
                res = logic.handle(cat, store, KEY, USER, data, NOW)
                chat = logic.chat_data(cat, store, KEY, NOW) if res.changed else None
                return {"answer": json.dumps(res.answer, ensure_ascii=False), "chat": chat}

            page = browser.new_page(viewport={"width": 390, "height": 900}, device_scale_factor=2)
            page.expose_function("botRequest", bot_request)
            page.on("console", lambda m: m.type == "error" and problems.append(f"console: {m.text}"))
            page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
            src = Path(tmp) / f"{theme}.html"  # с file:// у виджета есть localStorage, как в Telegram
            src.write_text(page_html(widget, logic.chat_data(cat, store, KEY, NOW), theme), encoding="utf-8")
            page.goto(src.as_uri())
            page.set_default_timeout(5000)
            frame = page.frame_locator("#w")
            fr = page.frames[1]

            def fit(page=page, fr=fr) -> None:
                page.wait_for_timeout(150)
                page.evaluate("document.getElementById('w').style.height='1px'")
                h = fr.evaluate("document.documentElement.scrollHeight")
                page.evaluate(f"document.getElementById('w').style.height='{h}px'")

            def shot(name: str, page=page, theme=theme) -> None:
                fit()
                path = out / (f"{name}.png" if theme == "light" else f"{name}-dark.png")
                page.locator(".sheet").screenshot(path=str(path))
                print(path)

            fit()
            shot("1-usluga")
            frame.get_by_role("button", name="Стрижка").click()
            frame.get_by_role("button", name="Марина").click()
            frame.get_by_role("button", name="Завтра").click()
            if not frame.get_by_role("button", name="15:00").is_disabled():
                problems.append("занятое 15:00 не зачёркнуто")
            frame.get_by_role("button", name="14:00").click()
            shot("2-vybor")
            frame.get_by_role("button", name="Записаться · 1 800 ₽").click()
            frame.get_by_text("Заявка отправлена").wait_for(timeout=3000)
            shot("3-zayavka")
            # салон подтвердил: бот меняет состояние того же сообщения
            store.set_status(KEY, "ok")
            fr.evaluate("c => window.__push(c)", logic.chat_data(cat, store, KEY, NOW))
            frame.get_by_text("Вы записаны").wait_for(timeout=3000)
            shot("4-zapisan")
            # отмена клиентом и повторная запись
            frame.get_by_role("button", name="Отменить запись").click()
            frame.get_by_text("Запись отменена").wait_for(timeout=3000)
            if theme == "light":
                shot("5-otmena")
            frame.get_by_role("button", name="Записаться снова").click()
            frame.get_by_role("button", name="Записаться · 1 800 ₽").wait_for(state="detached", timeout=3000)
            # переполнение по ширине
            over = fr.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
            if over:
                problems.append(f"{theme}: виджет шире пузыря")
            page.close()
        browser.close()
    for pr in problems:
        print("PROBLEM", pr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
