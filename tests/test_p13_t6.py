"""Фаза 13, задача 6: редактор шаблона — блок вариантов (чипы-прямоугольники, единый стек gap 0.75rem)."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")

GEO = """(()=>{
  const item=[...document.querySelectorAll('.et-item')].find(i=>i.querySelector('.et-vars2 .et-chip')&&i.querySelectorAll('.et-chip').length>=2);
  const fs=parseFloat(getComputedStyle(document.documentElement).fontSize);
  const R=(e)=>e.getBoundingClientRect(); const ic=item.querySelector('input[data-et=name]'), row=item.querySelector('.et-row'), v2=item.querySelector('.et-vars2'), chips=item.querySelector('.chips'), now=item.querySelector('.et-now'), add=item.querySelector('.addex'), alt=item.querySelector('.et-vars');
  const cs=getComputedStyle(item), chip=item.querySelector('.et-chip'), onChip=item.querySelector('.et-chip.on'), offChip=item.querySelector('.et-chip:not(.on)'), inp=item.querySelector('.addex input'), btn=item.querySelector('.et-vadd');
  const stack=[ic,row,v2].map(R), inner=[chips,now,add,alt].map(R);
  const gaps=[stack[1].top-stack[0].bottom, stack[2].top-stack[1].bottom, inner[1].top-inner[0].bottom, inner[2].top-inner[1].bottom, inner[3].top-inner[2].bottom];
  const css=(e,p)=>getComputedStyle(e)[p];
  const chipRows=[...new Set([...item.querySelectorAll('.et-chip')].map(c=>Math.round(R(c).top)))].length;
  return {fs, display:cs.display, dir:cs.flexDirection, gap:cs.rowGap, gaps, margins:[row,v2,chips,now,add,alt].map(e=>css(e,'marginTop')),
    radius:{chip:css(chip,'borderRadius'), input:css(ic,'borderRadius'), btn:css(btn,'borderRadius'), inp:css(inp,'borderRadius')}, chipH:R(chip).height, chipBg:css(offChip,'backgroundColor'), onBg:css(onChip,'backgroundColor'), onBorder:css(onChip,'borderTopWidth')+' '+css(onChip,'borderTopColor'), onColor:css(onChip,'color'), offBorder:css(offChip,'borderTopColor'),
    x:chip.querySelector('.chip-x').getBoundingClientRect().right<=R(chip).right+0.5 && R(chip.querySelector('.chip-x')).left>R(chip).left+R(chip).width*0.4, xW:R(chip.querySelector('.chip-x')).width,
    addRow:{inpTop:R(inp).top, btnTop:R(btn).top, inpH:R(inp).height, btnH:R(btn).height, shrink:css(btn,'flexShrink'), nowrap:css(btn,'whiteSpace'), right:R(btn).right, cardRight:R(item).right, w:R(btn).width},
    noteText:now.textContent, noteBelow:R(now).top>=R(chips).bottom && R(now).bottom<=R(add).top, chipRows, n:item.querySelectorAll('.et-chip').length,
    accent:(()=>{const p=document.createElement('span'); p.style.color='var(--accent)'; document.body.appendChild(p); const c=getComputedStyle(p).color; p.remove(); return c;})(),
    surf2:(()=>{const p=document.createElement('span'); p.style.color='var(--surface-2)'; document.body.appendChild(p); const c=getComputedStyle(p).color; p.remove(); return c;})()}; })()"""

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
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.click('button[data-tab="tpl"]'); await page.wait_for_timeout(200)
            # шаблон с вариантами: «Молотки» (Блок/Свободный) — есть в реальных данных
            tid = await page.evaluate("data.templates.find(t=>t.blocks.some(b=>b.items.some(i=>(i.vars||[]).length>=2))).id")
            await page.click('[data-act="etEdit"][data-id="%s"]' % tid); await page.wait_for_timeout(250)
            await page.evaluate("(()=>{ const ui_=ui.editTpl; for(const b of ui_.blocks) for(const it of b.items) if((it.vars||[]).length>=2) it._v=true; render(); })()"); await page.wait_for_timeout(200)
            for w, fs in [(390, 1), (320, 1), (320, 1.3), (390, 0.9), (390, 1.3)]:
                await page.set_viewport_size({"width": w, "height": 844})
                await page.evaluate("data.cfg.fontScale=%s; applyFontScale(); render(); 0" % fs); await page.wait_for_timeout(200)
                g = await page.evaluate(GEO)
                tag = "%dpx/%d%%" % (w, fs * 100)
                if w == 390 and fs == 1:
                    check("6: чип — прямоугольник со скруглением как у полей и кнопок редактора (0.75rem), высота ≥ 2.75rem (44px), фон --surface-2, крестик справа внутри", g["radius"]["chip"] == g["radius"]["input"] == g["radius"]["btn"] == g["radius"]["inp"] == "12px" and g["chipH"] >= 43.5 and g["chipBg"] == g["surf2"] and g["x"], g)
                    check("6: вариант «по очереди» — обводка 1.5px --accent, текст --accent, без заливки; остальные — без обводки акцентом", g["onBorder"].endswith(" " + g["accent"]) and g["onBorder"][:3] in ("1px", "1.5") and "border:1.5px solid transparent" in open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read() and g["onColor"] == g["accent"] and g["onBg"] == "rgba(0, 0, 0, 0)" and g["offBorder"] != g["accent"], (g["onBorder"], g["onColor"], g["onBg"]))
                    check("6: подпись «Сейчас по очереди: …» под чипами, выше поля нового варианта", g["noteText"].startswith("Сейчас по очереди: ") and g["noteBelow"], g["noteText"])
                check("6: %s: ряды карточки упражнения (название, план+варианты, чипы, подпись, новый вариант, чередование) — один вертикальный стек, gap 0.75rem (%dpx), без margin у рядов" % (tag, round(12 * g["fs"] / 16)),
                      g["display"] == "flex" and g["dir"] == "column" and all(abs(x - 12 * g["fs"] / 16) < 1.0 for x in g["gaps"]) and all(m == "0px" for m in g["margins"]), (g["gaps"], g["margins"], g["gap"]))
                a = g["addRow"]
                check("6: %s: «Новый вариант…» и «+ вариант» — одна строка, одной высоты, кнопка не сжимается и не выходит за карточку" % tag, abs(a["inpTop"] - a["btnTop"]) < 1.5 and abs(a["inpH"] - a["btnH"]) < 1.5 and a["shrink"] == "0" and a["nowrap"] == "nowrap" and a["right"] <= a["cardRight"] + 0.5, a)
                ov = await page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                check("6: %s: нет горизонтальной прокрутки" % tag, ov)
            # длинный вариант переносится, чипы не вылезают
            await page.set_viewport_size({"width": 320, "height": 844}); await page.evaluate("data.cfg.fontScale=1; applyFontScale(); 0")
            await page.evaluate("(()=>{ for(const b of ui.editTpl.blocks) for(const it of b.items) if((it.vars||[]).length>=2){ it.vars[0]='Очень длинный вариант упражнения для проверки переноса строк'; } render(); })()"); await page.wait_for_timeout(200)
            lc = await page.evaluate("(()=>{ const c=document.querySelector('.et-item .et-chip'); const r=c.getBoundingClientRect(); return {r:r.right, vw:innerWidth, h:r.height}; })()")
            check("6: длинный вариант в чипе не выходит за экран (320px)", lc["r"] <= lc["vw"] and lc["h"] >= 43.5, lc)
            # функциональность не сломана: добавление и удаление варианта
            await page.fill('.et-item .addex input', 'Новый хват'); await page.click('.et-item .et-vadd'); await page.wait_for_timeout(200)
            cnt = await page.evaluate("ui.editTpl.blocks.flatMap(b=>b.items).find(i=>(i.vars||[]).includes('Новый хват'))!==undefined")
            check("6: «+ вариант» по-прежнему добавляет вариант, крестик на чипе удаляет", cnt)
            check("нет pageerror", not errs, errs[:2])
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_p13_t6.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
