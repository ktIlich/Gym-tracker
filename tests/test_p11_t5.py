"""Фаза 11, задача 5: приветственный экран. На реальном дампе (без поля onboardingSeen — как у существующего пользователя)."""
import asyncio, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, check, RESULTS, REPO, BASE
from test_task7 import seed
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
BB = "(()=>{ const W=window.Telegram.WebApp; window.__bb=false; W.BackButton={show(){window.__bb=true},hide(){window.__bb=false},onClick(cb){window.__bbcb=cb}}; })();"
INSETS = "(()=>{ const W=window.Telegram.WebApp; W.safeAreaInset={top:47,bottom:34,left:0,right:0}; W.contentSafeAreaInset={top:56,bottom:0,left:0,right:0}; W.viewportStableHeight=800; W.onEvent=()=>{}; })();"
DAY = 86400000

async def open_page(browser, extra="", endpoint="", reduced=False, viewport=(390, 844)):
    ctx = await browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, reduced_motion="reduce" if reduced else "no-preference")
    await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
    await ctx.add_init_script(BB + extra)
    page = await ctx.new_page(); errs = []; reqs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    await page.route("**/telegram.org/**", lambda r: r.abort()); await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
    async def index(route):
        resp = await route.fetch(); txt = await resp.text()
        if endpoint: txt = txt.replace('const BACKUP_ENDPOINT="";', 'const BACKUP_ENDPOINT="%s";' % endpoint)
        await route.fulfill(response=resp, body=txt)
    await page.route("**/test/index.html", index)
    async def worker(route):
        if route.request.method == "OPTIONS": return await route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "POST, OPTIONS"})
        reqs.append(1); await route.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*"}, content_type="application/json", body='{"ok":true}')
    await page.route("https://worker.test/**", worker)
    return page, errs, reqs

def seed_raw(dump, **over):
    seed(dump)
    cfg = json.loads(STORE["tst_cfg"]); cfg.pop("onboardingSeen", None); cfg.update(over); STORE["tst_cfg"] = json.dumps(cfg)

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8"))
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            raw_dump = json.loads(json.dumps(dump))
            seed_raw(dump); _pg, _e, _r = await open_page(browser); await _pg.goto(BASE + "/test/index.html"); await _pg.wait_for_timeout(2500)
            mig_dump = await _pg.evaluate("({cfg:data.cfg,templates:data.templates,log:data.log})"); await _pg.context.close()   # уже мигрированные данные (копия перед миграцией — в test_prod_prep)
            load = lambda page, w=2500: (page.goto(BASE + "/test/index.html"))

            # ---- существующий пользователь: поля onboardingSeen нет
            seed_raw(dump)
            check("5.1: у существующих данных поля onboardingSeen нет (→ 0)", "onboardingSeen" not in STORE["tst_cfg"])
            page, errs, reqs = await open_page(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            check("5.4: существующий пользователь (данные склонированы из prod) видит приветствие при первом открытии test", await page.locator("#onb").count() == 1 and await page.evaluate("ui.onb.idx===0"))
            check("5.1: константа ONBOARDING_VERSION = 1", await page.evaluate("ONBOARDING_VERSION===1"))
            ov = await page.evaluate("""(()=>{ const o=document.getElementById('onb'), r=o.getBoundingClientRect(); const card=o.querySelectorAll('.onb-card')[0];
                return {full:getComputedStyle(o).position==='fixed'&&r.width>=innerWidth-1&&r.height>=innerHeight-1, bg:getComputedStyle(o).backgroundColor===getComputedStyle(document.body).backgroundColor,
                        icon:card.querySelector('.onb-ic svg').getBoundingClientRect().width, iconColor:getComputedStyle(card.querySelector('.onb-ic')).color, title:card.querySelector('.onb-title').textContent, text:card.querySelector('.onb-text').textContent,
                        dots:[...o.querySelectorAll('.onb-dots i')].map(d=>d.classList.contains('on')), next:o.querySelector('[data-onb=next]').textContent, nextBg:getComputedStyle(o.querySelector('[data-onb=next]')).backgroundColor,
                        nextW:o.querySelector('[data-onb=next]').getBoundingClientRect().width, skip:getComputedStyle(o.querySelector('[data-onb=skip]')).visibility, skipTxt:o.querySelector('[data-onb=skip]').textContent,
                        help:getComputedStyle(o.querySelector('[data-onb=help]')).display, z:+getComputedStyle(o).zIndex}; })()""")
            check("5.2: полноэкранный оверлей с фоном приложения, поверх навигации", ov["full"] and ov["bg"] and ov["z"] > await page.evaluate("+getComputedStyle(document.getElementById('tabbar')).zIndex"), ov)
            check("5.2: иконка 48px акцентного цвета, заголовок и текст первой карточки", ov["icon"] == 48 and ov["iconColor"] == "rgb(255, 159, 10)" and ov["title"] == "Твой дневник тренировок" and ov["text"].startswith("Шаблоны, запись подходов, рекомендации по весу и прогресс"), ov)
            check("5.2: 5 точек, текущая акцентная; кнопка «Далее» на всю ширину, залита акцентом; «Пропустить» виден; «Открыть справку» скрыта", ov["dots"] == [True, False, False, False, False] and ov["next"] == "Далее" and ov["nextBg"] == "rgb(255, 159, 10)" and ov["nextW"] > 340 and ov["skip"] == "visible" and ov["skipTxt"] == "Пропустить" and ov["help"] == "none", ov)
            check("5.2: BackButton на первой карточке скрыт", await page.evaluate("window.__bb") is False)
            titles = []
            texts = []
            for i in range(5):
                titles.append(await page.evaluate("document.querySelectorAll('.onb-card')[%d].querySelector('.onb-title').textContent" % i))
                texts.append(await page.evaluate("document.querySelectorAll('.onb-card')[%d].querySelector('.onb-text').textContent" % i))
            check("5.3: заголовки пяти карточек", titles == ["Твой дневник тренировок", "Шаблоны", "Запись подхода", "Цикл и прогресс", "Резервная копия"], titles)
            check("5.3: тексты карточек 2–4 как в ТЗ", texts[1] == "Тренировочные дни собираются из упражнений и суперсетов. План пишется как 3х8-12, у упражнения могут быть варианты — например, блок или свободный вес."
                  and texts[2] == "Следующий подход уже заполнен рекомендацией или прошлым результатом. ± меняют вес и повторы, галочка записывает. Цветной бейдж — рекомендация на сегодня. По «?» на каждой вкладке есть подсказки прямо на экране."
                  and texts[3] == "Рабочие недели и недели отдыха считаются автоматически, в неделю отдыха вес снижается сам. На вкладке «Прогресс» — графики, тоннаж и сравнение циклов.", texts[1:4])
            check("5.3: карточка 5 при пустом BACKUP_ENDPOINT — «Сохрани копию данных в настройках — JSON для восстановления. Приложение напомнит, если копия давно не делалась.»", texts[4] == "Сохрани копию данных в настройках — JSON для восстановления. Приложение напомнит, если копия давно не делалась.", texts[4])
            icons = await page.evaluate("[...document.querySelectorAll('.onb-card .onb-ic')].map(e=>!!e.querySelector('svg.icon')&&e.textContent.trim()==='')")
            check("5.3: иконки карточек — SVG (гантель, закладка, галочка, календарь, облако со стрелкой)", icons == [True] * 5)
            src = open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read()
            check("5.3: иконки — те самые константы (ICON_DUMBBELL, ICON_BOOKMARK, ICON_CHECK, ICON_CALENDAR, ICON_CLOUD_UP)", all(n in src.split("function onbCards(){")[1].split("];")[0] for n in ("ICON_DUMBBELL", "ICON_BOOKMARK", "ICON_CHECK", "ICON_CALENDAR", "ICON_CLOUD_UP")))

            # ---- навигация
            await page.click('[data-onb="next"]'); await page.wait_for_timeout(300)
            check("5.2: «Далее» переходит ко второй карточке; BackButton показан", await page.evaluate("ui.onb.idx")  == 1 and await page.evaluate("window.__bb") is True and await page.evaluate("document.querySelector('.onb-dots i.on')===document.querySelectorAll('.onb-dots i')[1]"))
            await page.evaluate("window.__bbcb()"); await page.wait_for_timeout(250)
            check("5.2: BackButton на карточке 2 возвращает на предыдущую и снова скрывается", await page.evaluate("ui.onb.idx")  == 0 and await page.evaluate("window.__bb") is False)
            # свайп
            async def swipe(dx):
                box = await page.locator(".onb-viewport").bounding_box()
                y = box["y"] + box["height"] / 2; x = box["x"] + box["width"] / 2
                await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x + dx, y, steps=6); await page.mouse.up(); await page.wait_for_timeout(300)
            await swipe(-150)
            s1 = await page.evaluate("ui.onb.idx")
            await swipe(+150)
            s2 = await page.evaluate("ui.onb.idx")
            await swipe(+150)
            s3 = await page.evaluate("ui.onb.idx")
            await swipe(-20)
            s4 = await page.evaluate("ui.onb.idx")
            check("5.2: свайп влево — вперёд, вправо — назад; на краю не выходит за пределы; короткое смещение игнорируется", (s1, s2, s3, s4) == (1, 0, 0, 0), (s1, s2, s3, s4))
            dur = await page.evaluate("getComputedStyle(document.querySelector('.onb-track')).transitionDuration")
            check("5.2: анимация сдвига ≤ 200 мс", dur == "0.2s", dur)
            # дойти до последней карточки
            for _ in range(4): await page.click('[data-onb="next"]'); await page.wait_for_timeout(120)
            last = await page.evaluate("""(()=>{ const o=document.getElementById('onb'); return {idx:ui.onb.idx, next:o.querySelector('[data-onb=next]').textContent, skip:getComputedStyle(o.querySelector('[data-onb=skip]')).visibility, help:getComputedStyle(o.querySelector('[data-onb=help]')).display, helpFilled:getComputedStyle(o.querySelector('[data-onb=help]')).backgroundColor}; })()""")
            check("5.2: на последней карточке «Начать», «Пропустить» скрыт, под кнопкой вторичная «Открыть справку» (не залита акцентом)", last["idx"] == 4 and last["next"] == "Начать" and last["skip"] == "hidden" and last["help"] != "none" and last["helpFilled"] != "rgb(255, 159, 10)", last)

            # ---- «Начать» ставит флаг
            await page.click('[data-onb="next"]'); await page.wait_for_timeout(500)
            check("5.1: «Начать» закрывает приветствие, ставит cfg.onboardingSeen=1 и синхронизирует cfg (облако)", await page.locator("#onb").count() == 0 and await page.evaluate("data.cfg.onboardingSeen") == 1 and '"onboardingSeen":1' in STORE["tst_cfg"])
            await page.reload(); await page.wait_for_timeout(2500)
            check("5.4: после перезапуска приветствие не показывается", await page.locator("#onb").count() == 0)

            # ---- «Пропустить» на карточке 2; другое устройство
            seed_raw(dump)
            page, errs2, _ = await open_page(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.click('[data-onb="next"]'); await page.wait_for_timeout(300)
            await page.click('[data-onb="skip"]'); await page.wait_for_timeout(500)
            check("5.4: «Пропустить» на карточке 2 → приветствие закрыто, флаг выставлен", await page.locator("#onb").count() == 0 and await page.evaluate("data.cfg.onboardingSeen") == 1 and '"onboardingSeen":1' in STORE["tst_cfg"])
            await page.reload(); await page.wait_for_timeout(2500)
            check("5.4: после перезапуска не показывается", await page.locator("#onb").count() == 0)
            other, eo, _ = await open_page(browser)   # «другое устройство»: новый контекст, пустой localStorage, флаг только в облаке
            await other.goto(BASE + "/test/index.html"); await other.wait_for_timeout(2500)
            check("5.4: на другом устройстве (флаг пришёл из облака) приветствие не появляется", await other.locator("#onb").count() == 0 and await other.evaluate("data.cfg.onboardingSeen") == 1)

            # ---- закрыли посреди показа → флага нет → повтор с первой карточки
            seed_raw(dump)
            page, e3, _ = await open_page(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.click('[data-onb="next"]'); await page.click('[data-onb="next"]'); await page.wait_for_timeout(300)
            check("5.1: посреди показа (карточка 3) флаг не ставится", await page.evaluate("ui.onb.idx") == 2 and "onboardingSeen" not in STORE["tst_cfg"])
            await page.reload(); await page.wait_for_timeout(2500)
            check("5.1: при следующем старте показ повторяется с первой карточки", await page.locator("#onb").count() == 1 and await page.evaluate("ui.onb.idx") == 0)

            # ---- «Показать приветствие» из настроек: флаг не меняется
            await page.click('[data-onb="skip"]'); await page.wait_for_timeout(300)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            check("5.1: в «Настройках» есть пункт «Показать приветствие»", await page.locator('[data-act="onbShow"]').count() == 1)
            await page.locator('[data-act="onbShow"]').click(); await page.wait_for_timeout(300)
            check("5.4: «Показать приветствие» открывает его с первой карточки", await page.locator("#onb").count() == 1 and await page.evaluate("ui.onb.idx===0"))
            await page.evaluate("data.cfg.onboardingSeen=0; 0")
            await page.click('[data-onb="next"]'); await page.click('[data-onb="skip"]'); await page.wait_for_timeout(300)
            check("5.4: закрытие приветствия, открытого из настроек, флаг не меняет и повторно не показывает", await page.locator("#onb").count() == 0 and await page.evaluate("data.cfg.onboardingSeen") == 0)
            await page.locator('[data-act="onbShow"]').click(); await page.wait_for_timeout(200)
            for _ in range(4): await page.click('[data-onb="next"]'); await page.wait_for_timeout(100)
            await page.click('[data-onb="next"]'); await page.wait_for_timeout(300)
            check("5.4: «Начать» из настроек тоже не меняет флаг", await page.evaluate("data.cfg.onboardingSeen") == 0 and await page.locator("#onb").count() == 0)
            check("нет pageerror (приветствие)", not (errs or errs2 or eo or e3), (errs[:1], errs2[:1], eo[:1], e3[:1]))

            # ---- «Открыть справку»
            seed_raw(dump)
            page, e4, _ = await open_page(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            for _ in range(4): await page.click('[data-onb="next"]'); await page.wait_for_timeout(100)
            check("7: на последней карточке вторичная кнопка называется «Пройти тур»", await page.inner_text('[data-onb="help"]') == "Пройти тур")
            await page.click('[data-onb="help"]'); await page.wait_for_timeout(400)
            check("7: «Пройти тур» ставит флаг, закрывает приветствие и запускает тур по всем табам с «Сегодня»", await page.locator("#onb").count() == 0 and await page.evaluate("data.cfg.onboardingSeen") == 1
                  and await page.locator("#tour").count() == 1 and await page.evaluate("[tour.mode, tour.cur.target, tour.steps.length, ui.tab]") == ["all", "week-badge", 37, "day"])
            await page.click('#tour [data-t="skip"]'); await page.wait_for_timeout(200)
            check("7: после выхода из тура приложение на реальных данных, приветствие не возвращается", await page.locator("#tour").count() == 0 and await page.locator("#onb").count() == 0 and await page.evaluate("TOUR_MODE") is False)

            # ---- карточка 5 при заданном сервере; reduced-motion
            seed_raw(dump)
            page, e5, _ = await open_page(browser, endpoint="https://worker.test/", reduced=True)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            t5 = await page.evaluate("document.querySelectorAll('.onb-card')[4].querySelector('.onb-text').textContent")
            check("5.3: при заданном BACKUP_ENDPOINT карточка 5: «Отправь копию в чат с ботом — JSON для восстановления, Excel или CSV для просмотра…»", t5 == "Отправь копию в чат с ботом — JSON для восстановления, Excel или CSV для просмотра. Приложение напомнит, если копия давно не делалась.", t5)
            check("5.2: prefers-reduced-motion — без анимации (transition none)", await page.evaluate("getComputedStyle(document.querySelector('.onb-track')).transitionDuration") in ("0s", "0.0s"))

            # ---- safe-area
            seed_raw(dump)
            page, e6, _ = await open_page(browser, extra=INSETS)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            sa = await page.evaluate("""(()=>{ const o=document.getElementById('onb'), s=o.querySelector('[data-onb=skip]').getBoundingClientRect(), n=o.querySelector('[data-onb=next]').getBoundingClientRect(); return {skipTop:s.top, nextBottom:n.bottom, h:innerHeight, pt:getComputedStyle(o).paddingTop, pb:getComputedStyle(o).paddingBottom}; })()""")
            check("5.4: кнопки не заходят под системные зоны: «Пропустить» ниже 47+56 px, «Далее» выше нижнего inset (34 px)", sa["skipTop"] >= 103 and sa["nextBottom"] <= sa["h"] - 34, sa)

            # ---- новый пользователь: сначала мастер, затем приветствие
            STORE.clear()
            page, e7, _ = await open_page(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            check("5.1: новый пользователь: первым идёт мастер настройки цикла, приветствия пока нет", await page.locator('[data-act="setupNext"]').count() == 1 and await page.locator("#onb").count() == 0)
            await page.click('[data-act="setupNext"]'); await page.click('[data-act="setupSkip"]'); await page.wait_for_timeout(500)
            check("5.1: после мастера показывается приветствие", await page.locator("#onb").count() == 1)

            # ---- автоотправка копии ждёт закрытия приветствия
            seed_raw(mig_dump, lastBackup=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 20 * 86400)), autoBackup=True, writeAccess=True)
            page, e8, reqs = await open_page(browser, endpoint="https://worker.test/")
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(3000)
            before = len(reqs)
            await page.click('[data-onb="skip"]'); await page.wait_for_timeout(1500)
            check("5.1: автоотправка не запускается поверх приветствия — только после его закрытия", before == 0 and len(reqs) == 1, (before, len(reqs)))
            check("нет pageerror (остальное)", not (e4 or e5 or e6 or e7 or e8), (e4[:1], e5[:1], e6[:1], e7[:1], e8[:1]))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
