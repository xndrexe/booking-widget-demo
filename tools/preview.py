"""Собрать ui/preview.html — виджет отдельной страницей для проверки в браузере (ui-check).

Вместо Telegram — подмена TelegramWidget, а запросы обрабатывает маленькая
заглушка на JS: заявка → «ждёт», отмена → «отменена». Настоящая логика бота
проверяется тестами и tools/shoot.py; здесь — только вёрстка и клики.

python3 tools/preview.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from widget_bot.catalog import Catalog  # noqa: E402
from widget_bot.widget import render  # noqa: E402

STANDIN = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Виджет записи — превью</title>
<style>:root{--tg-theme-bg-color:#fff;--tg-theme-text-color:#000;--tg-theme-hint-color:#707579;
--tg-theme-link-color:#3390ec;--tg-theme-button-color:#3390ec;--tg-theme-button-text-color:#fff;
--tg-theme-secondary-bg-color:#f1f1f4;--tg-theme-destructive-text-color:#e53935}</style>
<script>
(function(){const h={},p=n=>String(n).padStart(2,'0'),now=new Date(),days=[0,1,2].map(i=>{
const d=new Date(now.getFullYear(),now.getMonth(),now.getDate()+i);return p(d.getMonth()+1)+p(d.getDate())});
const busy={['2:'+days[1]]:['1100','1500','1600'],['1:'+days[1]]:['1300']};let st={days,busy};
const push=()=>{TelegramWidget.chatData=JSON.stringify(st);setTimeout(()=>(h.chatDataChanged||[]).forEach(f=>f()),0)};
window.TelegramWidget={profile:1,isProfileAtLeast:n=>n<=1,colorScheme:'light',themeParams:{},isActive:true,
isPreview:false,isForward:false,chatType:'private',viewer:{id:42,first_name:'Ира'},chatData:JSON.stringify(st),
publicData:null,HapticFeedback:{selectionChanged(){return this},impactOccurred(){return this},
notificationOccurred(){return this}},onEvent:(e,f)=>(h[e]=h[e]||[]).push(f),offEvent(){},ready(){},
setResizeAnchor(){},watchPublicData(){},unwatchPublicData(){},openLink(){},openTelegramLink(){},copyText(){},
request(q){return new Promise(ok=>setTimeout(()=>{let a={ok:1};const b=q.split(':');
if(q=='r')a={busy:st.busy,days:st.days};
else if(b[0]=='b'){st.bk={s:'wait',svc:+b[1],m:+b[2],d:b[3],t:b[4],n:'2417'};push()}
else if(q=='x'&&st.bk){st.bk.s='cancel';push()}
ok({result:JSON.stringify(a)})},150))}};
})();
</script></head><body>
"""

FRAME = """<style>html{background:#d9e3ea}body{max-width:350px;margin:24px auto;background:#fff;
border-radius:14px;color:#000}</style></body></html>
"""


def main() -> None:
    cat = Catalog.load(ROOT / "data" / "catalog.json")
    out = ROOT / "ui" / "preview.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(STANDIN + render(cat) + FRAME, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
