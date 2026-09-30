"""Фаза 12, задача 2: режимы таймера отдыха. На реальном дампе."""
import asyncio, json, os, subprocess, sys, time
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
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            mig = await page.evaluate("""(()=>{ const n=(c)=>normalizeData({cfg:c,templates:[],log:{}}).cfg;
                return [n({autoTimer:true}).timerMode, n({autoTimer:false}).timerMode, n({}).timerMode, n({timerMode:'off',autoTimer:true}).timerMode, n({timerMode:'мусор',autoTimer:false}).timerMode, n({autoTimer:false}).autoTimer]; })()""")
            check("2: миграция cfg: autoTimer true → «auto», false → «manual» (кнопка остаётся), нет поля → «auto», существующий timerMode сохраняется, мусор → по autoTimer; autoTimer не удалён", mig == ["auto", "manual", "auto", "off", "manual", False], mig)
            check("2: в реальных данных (autoTimer=false) режим стал «manual»", await page.evaluate("data.cfg.timerMode") == "manual" and dump["cfg"]["autoTimer"] is False)
            check("2: autoTimer больше не читается (в коде нет чтения data.cfg.autoTimer)", "data.cfg.autoTimer)" not in open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read().replace("data.cfg.autoTimer=(m===", ""))

            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            seg = await page.evaluate("[...document.querySelectorAll('#timerSeg button')].map(b=>[b.textContent,b.classList.contains('on'),Math.round(b.getBoundingClientRect().height)])")
            check("2: настройки «Таймер отдыха»: сегментированный переключатель Выключен / Вручную / Автоматически (зоны ≥ 44px), выбран текущий", seg == [["Выключен", False, 52], ["Вручную", True, 52], ["Автоматически", False, 52]] or ([s[0] for s in seg] == ["Выключен", "Вручную", "Автоматически"] and seg[1][1] and all(s[2] >= 44 for s in seg)), seg)
            check("2: старого переключателя «Автозапуск таймера» нет", "Автозапуск таймера" not in await page.inner_text("#app"))
            check("2: длительность отдыха показана в режиме «Вручную»", await page.locator("#timerDur").is_visible())
            await page.evaluate("window.__renders=0; const R=window.render; window.render=function(){ window.__renders++; return R.apply(this,arguments); }; 0")
            await page.click('[data-act="timerMode"][data-mode="off"]'); await page.wait_for_timeout(400)
            check("2: режим «Выключен»: длительность скрыта, сохранено в cfg и в облаке, полный render() не вызывался",
                  not await page.locator("#timerDur").is_visible() and await page.evaluate("data.cfg.timerMode") == "off" and '"timerMode":"off"' in STORE["tst_cfg"] and await page.evaluate("window.__renders") == 0)
            check("2: autoTimer синхронизируется для совместимости (off → false)", await page.evaluate("data.cfg.autoTimer") is False)
            await page.click('[data-act="timerMode"][data-mode="auto"]'); await page.wait_for_timeout(300)
            check("2: режим «Автоматически»: длительность снова видна; подсказка под переключателем меняется", await page.locator("#timerDur").is_visible() and "стартует после записи подхода" in await page.inner_text("#timerSeg + .note") and await page.evaluate("data.cfg.autoTimer") is True)

            # день
            await page.evaluate("curDate='2026-10-07'; ui.tab='day'; data.cfg.restTimerSec=30; delete data.log[curDate]; delete ui.drafts[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); 0")
            async def row():
                return await page.evaluate("""(()=>{ const c=document.querySelector('.addset-extras'); const b=[...c.children].map(x=>x.dataset.act); const v=c.querySelector('.variant-btn').getBoundingClientRect().width;
                    return {acts:b, cols:getComputedStyle(c).gridTemplateColumns.split(' ').length, timer:document.querySelectorAll('.timer-btn').length, vw:v, h:c.getBoundingClientRect().height}; })()""")
            r_auto = await row()
            check("2: «Автоматически»: кнопка таймера в упражнении есть, ряд из 3 колонок", r_auto["timer"] > 0 and r_auto["cols"] == 3 and r_auto["acts"][0] == "timerToggle", r_auto)
            await page.evaluate("(()=>{ const id=getDay().exercises[0].id; ui.nextSet[id]={w:10,r:10}; updateNextDom(id); window.__id=id; 0 })()")
            await page.click('.check >> nth=0'); await page.wait_for_timeout(300)
            check("2: «Автоматически»: запись подхода запускает таймер", await page.evaluate("timerEnd>Date.now()"))
            await page.evaluate("stopTimer(); data.cfg.timerMode='manual'; render(); 0")
            r_man = await row()
            await page.click('.check >> nth=0'); await page.wait_for_timeout(300)
            check("2: «Вручную»: кнопка есть, подход таймер не запускает, кнопка запускает", r_man["timer"] > 0 and not await page.evaluate("timerEnd>Date.now()"))
            await page.locator('[data-act="timerToggle"]').first.click(); await page.wait_for_timeout(200)
            check("2: «Вручную»: тап по кнопке запускает отсчёт", await page.evaluate("timerEnd>Date.now()"))
            await page.click('button[data-tab="set"]'); await page.click('[data-act="timerMode"][data-mode="off"]'); await page.wait_for_timeout(200)
            check("2: если таймер шёл при переключении в «Выключен» — он остановлен", await page.evaluate("timerEnd===0") and await page.evaluate("timerInterval===null"))
            await page.click('button[data-tab="day"]'); await page.wait_for_timeout(200)
            r_off = await row()
            check("2: «Выключен»: кнопка таймера не рендерится, ряд перестроен (2 колонки), кнопка варианта шире", r_off["timer"] == 0 and r_off["cols"] == 2 and "timerToggle" not in r_off["acts"] and r_off["vw"] > r_auto["vw"] * 1.3, (r_off, r_auto["vw"]))
            check("2: «Выключен»: высота ряда не меняется (фиксированная)", r_off["h"] == r_auto["h"], (r_off["h"], r_auto["h"]))
            await page.click('.check >> nth=0'); await page.wait_for_timeout(200)
            check("2: «Выключен»: запись подхода таймер не запускает", not await page.evaluate("timerEnd>Date.now()"))
            check("нет pageerror", not errs, errs[:2])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
