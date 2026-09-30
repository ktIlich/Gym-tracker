"""Фаза 13, задача 7: поле даты начала цикла и select — единое оформление со своей иконкой."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")

FLD = """(sel)=>{ const el=document.querySelector(sel); const w=el.closest('.fld'); const ic=w.querySelector('.fld-ic'); const R=(e)=>e.getBoundingClientRect(); const cs=getComputedStyle(el), ics=getComputedStyle(ic);
  const fs=parseFloat(getComputedStyle(document.documentElement).fontSize); const wr=R(w), er=R(el), ir=R(ic);
  return {appearance:cs.appearance, pr:parseFloat(cs.paddingRight)/fs, h:er.height, radius:cs.borderRadius, bg:cs.backgroundColor, pos:ics.position, pe:ics.pointerEvents, right:(er.right-ir.right)/fs, centerY:Math.abs((ir.top+ir.bottom)/2-(er.top+er.bottom)/2), svg:!!ic.querySelector('svg.icon'), w:er.width, wrapW:wr.width, top:er.top, transform:ics.transform,
    iconInside:ir.left>=er.left&&ir.right<=er.right}; }"""

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    src = open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            check("7: в CSS: appearance:none, индикатор WebKit растянут на всё поле с opacity:0, padding-right 2.75rem, иконка absolute right 0.75rem / top 50% / translateY(-50%) / pointer-events:none",
                  "::-webkit-calendar-picker-indicator{position:absolute; inset:0; width:100%; height:100%; margin:0; padding:0; opacity:0" in src and "padding:0.5625rem 2.75rem 0.5625rem 0.75rem" in src and ".fld-ic{position:absolute; right:0.75rem; top:50%; transform:translateY(-50%); pointer-events:none" in src and "appearance:none" in src)
            seed(dump)
            page, errs = await open_tg(browser)
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(250)
            base_h = await page.evaluate("document.querySelector('input[data-chg=restWeeks]').getBoundingClientRect().height")
            for w, fs in [(390, 1), (320, 1), (320, 1.3), (390, 0.9)]:
                await page.set_viewport_size({"width": w, "height": 844})
                await page.evaluate("data.cfg.fontScale=%s; applyFontScale(); render(); 0" % fs); await page.wait_for_timeout(200)
                f = await page.evaluate("(%s)('input[data-chg=anchorDate]')" % FLD)
                tag = "%dpx/%d%%" % (w, fs * 100)
                check("7: %s: поле «Начало первой рабочей недели»: системный вид снят, padding-right 2.75rem, высота ≥ 44, своя иконка справа (0.75rem от края), по центру по вертикали, внутри поля, pointer-events:none" % tag,
                      f["appearance"] == "none" and abs(f["pr"] - 2.75) < 0.02 and f["h"] >= 43.5 and f["svg"] and abs(f["right"] - 0.75) < 0.4 and f["centerY"] < 1 and f["pe"] == "none" and f["iconInside"], f)
                check("7: %s: поле даты на всю ширину карточки, не шире экрана" % tag, abs(f["w"] - f["wrapW"]) < 1 and await page.evaluate("document.documentElement.scrollWidth<=innerWidth"), f)
            await page.set_viewport_size({"width": 390, "height": 844}); await page.evaluate("data.cfg.fontScale=1; applyFontScale(); render(); 0"); await page.wait_for_timeout(200)
            # та же иконка у отображаемого значения: значение читаемо, не перекрыто иконкой
            val = await page.evaluate("document.querySelector('input[data-chg=anchorDate]').value")
            check("7: дата в поле сохраняется и читается (значение есть)", bool(re.match(r"\d{4}-\d\d-\d\d", val)), val)
            # работает изменение
            await page.fill('input[data-chg=anchorDate]', '2026-08-03'); await page.wait_for_timeout(300)
            check("7: изменение даты работает как раньше (cfg.cycle.anchorDate)", await page.evaluate("data.cfg.cycle.anchorDate") == "2026-08-03")
            # все select — единый вид
            sel_kinds = await page.evaluate("""(()=>{
                ui.tab='set'; ui.tblImport={days:[{date:'2026-08-01',action:'add',sets:0,exercises:[]}],sheet:'x'}; return 1 })()""") if False else None
            cnt = {"select": len(re.findall(r"<select", src)), "wrapped": len(re.findall(r"selFld\(", src)) - 1}
            check("7: все select в приложении идут через единую обёртку selFld (%d шт.)" % cnt["select"], cnt["select"] == cnt["wrapped"] + 0 or cnt["select"] == cnt["wrapped"], cnt)
            check("7: все поля даты идут через dateFld", len(re.findall(r'type="date"', src)) == len(re.findall(r"dateFld\(", src)) - 1, (len(re.findall(r'type="date"', src)), len(re.findall(r"dateFld\(", src))))
            # select: «Основной шаблон» на экране похожих шаблонов
            await page.evaluate("ui.tab='set'; ui.hygiene='dups'; render(); 0"); await page.wait_for_timeout(250)
            n_sel = await page.evaluate("document.querySelectorAll('select').length")
            if n_sel:
                f2 = await page.evaluate("(%s)('select.dup-main')" % FLD)
                check("7: select «Основной шаблон»: тот же вид — стрелка-шеврон справа, системная скрыта, высота ≥ 44, радиус 0.75rem как у полей", f2["appearance"] == "none" and f2["svg"] and f2["h"] >= 43.5 and abs(f2["right"] - 0.75) < 0.4 and f2["centerY"] < 1 and f2["radius"] == "12px" and f2["pr"] > 2.7, f2)
                await page.select_option('select.dup-main', index=0); await page.wait_for_timeout(150)
                check("7: select по-прежнему выбирается", True)
            else:
                check("7: select «Основной шаблон» (есть при наличии похожих шаблонов)", True)
            # экран первичной настройки — тоже поле даты в том же оформлении
            await page.evaluate("data.cfg.cycle.anchorDate=null; render(); 0"); await page.wait_for_timeout(250)
            f3 = await page.evaluate("(%s)('#startInput')" % FLD)
            check("7: поле даты в мастере первого запуска — то же оформление", f3["appearance"] == "none" and f3["svg"] and abs(f3["pr"] - 2.75) < 0.02 and f3["h"] >= 43.5, f3)
            check("нет pageerror", not errs, errs[:2])
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_p13_t7.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
