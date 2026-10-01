"""Фаза 13, задача 3: экран темы — сетки, иконки «свой цвет», «Основа», цвет недели отдыха (--rest)."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")

import re as _re
def has(css, r, g, b):
    """есть ли в строке цвет (rgb() или color(srgb …)) с данными каналами"""
    for m in _re.finditer(r"rgb\(\s*(\d+),\s*(\d+),\s*(\d+)", css):
        if tuple(map(int, m.groups())) == (r, g, b): return True
    for m in _re.finditer(r"color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", css):
        if tuple(round(float(x) * 255) for x in m.groups()) == (r, g, b): return True
    return False

def rgb(h):
    h = h.lstrip("#"); return "rgb(%d, %d, %d)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

async def pick(page, tok, hexv, done=True):
    """выбрать свой цвет через пикер: открыть лист, ввести HEX, «Готово» (или «Отмена»)"""
    await page.click('[data-act="colorOpen"][data-tok="%s"]' % tok); await page.wait_for_timeout(120)
    await page.fill("#cpHex", hexv); await page.wait_for_timeout(100)
    await page.click('#cpick .cp-btns [data-cp="%s"]' % ("done" if done else "cancel")); await page.wait_for_timeout(120)

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            seed(dump)
            page, errs = await open_tg(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.click('button[data-tab="set"]'); await page.click('[data-act="themeOpen"]'); await page.wait_for_timeout(250)
            GEO = """(id)=>{ const g=document.getElementById(id); const cs=getComputedStyle(g); const items=[...g.querySelectorAll('.swatch')].map(b=>b.getBoundingClientRect());
                const tops=[...new Set(items.map(r=>Math.round(r.top)))]; return {display:cs.display, cols:cs.gridTemplateColumns.split(' ').length, gap:cs.columnGap+'/'+cs.rowGap, n:items.length, rows:tops.length, w:items[0].width, h:items[0].height, caps:g.querySelectorAll('.sw-cap').length,
                    overlap:items.some((a,i)=>items.some((b,j)=>j>i&&Math.abs(a.top-b.top)<2&&a.right>b.left+0.5&&a.left<b.left)), right:Math.max(...items.map(r=>r.right)), card:g.parentElement.getBoundingClientRect().right}; }"""
            for gid, n, rows, name in [("swBase", 6, 1, "Основа"), ("swAccent", 12, 2, "Акцент"), ("swAccent2", 12, 2, "Дополнительный цвет"), ("swRest", 12, 2, "Неделя отдыха")]:
                g = await page.evaluate("(%s)('%s')" % (GEO, gid))
                check("3.1: «%s»: grid на 6 колонок, gap 0.75rem (12px), %d образцов = %d ряд(а), кружки ≤ 2.75rem (44px), подписей под кружками нет" % (name, n, rows),
                      g["display"] == "grid" and g["cols"] == 6 and g["gap"] == "12px/12px" and g["n"] == n and g["rows"] == rows and abs(g["w"] - g["h"]) < 0.5 and g["w"] <= 44.5 and g["caps"] == 0 and not g["overlap"] and g["right"] <= g["card"] + 0.5, g)
            g = await page.evaluate("(%s)('swAccent')" % GEO)
            check("3.1: на iPhone 13 (390px) кружки ровно 2.75rem (44px)", abs(g["w"] - 44) < 0.6, g["w"])
            cap = await page.evaluate("[...document.querySelectorAll('.sw-picked')].map(e=>e.textContent)")
            check("3.1: под каждой сеткой одна строка «Выбрано: …» (Как в Telegram / Оранжевый / как акцент / Зелёный)", cap == ["Выбрано: Как в Telegram", "Выбрано: Оранжевый", "Выбрано: как акцент", "Выбрано: Зелёный"], cap)
            sel = await page.evaluate("(()=>{ const b=document.querySelector('#swAccent .swatch.sel'); const cs=getComputedStyle(b); return {w:cs.outlineWidth, st:cs.outlineStyle, off:cs.outlineOffset, col:cs.outlineColor, text:getComputedStyle(document.documentElement).getPropertyValue('--text')}; })()")
            tcol = await page.evaluate("(()=>{const p=document.createElement('span'); p.style.color='var(--text)'; document.body.appendChild(p); const c=getComputedStyle(p).color; p.remove(); return c;})()")
            check("3.1: выбранный образец — обводка 2px --text с отступом 2px", sel["w"] == "2px" and sel["st"] == "solid" and sel["off"] == "2px" and sel["col"] == tcol, (sel, tcol))

            # 3.2 иконки «свой цвет»
            un = await page.evaluate("(()=>{ const l=document.querySelector('.swatch.custom[data-custom=accent]'); const cs=getComputedStyle(l); return {bs:cs.borderStyle, bc:cs.borderColor, plus:!!l.querySelector('svg.icon line'), pencil:!!l.querySelector('.sw-edit'), bg:cs.backgroundColor, set:l.classList.contains('set')}; })()")
            check("3.2: «Свой цвет» не задан — кружок с пунктирной обводкой и «+» по центру, без радуги", un["bs"] == "dashed" and un["plus"] and not un["pencil"] and not un["set"] and "conic" not in un["bg"], un)
            # задаём свой акцент
            await pick(page, 'accent', '#3a7bd5'); await page.wait_for_timeout(300)
            st = await page.evaluate("""(()=>{ const l=document.querySelector('.swatch.custom[data-custom=accent]'); const cs=getComputedStyle(l); const e=l.querySelector('.sw-edit'); const er=e.getBoundingClientRect(), lr=l.getBoundingClientRect();
                return {bg:cs.backgroundColor, w:er.width, h:er.height, r:lr.right-er.right, b:lr.bottom-er.bottom, ebg:getComputedStyle(e).backgroundColor, ecol:getComputedStyle(e).color, plus:!!l.querySelector(':scope > svg.icon'), cap:document.querySelectorAll('.sw-picked')[1].textContent, reset:!!l.closest('.cs-row').querySelector('.cs-reset')}; })()""")
            surf = await page.evaluate("(()=>{const p=document.createElement('span'); p.style.color='var(--surface)'; document.body.appendChild(p); const c=getComputedStyle(p).color; p.remove(); return c;})()")
            check("3.2: «Свой цвет» задан — кружок залит выбранным цветом, внизу справа значок-карандаш (кружок 1rem, фон --surface, иконка --text), плюса нет", st["bg"] == rgb("#3a7bd5") and abs(st["w"] - 16) < 0.6 and abs(st["h"] - 16) < 0.6 and st["ebg"] == surf and st["ecol"] == tcol and not st["plus"] and st["b"] < 6 and st["r"] < 6, st)
            check("3.1: подпись при своём цвете: «Выбрано: свой #3A7BD5»; у строки появилось «Сбросить»", st["cap"] == "Выбрано: свой #3A7BD5" and st["reset"], st["cap"])
            await page.click('[data-act="themeCustomReset"][data-tok="accent"]'); await page.wait_for_timeout(200)
            check("3.2: «Сбросить» возвращает оранжевый, значок снова «+»", await page.evaluate("data.cfg.theme.accent") == "#ff9f0a" and await page.evaluate("!!document.querySelector('.swatch.custom[data-custom=accent] svg.icon line') && !document.querySelector('.swatch.custom[data-custom=accent].set')"))

            # 3.3 основа
            tg = await page.evaluate("(()=>{ const b=document.querySelector('#swBase [data-v=tg]'); return {icon:!!b.querySelector('svg.icon'), title:b.title}; })()")
            check("3.3: образец «Как в Telegram» — кружок с иконкой самолётика", tg["icon"] and tg["title"] == "Как в Telegram", tg)
            rows = await page.evaluate("""(()=>{ const sec=document.getElementById('themeSections'); const card=document.getElementById('swBase').parentElement; const crr=card.getBoundingClientRect();
                return {title:[...card.querySelectorAll('.sec-sub')].map(e=>e.textContent), rows:[...card.querySelectorAll('.cs-row')].map(r=>{ const rr=r.getBoundingClientRect(), nm=r.querySelector('.cs-name').getBoundingClientRect(), sw=r.querySelector('.swatch').getBoundingClientRect();
                    return {name:r.querySelector('.cs-name').textContent, full:Math.abs(rr.width-(crr.width-32))<4||rr.width>crr.width-40, swRight:sw.left>nm.right-1&&Math.abs(rr.right-sw.right-0)<24, h:rr.height, reset:!!r.querySelector('.cs-reset')}; }), baseTop:document.getElementById('swBase').getBoundingClientRect().top}; })()""")
            check("3.3: под сеткой подблок «Свои цвета основы»: три строки на всю ширину — «Фон», «Карточки», «Текст», название слева, образец справа, высота ≥ 44", rows["title"] == ["Свои цвета основы"] and [r["name"] for r in rows["rows"]] == ["Фон", "Карточки", "Текст"] and all(r["full"] and r["swRight"] and r["h"] >= 44 and not r["reset"] for r in rows["rows"]), rows)
            await pick(page, 'bg', '#202020'); await page.wait_for_timeout(300)
            r2 = await page.evaluate("({resets:[...document.querySelectorAll('#swBase')[0].parentElement.querySelectorAll('.cs-reset')].length, base:data.cfg.theme.base, cap:document.getElementById('swBaseName').textContent, from:data.cfg.theme.custom.from, sel:document.querySelectorAll('#swBase .swatch.sel').length})")
            check("3.3: задан свой цвет → основа «свои цвета», у строк есть «Сбросить», в сетке основ нет выбранной", r2["base"] == "custom" and r2["resets"] == 3 and r2["cap"] == "Выбрано: свои цвета" and r2["sel"] == 0, r2)
            await page.click('[data-act="themeCustomReset"][data-tok="bg"]'); await page.wait_for_timeout(250)
            r3 = await page.evaluate("({base:data.cfg.theme.base, custom:data.cfg.theme.custom, cap:document.getElementById('swBaseName').textContent})")
            check("3.3: «Сбросить» снимает свои цвета основы и возвращает прежнюю готовую основу", r3["base"] == "tg" and r3["custom"] == {} and r3["cap"] == "Выбрано: Как в Telegram", r3)

            # 3.4 цвет недели отдыха
            check("3.4: токен --rest: по умолчанию зелёный #30d158", await page.evaluate("JSON.stringify(resolveColor('--rest'))") == '{"r":48,"g":209,"b":88}')
            await page.evaluate("ui.themeScreen=false; ui.tab='day'; render(); 0")
            def col(sel_, prop): return "getComputedStyle(document.querySelector('%s')).%s" % (sel_, prop)
            await page.evaluate("data.cfg.theme.accent2='#ff453a'; applyTheme(); 0")
            cl = await page.evaluate("({seg:getComputedStyle(document.querySelector('.strip .s-rest')).backgroundImage, acc2:getComputedStyle(document.documentElement).getPropertyValue('--accent-2').trim(), rest:getComputedStyle(document.documentElement).getPropertyValue('--rest').trim()})")
            check("3.4: --accent-2 (красный) больше не красит недели отдыха: полоса цикла по-прежнему зелёная, --rest остаётся #30d158", cl["acc2"] == "#ff453a" and cl["rest"] == "#30d158" and has(cl["seg"], 48, 209, 88) and not has(cl["seg"], 255, 69, 58), cl)
            await page.evaluate("data.cfg.theme.accent2=null; data.cfg.theme.rest='#ff6fae'; applyTheme(); 0")
            # места использования
            await page.evaluate("ui.tab='cal'; render(); 0")
            calc = await page.evaluate("(()=>{ const d=document.querySelector('.cal-day.rest:not(.today):not(.sel)'); return d?{bg:getComputedStyle(d).backgroundColor, bc:getComputedStyle(d).borderColor}:null; })()")
            check("3.4: недели отдыха в календаре красятся --rest (розовый)", calc and has(calc["bg"], 255, 111, 174) and has(calc["bc"], 255, 111, 174), calc)
            await page.evaluate("ui.tab='day'; curDate=toKey(new Date()); render(); 0")
            chk = await page.evaluate("""(()=>{ const out={}; const wi=weekInfo(curDate); const badge=document.querySelector('.badge.b-rest'); out.badge=badge?getComputedStyle(badge).color:'(рабочая неделя)';
                const seg=getComputedStyle(document.querySelector('.strip .s-rest')).backgroundImage; out.seg=seg; return out; })()""")
            check("3.4: полоса цикла красится --rest", has(chk["seg"], 255, 111, 174), chk)
            await page.evaluate("""(()=>{ const k=addDays(getMondayKey(toKey(new Date())),-6); const ex=newEx('Жим','3х8-12',null); ex.sets=[{w:50,r:10}]; data.log[k]={title:'Т',exercises:[ex],weekType:'rest',up:1}; const ex2=newEx('Жим','3х8-12',null); commitDay(toKey(new Date()),{title:'Т2',exercises:[ex2]}); ui.tab='day'; render(); 0 })()""")
            await page.wait_for_timeout(200)
            er = await page.evaluate("(()=>{ const e=document.querySelector('.ex-last.ex-rest'); return e?{c:getComputedStyle(e).color,t:e.textContent}:null; })()")
            check("3.4: строка «Отдых 16.09: …» в карточке красится --rest", er and has(er["c"], 255, 111, 174) and er["t"].startswith("Отдых"), er)
            await page.evaluate("ui.tab='prg'; ui.progMode='summary'; render(); 0")
            leg = await page.evaluate("[...document.querySelectorAll('.cal-legend i')].map(i=>getComputedStyle(i).backgroundColor)")
            check("3.4: легенда и точки недель отдыха на графике — --rest", any(has(x, 255, 111, 174) for x in leg), leg)

            # раздел и превью
            await page.evaluate("data.cfg.theme.rest='#30d158'; applyTheme(); ui.tab='set'; ui.themeScreen=true; render(); 0"); await page.wait_for_timeout(200)
            secs = await page.evaluate("[...document.querySelectorAll('#themeSections .sec-label')].map(e=>e.textContent)")
            check("3.4: разделы экрана: Основа, Акцент, Дополнительный цвет, Неделя отдыха", secs == ["Основа", "Акцент", "Дополнительный цвет", "Неделя отдыха"], secs)
            desc = await page.evaluate("[...document.querySelectorAll('#themeSections .card')][2].querySelector('.note').textContent")
            check("3.4: описание «Дополнительного цвета» — «Бейдж рекомендации и обводка следующего подхода»", desc.startswith("Бейдж рекомендации и обводка следующего подхода"), desc)
            await page.click('#swRest [data-v="#ff453a"]'); await page.wait_for_timeout(300)
            rr = await page.evaluate("({rest:data.cfg.theme.rest, stored:document.documentElement.style.getPropertyValue('--rest'), seg:getComputedStyle(document.querySelector('#themePreview .s-rest')).backgroundImage, cap:document.querySelectorAll('.sw-picked')[3].textContent})")
            check("3.4: выбор красного в «Неделе отдыха» — cfg.theme.rest, --rest на :root, мини-полоса превью перекрасилась, подпись «Выбрано: Красный»", rr["rest"] == "#ff453a" and rr["stored"] == "#ff453a" and has(rr["seg"], 255, 69, 58) and rr["cap"] == "Выбрано: Красный", rr)
            strip = await page.evaluate("[...document.querySelectorAll('#themePreview .strip i')].map(i=>i.className)")
            check("3.4: в превью темы мини-полоса цикла: 3 рабочих сегмента + 1 отдыха", strip == ["s-work", "s-work", "s-work", "s-rest"], strip)
            check("3.4: cfg.theme.rest сохранён в облаке", '"rest":"#ff453a"' in STORE["tst_cfg"])
            # миграция
            mg = await page.evaluate("[normTheme({base:'tg',accent:'#ff9f0a',accent2:'#ff453a',custom:{}}).rest, normTheme({base:'tg',accent:'#ff9f0a',rest:'#ABCDEF'}).rest, normTheme({rest:'мусор'}).rest, normTheme('dark','#34d399').rest, normalizeData({cfg:{theme:{base:'tg',accent:'#ff9f0a',accent2:'#ff453a'}},templates:[],log:{}}).cfg.theme.rest]")
            check("3.4: миграция: явный accent2 не наследуется — rest по умолчанию #30d158; валидный rest сохраняется; мусор → по умолчанию", mg == ["#30d158", "#abcdef", "#30d158", "#30d158", "#30d158"], mg)
            # сброс темы возвращает rest
            await page.click('[data-act="themeResetAsk"]'); await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(500)
            check("3.4: «Сбросить к стандартной» возвращает и цвет недели отдыха", await page.evaluate("data.cfg.theme.rest") == "#30d158")

            # 320px / 130%
            for w, fs in [(320, 1), (320, 1.3), (390, 1.3)]:
                await page.set_viewport_size({"width": w, "height": 800})
                await page.evaluate("data.cfg.fontScale=%s; applyFontScale(); ui.tab='set'; ui.themeScreen=true; render(); 0" % fs); await page.wait_for_timeout(250)
                ov = await page.evaluate("""(()=>{ const W=innerWidth; const bad=[...document.querySelectorAll('#app *')].filter(e=>e.getBoundingClientRect().right>W+1&&getComputedStyle(e).position!=='fixed').length; const s=[...document.querySelectorAll('#swAccent .swatch')].map(b=>b.getBoundingClientRect()); const rows=new Set(s.map(r=>Math.round(r.top))).size;
                    return {bad, scroll:document.documentElement.scrollWidth<=W, w:s[0].width, rows, overlap:s.some((a,i)=>s.some((b,j)=>j>i&&Math.abs(a.top-b.top)<2&&a.right>b.left+0.5))}; })()""")
                check("3: %dpx, шрифт %d%%: нет горизонтальной прокрутки, 12 цветов = 2 ряда, кружки не перекрываются (диаметр %.0fpx)" % (w, fs * 100, ov["w"]), ov["scroll"] and ov["bad"] == 0 and ov["rows"] == 2 and not ov["overlap"], ov)
            check("нет pageerror", not errs, errs[:2])
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_p13_t3.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
