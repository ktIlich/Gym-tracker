"""Фаза 13, задача 5: экран «Проверка данных» — строки-сетки в две строки текста, шеврон 44×44."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            seed(dump)
            page, errs = await open_tg(browser)
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            # добавим замечания каждого вида, включая длинное название и план в скобках
            await page.evaluate("""(()=>{ const k1='2026-07-13', k2='2026-07-14', k3='2026-07-15'; const c2=newEx('Тяга','3х8-12',null); c2.sets=[{w:40,r:10}];
                const a=newEx('Жим Смит / гантели на плечи','2х8-12',null); a.sets=[{w:30,r:10},{w:30,r:10},{w:30,r:10}];
                const b=newEx('Жим Смит / гантели на плечи','3х8-12','Блок'); b.sets=[];
                data.log[k1]={title:'Плечи',exercises:[a],weekType:'work',up:1}; const c=newEx('Тяга','3х8-12',null); c.sets=[{w:40,r:10}]; data.log[k2]={title:'',exercises:[c,b],weekType:'work',up:1}; data.log[k3]={title:'Длинное название тренировки для проверки переноса строк в списке',exercises:[c2,newEx('Очень длинное название упражнения для проверки переноса строк в списке замечаний','3х8-12',null)],weekType:'work',up:1};
                ui.tab='set'; ui.hygiene='check'; render(); })()"""); await page.wait_for_timeout(250)
            rows = await page.evaluate("""(()=>{ return [...document.querySelectorAll('.chk-row')].map(r=>{ const cs=getComputedStyle(r), rr=r.getBoundingClientRect(), go=r.querySelector('.chk-go').getBoundingClientRect(), txt=r.querySelector('.chk-txt').getBoundingClientRect();
                return {tag:r.tagName, act:r.dataset.act, cols:cs.gridTemplateColumns.split(' ').length, display:cs.display, gap:cs.columnGap, ai:cs.alignItems, l1:r.querySelector('.chk-l1').textContent, l2:r.querySelector('.chk-l2').textContent, l2color:getComputedStyle(r.querySelector('.chk-l2')).color, goW:go.width, goH:go.height,
                    bt:cs.borderTopStyle, bw:cs.borderTopWidth, h:rr.height, btn:!!r.querySelector('button'), right:rr.right, tr:txt.right, goL:go.left, l1lines:Math.round(r.querySelector('.chk-l1').getBoundingClientRect().height/parseFloat(getComputedStyle(r.querySelector('.chk-l1')).lineHeight)), l2lines:Math.round(r.querySelector('.chk-l2').getBoundingClientRect().height/parseFloat(getComputedStyle(r.querySelector('.chk-l2')).lineHeight))}; }); })()""")
            check("5: экран показывает замечания строками (.chk-row), нажимается вся строка (data-act=hygOpenDay), вложенных кнопок нет", len(rows) >= 4 and all(r["tag"] == "BUTTON" and r["act"] == "hygOpenDay" and not r["btn"] for r in rows), len(rows))
            check("5: строка — grid 1fr auto, align-items:center, gap 0.75rem (12px)", all(r["display"] == "grid" and r["cols"] == 2 and r["gap"] == "12px" and r["ai"] == "center" for r in rows), rows[0])
            by = {r["l1"]: r for r in rows}
            a = next(r for r in rows if r["l1"].startswith("13.07"))
            check("5: первая строка — «13.07 · Жим Смит / гантели на плечи» (без плана в скобках), вторая — «подходов 3, в плане 2»", a["l1"] == "13.07 · Жим Смит / гантели на плечи" and a["l2"] == "подходов 3, в плане 2", (a["l1"], a["l2"]))
            bb = next(r for r in rows if r["l1"].startswith("14.07"))
            check("5: вариант показывается, план нет: «14.07 · Жим Смит / гантели на плечи · Блок» / «без подходов»", bb["l1"] == "14.07 · Жим Смит / гантели на плечи · Блок" and bb["l2"] == "без подходов" and "(" not in bb["l1"], (bb["l1"], bb["l2"]))
            dates = await page.evaluate("[...document.querySelectorAll('.chk-l1 b')].map(b=>[b.textContent, getComputedStyle(b).fontWeight])")
            check("5: дата полужирная", all(int(w) >= 700 for _, w in dates), dates[:2])
            mutedc = await page.evaluate("(()=>{const p=document.createElement('span'); p.style.color='var(--text-muted)'; document.body.appendChild(p); const c=getComputedStyle(p).color; p.remove(); return c;})()")
            check("5: вторая строка — приглушённым цветом (--text-muted)", all(r["l2color"] == mutedc for r in rows), (rows[0]["l2color"], mutedc))
            check("5: справа иконка-шеврон 44×44, прижата к правому краю строки", all(abs(r["goW"] - 44) < 0.6 and abs(r["goH"] - 44) < 0.6 and r["right"] - r["goL"] - 44 < 2 for r in rows), [(r["goW"], r["goH"]) for r in rows[:2]])
            check("5: между строками разделитель --border (у первой в карточке нет), высота ≥ 44", all(r["h"] >= 44 for r in rows) and sum(1 for r in rows if r["bt"] == "solid") >= len(rows) - 4, [(r["bt"], r["h"]) for r in rows[:4]])
            # высота не прыгает: у строк без переноса одинаковая высота
            hs = sorted({round(r["h"] - float(r["bw"][:-2]) * (r["bt"] == "solid")) for r in rows if r["l1lines"] == 1 and r["l2lines"] == 1})
            check("5: строки с короткими названиями — одной высоты (кнопка не переносится на две строки)", len(hs) == 1, hs)
            bad_words = await page.evaluate("[...document.querySelectorAll('.chk-go')].every(g=>g.textContent.trim()==='' && !!g.querySelector('svg.icon'))")
            check("5: вместо слов «К дню» — SVG-шеврон «›»", bad_words)
            # тап по любой части строки
            tg = await page.evaluate("(()=>{ const r=document.querySelector('.chk-row[data-date=\"2026-07-13\"] .chk-l2').getBoundingClientRect(); return [r.left+5, r.top+5]; })()")
            await page.mouse.click(tg[0], tg[1]); await page.wait_for_timeout(300)
            check("5: тап по тексту строки открывает день 13.07 на «Сегодня»", await page.evaluate("curDate==='2026-07-13' && ui.tab==='day' && !ui.hygiene"))
            await page.evaluate("ui.tab='set'; ui.hygiene='check'; render(); 0"); await page.wait_for_timeout(200)
            await page.click('.chk-row[data-date="2026-07-14"] .chk-go'); await page.wait_for_timeout(300)
            check("5: тап по шевpону открывает день 14.07", await page.evaluate("curDate==='2026-07-14' && ui.tab==='day'"))
            # 320 px / 130 %: длинные названия переносятся, ничего не вылезает
            await page.evaluate("ui.tab='set'; ui.hygiene='check'; render(); 0")
            for w, fs in [(320, 1), (320, 1.3), (390, 1.3)]:
                await page.set_viewport_size({"width": w, "height": 800})
                await page.evaluate("data.cfg.fontScale=%s; applyFontScale(); render(); 0" % fs); await page.wait_for_timeout(200)
                g = await page.evaluate("""(()=>{ const W=innerWidth; const rs=[...document.querySelectorAll('.chk-row')]; const bad=rs.filter(r=>r.getBoundingClientRect().right>W+1||r.scrollWidth>r.clientWidth+1).length;
                    const goX=rs.map(r=>Math.round(r.querySelector('.chk-go').getBoundingClientRect().left)); const long=rs.find(r=>r.textContent.includes('Очень длинное')); return {bad, scroll:document.documentElement.scrollWidth<=W, goAligned:new Set(goX).size===1, longLines:Math.round(long.querySelector('.chk-l1').getBoundingClientRect().height/parseFloat(getComputedStyle(long.querySelector('.chk-l1')).lineHeight)), goH:Math.min(...rs.map(r=>r.querySelector('.chk-go').getBoundingClientRect().height))}; })()""")
                check("5: %dpx, шрифт %d%%: строки в экране, шевроны выровнены в колонку, длинное название переносится (строк: %d), шеврон ≥ 44px" % (w, fs * 100, g["longLines"]), g["bad"] == 0 and g["scroll"] and g["goAligned"] and g["longLines"] >= 2 and g["goH"] >= 43.5, g)
            check("нет pageerror", not errs, errs[:2])
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_p13_t5.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
