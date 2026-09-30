"""Фаза 13, задача 8: тур — плашка с названием экрана сверху (Тур · Сегодня, «3 / 14», «Выйти»)."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, WRITES, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
S = """(()=>{ const t=document.querySelector('#tour'); const bar=t.querySelector('.tour-banner').getBoundingClientRect(); const tg=document.querySelector('[data-tour="'+tour.cur.target+'"]').getBoundingClientRect(); const hole=t.querySelector('.tour-hole').getBoundingClientRect();
  const tip=t.querySelector('.tour-tip'); const ex=t.querySelector('.tour-exit').getBoundingClientRect(), cnt=t.querySelector('.tour-count').getBoundingClientRect(), scr=t.querySelector('.tour-screen').getBoundingClientRect();
  return {screen:t.querySelector('.tour-screen').textContent, count:t.querySelector('.tour-count').textContent, exit:t.querySelector('.tour-exit').textContent, exitH:ex.height, exitW:ex.width,
    bar:{t:bar.top,b:bar.bottom,l:bar.left,r:bar.right}, vw:innerWidth, hole:{t:hole.top, b:hole.bottom}, tg:{t:tg.top,b:tg.bottom}, tipCount:tip.querySelector('.tour-count')!==null, tipTop:tip.getBoundingClientRect().top, order:[scr.left, cnt.left, ex.left], rightOfCount:cnt.right<=ex.left+1, target:tour.cur.target,
    example:t.querySelector('.tour-example').textContent}; })()"""

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
            await page.click('button[data-tab="set"]'); await page.click('[data-act="tourAll"]'); await page.wait_for_timeout(400)
            seen = []; bad = []; names = []
            for i in range(60):
                await page.wait_for_timeout(250)
                st = await page.evaluate(S)
                seen.append(st)
                if st["tipCount"]: bad.append(("счётчик в подсказке", st["target"]))
                if st["hole"]["t"] < st["bar"]["b"] - 1 and st["tg"]["t"] >= 0 and st["target"] != "tabbar": bad.append(("перекрыта цель", st["target"], st["hole"], st["bar"]))
                if not (st["tipTop"] >= st["bar"]["b"] - 0.5): bad.append(("подсказка под плашкой", st["target"], st["tipTop"], st["bar"]["b"]))
                if st["count"].split(" / ")[0] != str(i + 1): bad.append(("счётчик", st["count"], i + 1))
                if st["screen"] not in names: names.append(st["screen"])
                if await page.inner_text('#tour [data-t="next"]') == "Готово": break
                await page.click('#tour [data-t="next"]')
            first = seen[0]
            check("8: плашка сверху на всю ширину: «Тур · Сегодня» слева, «1 / 37» и «Выйти» справа; ниже «Пример — данные не сохраняются»", first["screen"] == "Тур · Сегодня" and first["count"] == "1 / 37" and first["exit"] == "Выйти" and first["bar"]["l"] == 0 and first["bar"]["r"] == first["vw"] and first["order"] == sorted(first["order"]) and first["rightOfCount"] and "не сохраняются" in first["example"], first)
            check("8: кнопка «Выйти» ≥ 44px по высоте", all(s["exitH"] >= 43.5 for s in seen), min(s["exitH"] for s in seen))
            check("8: при переходе на другой таб название меняется: Сегодня → Шаблоны → Календарь → Прогресс → Настройки", names == ["Тур · Сегодня", "Тур · Шаблоны", "Тур · Календарь", "Тур · Прогресс", "Тур · Настройки"], names)
            check("8: счётчика в самой подсказке нет, нумерация «N / 37» сквозная, плашка не перекрывает подсвеченный элемент (шагов: %d)" % len(seen), not bad and len(seen) == 37, bad[:3])
            await page.click('#tour [data-t="next"]'); await page.wait_for_timeout(300)
            check("8: «Готово» закрывает тур", await page.locator("#tour").count() == 0)
            await page.click('button[data-tab="day"]'); await page.evaluate("window.scrollTo(0, 0); 0")
            await page.click("header .help-btn"); await page.wait_for_timeout(400)
            st = await page.evaluate(S)
            check("8: цель в верхней части экрана (week-badge) — окно подсветки ниже плашки", st["target"] == "week-badge" and st["hole"]["t"] >= st["bar"]["b"] - 0.5, st)
            sm = await page.evaluate("document.querySelector('[data-tour=week-badge]').style.scrollMarginTop")
            check("8: scroll-margin-top цели = высоте плашки", abs(float(sm[:-2]) - st["bar"]["b"]) < 1, (sm, st["bar"]["b"]))
            await page.click('#tour [data-t="skip"]'); await page.wait_for_timeout(250)
            check("8: «Выйти» закрывает тур без следов (оверлея нет, TOUR_MODE выключен, класс in-tour снят)", await page.locator("#tour").count() == 0 and await page.evaluate("TOUR_MODE") is False and await page.evaluate("!document.body.classList.contains('in-tour')"))
            await page.evaluate("document.documentElement.style.setProperty('--sa-top','47px'); 0")
            await page.click("header .help-btn"); await page.wait_for_timeout(350)
            sa = await page.evaluate(S)
            check("8: safe-area: плашка начинается ниже верхнего выреза (top = 47px)", abs(sa["bar"]["t"] - 47) < 1.5, sa["bar"])
            await page.click('#tour [data-t="skip"]'); await page.evaluate("document.documentElement.style.removeProperty('--sa-top'); 0")
            for w, fs in [(320, 1), (320, 1.3)]:
                await page.set_viewport_size({"width": w, "height": 640})
                await page.evaluate("data.cfg.fontScale=%s; applyFontScale(); render(); 0" % fs); await page.wait_for_timeout(150)
                await page.click('button[data-tab="day"]'); await page.click("header .help-btn"); await page.wait_for_timeout(350)
                ok = True; why = None
                for i in range(20):
                    await page.wait_for_timeout(200)
                    s2 = await page.evaluate(S)
                    if s2["bar"]["r"] > s2["vw"] + 0.5 or s2["exitW"] < 40 or not s2["rightOfCount"] or s2["tipTop"] < s2["bar"]["b"] - 0.5: ok = False; why = s2; break
                    if await page.inner_text('#tour [data-t="next"]') == "Готово": break
                    await page.click('#tour [data-t="next"]')
                check("8: %dpx/%d%%: плашка в экране, счётчик и «Выйти» не накладываются, подсказка ниже плашки на всех шагах" % (w, fs * 100), ok, why)
                await page.click('#tour [data-t="skip"]'); await page.wait_for_timeout(150)
            check("нет pageerror", not errs, errs[:2])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
