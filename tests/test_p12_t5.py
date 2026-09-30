"""Фаза 12, задача 5: алиасы — вертикальный вид и новое описание. На реальном дампе."""
import asyncio, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
NEW_TEXT_1 = "Алиасы объединяют разные названия одного упражнения или варианта. Например, в старых записях было «Голень стоя», а в шаблоне — «Голень стоя (икры)». Без алиаса это два разных упражнения: история, графики и рекомендации разрываются."
NEW_TEXT_2 = "Сверху — название, как оно записано в истории. Снизу — как оно должно называться (как в шаблоне). После сохранения старые записи пересчитаются, сами тренировки не меняются."

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
            await page.click('button[data-tab="set"]'); await page.click('[data-act="aliasOpen"]'); await page.wait_for_timeout(300)
            txt = await page.inner_text(".al-explain")
            check("5.3: новое пояснение вверху экрана (оба абзаца из ТЗ)", NEW_TEXT_1 in txt and NEW_TEXT_2 in txt and "Слева" not in txt, txt[:120])
            geo = await page.evaluate("""(()=>{ const c=[...document.querySelectorAll('.al-card')].find(x=>x.querySelector('.al-old').textContent==='Голень стоя'); const q=(s)=>c.querySelector(s).getBoundingClientRect();
                const cap1=c.querySelectorAll('.al-cap')[0], cap2=c.querySelectorAll('.al-cap')[1], div=c.querySelector('.al-divider'), line=c.querySelectorAll('.al-divider i'), arrow=c.querySelector('.al-divider svg');
                const cr=c.getBoundingClientRect(), tx=q('.al-txt'), dv=div.getBoundingClientRect(), ar=arrow.getBoundingClientRect(), l0=line[0].getBoundingClientRect(), l1=line[1].getBoundingClientRect();
                return {order:[cap1.getBoundingClientRect().top, q('.al-old').top, dv.top, cap2.getBoundingClientRect().top, q('.al-new').top, q('.al-count').top], caps:[cap1.textContent, cap2.textContent], old:q('.al-old'), newW:getComputedStyle(c.querySelector('.al-new')).fontWeight,
                    lineBg:getComputedStyle(line[0]).backgroundColor, muted:getComputedStyle(document.documentElement).getPropertyValue('--text-muted'), lineH:l0.height,
                    lineSpan:(l1.right-l0.left)+0, txW:tx.width, arrowCenter:Math.abs((ar.left+ar.right)/2-(dv.left+dv.right)/2), count:c.querySelector('.al-count').textContent, del:c.querySelector('.al-del').getBoundingClientRect().top, cardTop:cr.top}; })()""")
            check("5.1: карточка вертикальная: «Было в истории» → старое → линия со стрелкой → «Стало» → каноническое → «Затрагивает N тренировок» (строго сверху вниз)", geo["order"] == sorted(geo["order"]) and geo["caps"] == ["Было в истории", "Стало"], geo["order"])
            check("5.1: линия на всю ширину текстового блока цветом --text-muted (1px), стрелка вниз строго по центру", geo["lineH"] == 1 and geo["arrowCenter"] < 1.5 and geo["lineSpan"] >= geo["txW"] - 30, (geo["lineSpan"], geo["txW"], geo["arrowCenter"]))
            check("5.1: каноническое название полужирным; «Затрагивает N тренировок» с верным склонением", geo["newW"] in ("700", "bold") and geo["count"] == "Затрагивает 9 тренировок", (geo["newW"], geo["count"]))
            check("5.1: корзина у карточки справа вверху", geo["del"] - geo["cardTop"] < 20, (geo["del"], geo["cardTop"]))
            word = await page.evaluate("[...document.querySelectorAll('.al-card .al-count')].map(e=>e.textContent)")
            check("5.1: склонение: 1 тренировка / 2 тренировки / 5 тренировок", await page.evaluate("[1,2,5,21,11].map(n=>n+' '+plural(n,'тренировка','тренировки','тренировок'))") == ["1 тренировка", "2 тренировки", "5 тренировок", "21 тренировка", "11 тренировок"], word[:2])
            # тап — редактирование, корзина — удаление
            await page.locator(".al-card").first.locator(".al-txt").click(); await page.wait_for_timeout(200)
            check("5.1: тап по карточке — редактирование (форма с заполненными полями)", await page.locator("#alias-left").count() == 1 and (await page.input_value("#alias-left")) != "")
            # форма: вертикально
            fm = await page.evaluate("""(()=>{ const l=document.getElementById('alias-left').getBoundingClientRect(), r=document.getElementById('alias-right').getBoundingClientRect(), d=document.querySelector('.card .al-divider').getBoundingClientRect();
                const labels=[...document.querySelectorAll('.card .lbl')].map(x=>x.textContent.trim()); return {leftAboveRight:l.bottom<=r.top, divBetween:d.top>=l.bottom&&d.bottom<=r.top, sameX:Math.abs(l.left-r.left)<1&&Math.abs(l.width-r.width)<1, labels}; })()""")
            check("5.2: форма: поля друг под другом с чертой и стрелкой между ними, подписи «Было в истории» и «Стало — как в шаблоне»", fm["leftAboveRight"] and fm["divBetween"] and fm["sameX"] and fm["labels"][:2] == ["Было в истории", "Стало — как в шаблоне"], fm)
            await page.click('[data-act="aliasFormCancel"]'); await page.click('[data-act="aliasNew"]')
            await page.fill("#alias-left", "Пуловер (3х10-20)"); await page.fill("#alias-right", "Пуловер в кроссовере"); await page.press("#alias-right", "Tab"); await page.wait_for_timeout(200)
            check("5.2: валидация, предпросмотр и обрезка плана — как в фазе 11 (поле очищено, подсказка, предпросмотр)", (await page.input_value("#alias-left")) == "Пуловер" and "План и вариант убраны" in await page.inner_text("#alMsgs"))
            await page.fill("#alias-left", "голень СТОЯ"); await page.wait_for_timeout(100)
            check("5.2: дубль слева по-прежнему отклоняется", "Для этого названия алиас уже есть" in await page.inner_text("#alMsgs") and await page.locator("#alSave").is_disabled())
            await page.click('[data-act="aliasFormCancel"]'); await page.wait_for_timeout(100)
            # первый экран
            first = await page.evaluate("(()=>{ const c=document.querySelector('.al-card').getBoundingClientRect(); return {bottom:c.bottom, nav:document.getElementById('tabbar').getBoundingClientRect().top, ex:document.querySelector('.al-explain').getBoundingClientRect().top>=0}; })()")
            check("5.3: на iPhone 13 (390×844) пояснение и первая пара целиком над нижней навигацией", first["ex"] and first["bottom"] <= first["nav"], first)
            # 320 px, 130%
            await page.set_viewport_size({"width": 320, "height": 800})
            await page.evaluate("data.cfg.fontScale=1.3; applyFontScale(); render(); 0"); await page.wait_for_timeout(200)
            ov = await page.evaluate("(()=>{ const W=innerWidth; const bad=[...document.querySelectorAll('.al-card *')].filter(e=>e.getBoundingClientRect().right>W+1).length; return {bad, scroll:document.documentElement.scrollWidth<=W}; })()")
            check("5: на 320px и 130% карточки алиасов не выходят за экран, длинные названия переносятся", ov["bad"] == 0 and ov["scroll"], ov)
            await page.evaluate("data.cfg.fontScale=1; applyFontScale(); render(); 0")
            # справочник
            await page.evaluate("openHelp('set'); 0"); await page.wait_for_timeout(200)
            sect = await page.evaluate("document.querySelector('#helpOv [data-sec=set]').textContent")
            check("5.3: тот же текст в справочнике (раздел «Настройки» → «Алиасы»)", NEW_TEXT_1 in sect and NEW_TEXT_2 in sect, sect[-400:])
            check("нет pageerror", not errs, errs[:2])
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_alias_vert.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
