"""Фаза 12, задача 1: длинное название варианта в кнопке. На реальном дампе."""
import asyncio, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
LONG = "Прямая изогнутая рукоять узкая"   # 30 символов

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
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.evaluate("curDate='2026-10-07'; ui.tab='day'; delete data.log[curDate]; delete ui.drafts[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); 0")
            ex_id = await page.evaluate("getDay().exercises.find(e=>e.base.startsWith('Молотки')).id")
            async def measure(width):
                await page.set_viewport_size({"width": width, "height": 900}); await page.wait_for_timeout(150)
                return await page.evaluate("""(id)=>{ const btn=document.querySelector('[data-act=variantToggle][data-id="'+id+'"]'), t=btn.querySelector('.vtxt'), row=btn.closest('.addset-extras');
                    const br=btn.getBoundingClientRect(), tr=t.getBoundingClientRect(), lh=parseFloat(getComputedStyle(t).lineHeight);
                    return {btnW:br.width, btnH:br.height, rowH:row.getBoundingClientRect().height, inside:tr.left>=br.left-0.5&&tr.right<=br.right+0.5&&tr.top>=br.top-0.5&&tr.bottom<=br.bottom+0.5,
                            lines:Math.round(tr.height/lh), clamp:getComputedStyle(t).webkitLineClamp, sm:t.classList.contains('sm'), fs:getComputedStyle(t).fontSize, scrollOk:btn.scrollWidth<=btn.clientWidth+1,
                            cols:getComputedStyle(row).gridTemplateColumns.split(' ').length, pageScroll:document.documentElement.scrollWidth<=innerWidth}; }""", ex_id)
            short = await measure(390)
            await page.evaluate("doAction('applyVariant',{id:'%s',variant:'%s'}); 0" % (ex_id, LONG)); await page.wait_for_timeout(200)
            long390 = await measure(390)
            long320 = await measure(320)
            check("1: вариант из 30 символов на 320px не вылезает за кнопку, не шире экрана", long320["inside"] and long320["scrollOk"] and long320["pageScroll"], long320)
            check("1: текст не больше двух строк (line-clamp: 2)", long320["lines"] <= 2 and long320["clamp"] == "2" and long390["lines"] <= 2, (long320["lines"], long320["clamp"]))
            check("1: если не помещается в одну строку — кегль на шаг меньше (12.5px против 14px)", long320["sm"] and long320["fs"] == "12.5px" and short["fs"] == "14px" and not short["sm"], (long320["fs"], short["fs"]))
            check("1: высота ряда не меняется от длины названия (кнопка 52px ≥ 44px, ряд одинаков)", long320["btnH"] == short["btnH"] == 52 and long320["rowH"] == short["rowH"] and long320["btnH"] >= 44, (short["btnH"], long320["btnH"], short["rowH"], long320["rowH"]))
            check("1: нижний ряд — сетка по числу кнопок (3 колонки)", long320["cols"] == 3 and short["cols"] == 3)
            # полное название
            await page.set_viewport_size({"width": 390, "height": 900})
            await page.click('[data-act="variantToggle"][data-id="%s"]' % ex_id); await page.wait_for_timeout(150)
            names = await page.evaluate("[...document.querySelectorAll('.variant-list .prog-ex-btn')].map(b=>b.textContent.trim())")
            check("1: в списке выбора варианта есть пункт «— без варианта» и полные названия без обрезки", "— без варианта" in names and await page.evaluate("[...document.querySelectorAll('.variant-list .prog-ex-btn')].every(b=>b.scrollWidth<=b.clientWidth+1)"), names)
            await page.evaluate("ui.variantOpen={}; render(); 0")
            # «Рабочая …: вариант» над подходами — полное название: запись прошлого дня с длинным вариантом
            await page.evaluate("""(()=>{ const d=data.log['2026-09-23']; const e=d.exercises.find(x=>x.base.startsWith('Молотки')); e.variant=%s; e.name=composeName(e.base,e.plan,e.variant); curDate='2026-10-07'; render(); 0 })()""" % json.dumps(LONG))
            last = await page.evaluate("[...document.querySelectorAll('.card')].filter(c=>c.querySelector('.ex-name')&&c.querySelector('.ex-name').textContent.startsWith('Молотки'))[0].textContent")
            check("1: полное название варианта видно в строке «Рабочая …: вариант» над подходами", LONG in last, last[:160])
            await page.evaluate("""(()=>{ const d=data.log['2026-09-23']; const e=d.exercises.find(x=>x.base.startsWith('Молотки')); 0 })()""")
            check("нет pageerror", not errs, errs[:2])
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_p12t1.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
