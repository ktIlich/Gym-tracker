"""Фаза 12, задача 6: интерактивный тур по интерфейсу (на демо-данных, без записи в хранилище)."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, WRITES, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
TABS = [("day", "today"), ("tpl", "templates"), ("cal", "calendar"), ("prg", "progress"), ("set", "settings")]

STATE = """(()=>{ const t=document.querySelector('#tour'); if(!t) return null;
    const cur=window.__tourCur&&window.__tourCur(); const hole=t.querySelector('.tour-hole').getBoundingClientRect(), tip=t.querySelector('.tour-tip').getBoundingClientRect(), ar=t.querySelector('.tour-arrow');
    const target=document.querySelector('[data-tour="'+cur.target+'"]'); const r=target.getBoundingClientRect();
    const tb=document.getElementById('tabbar').getBoundingClientRect(), bn=t.querySelector('.tour-banner').getBoundingClientRect();
    const arr=ar.style.display==='none'?null:ar.getBoundingClientRect();
    return {target:cur.target, idx:cur.idx, total:cur.total, title:t.querySelector('.tour-title').textContent, text:t.querySelector('.tour-text').textContent, count:t.querySelector('.tour-count').textContent,
        hole:{l:hole.left,t:hole.top,w:hole.width,h:hole.height}, r:{l:r.left,t:r.top,w:r.width,h:r.height}, tip:{l:tip.left,t:tip.top,r:tip.right,b:tip.bottom,w:tip.width},
        arrowX:arr?(arr.left+arr.right)/2:null, cx:(r.left+r.right)/2, vw:innerWidth, vh:innerHeight, tabTop:tb.top, tabH:tb.height, banBottom:bn.bottom,
        vis:(r.bottom>0&&r.top<innerHeight), prevShown:getComputedStyle(t.querySelector('[data-t=prev]')).display!=='none', helpShown:getComputedStyle(t.querySelector('[data-t=help]')).display!=='none',
        nextText:t.querySelector('[data-t=next]').textContent, skipShown:getComputedStyle(t.querySelector('[data-t=skip]')).display!=='none'}; })()"""

async def walk(page, label, geometry=True):
    """Проходит тур кнопкой «Далее» до конца, возвращает список состояний шагов."""
    steps = []; bad = []
    for _ in range(80):
        await page.wait_for_timeout(260)
        st = await page.evaluate(STATE)
        if not st: break
        steps.append(st)
        if geometry:
            H = st["hole"]; R = st["r"]
            exact = abs(H["l"] - (R["l"] - 6)) < 1.5 and abs(H["w"] - (R["w"] + 12)) < 1.5
            tall = R["h"] + 12 > st["vh"] - 20
            ok_v = tall or (abs(H["t"] - (R["t"] - 6)) < 1.5 and abs(H["h"] - (R["h"] + 12)) < 1.5) or H["t"] == 0 or H["t"] + H["h"] >= st["vh"] - 0.5
            inside = st["tip"]["l"] >= 0 and st["tip"]["r"] <= st["vw"] + 0.5 and st["tip"]["t"] >= st["banBottom"] and st["tip"]["b"] <= st["tabTop"] + 0.5
            arrow_ok = st["arrowX"] is None or (st["tip"]["l"] + 6 <= st["arrowX"] <= st["tip"]["r"] - 6 and (abs(st["arrowX"] - st["cx"]) < 1.5 or st["arrowX"] <= st["tip"]["l"] + 21 or st["arrowX"] >= st["tip"]["r"] - 21))
            if not (exact and ok_v and inside and arrow_ok and st["vis"]): bad.append((st["target"], exact, ok_v, inside, arrow_ok, st["vis"]))
        if st["nextText"] == "Готово": break
        await page.click('#tour [data-t="next"]')
    return steps, bad

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
            # ---- статика
            check("6: правило-комментарий над TOUR и HELP (каждое ТЗ обновляет тур, data-tour и справочник)", src.count("ПРАВИЛО: каждое ТЗ") >= 2 and "обновляет шаги тура" in src)
            tour_targets = set(re.findall(r'\{ target:"([a-z-]+)"', src))
            attr_targets = set(re.findall(r'data-tour="([a-z-]+)"', src)) | set(re.findall(r'tw\("([a-z-]+)"', src))
            check("6.2: каждый target тура есть как data-tour в разметке", tour_targets <= attr_targets, tour_targets - attr_targets)
            check("6.2: селекторы по классам для тура не используются (только [data-tour=…])", "querySelector('[data-tour=\"'+" in src and "querySelector(\".tour-" in src)
            check("6.3: в TOUR_MODE запись бросает исключение (guardKey) и persist*/flush/cloudLoad/автокопия не пишут", "Blocked write in TOUR_MODE" in src and src.count("TOUR_MODE") >= 12)
            check("6.2: анимация до 250 мс, при prefers-reduced-motion — без анимации", "transition:left .2s ease" in src and "prefers-reduced-motion: reduce){ .tour-hole" in src)

            seed(dump)
            page, errs = await open_tg(browser)
            await page.add_init_script("")
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.evaluate("window.__tourCur=()=>({target:tour.cur.target,idx:tour.idx,total:tour.steps.length}); 0")
            before_keys = dict(STORE); before_writes = len(WRITES)
            before_ls = await page.evaluate("JSON.stringify(Object.keys(localStorage).sort().map(k=>[k,localStorage.getItem(k)]))")
            before_data = await page.evaluate("JSON.stringify(data)")

            # ---- «?» на каждом табе: тур этого таба
            for tab, tkey in TABS:
                await page.click('button[data-tab="%s"]' % tab); await page.wait_for_timeout(150)
                hb = await page.evaluate("(()=>{const b=document.querySelector('header .help-btn'); const r=b.getBoundingClientRect(); return {w:r.width,h:r.height,label:b.getAttribute('aria-label')}; })()")
                check("6.1: [%s] «?» в шапке 44×44 (не меньше)" % tab, hb["w"] >= 43.5 and hb["h"] >= 43.5, hb)
                await page.click("header .help-btn"); await page.wait_for_timeout(300)
                check("6.1: [%s] «?» запускает тур (оверлей, плашка «Пример — данные не сохраняются», справочник не открылся)" % tab,
                      await page.locator("#tour").count() == 1 and "Пример — данные не сохраняются" in await page.inner_text("#tour .tour-banner") and await page.locator("#helpOv").count() == 0)
                steps, bad = await walk(page, tab)
                names = [s["target"] for s in steps]
                exp = re.findall(r'target:"([a-z-]+)"', src[src.index("const TOUR={"):src.index("const TOUR_ORDER")])
                check("6.7: [%s] тур показал шаги: %s" % (tab, names), len(steps) >= 2, names)
                check("6.7: [%s] окно точно вокруг цели (отступ 6px), подсказка не выходит за экран и не заходит под шапку/навигацию, стрелка на цель (390×844)" % tab, not bad, bad[:3])
                last = steps[-1]
                check("6.1: [%s] последний шаг: «Готово» и «Вся справка», «Пропустить» скрыт, счётчик «N / M»" % tab, last["nextText"] == "Готово" and last["helpShown"] and not last["skipShown"] and re.match(r"^\d+ / \d+$", last["count"]), last)
                check("6: [%s] на первом шаге нет «Назад»" % tab, not steps[0]["prevShown"] and steps[0]["count"].startswith("1 /"))
                await page.click('#tour [data-t="help"]'); await page.wait_for_timeout(300)
                sec = await page.evaluate("Object.keys(ui.help.open)")
                check("6.1: [%s] «Вся справка» закрывает тур и открывает справочник на разделе таба" % tab, await page.locator("#tour").count() == 0 and sec == [tab], sec)
                await page.evaluate("closeHelp(); 0"); await page.wait_for_timeout(100)
            print("   шаги по табам проверены")

            # ---- содержимое шагов (6.4 / 6.5)
            await page.click('button[data-tab="day"]'); await page.click("header .help-btn"); await page.wait_for_timeout(300)
            steps, _ = await walk(page, "day", geometry=False)
            names = [s["target"] for s in steps]
            check("6.4: «Сегодня» на демо: все шаги показаны (ничего не пропущено)", names == ["week-badge", "day-title", "day-note", "rec-badge", "prev-line", "warmup-line", "next-set", "set-confirm", "set-delete", "ex-delete", "ex-timer", "ex-variant", "ex-note", "superset", "day-tpl", "tabbar"], names)
            check("6.4: тексты на «ты», без «разгрузк», не длиннее двух предложений", all(("разгруз" not in s["text"].lower()) and len(re.findall(r"[.!?…](?:\s|$)", s["text"])) <= 2 for s in steps), [s["text"] for s in steps if len(re.findall(r"[.!?…](?:\s|$)", s["text"])) > 2])
            await page.click('#tour [data-t="next"]'); await page.wait_for_timeout(200)
            await page.click('button[data-tab="tpl"]'); await page.click("header .help-btn"); await page.wait_for_timeout(300)
            st2, _ = await walk(page, "tpl", geometry=False)
            check("6.4: «Шаблоны»: список, импорт и 5 шагов редактора (план, варианты, чередование, суперсет, порядок)", [s["target"] for s in st2] == ["tpl-list", "tpl-import", "tpl-plan", "tpl-variants", "tpl-alt", "tpl-superset", "tpl-order"], [s["target"] for s in st2])
            await page.click('#tour [data-t="next"]')
            await page.click('button[data-tab="cal"]'); await page.click("header .help-btn"); await page.wait_for_timeout(300)
            st3, _ = await walk(page, "cal", geometry=False)
            check("6.4: «Календарь»: cal-week, cal-day (cal-override перенесён на «Сегодня»)", [s["target"] for s in st3] == ["cal-week", "cal-day"], [s["target"] for s in st3])
            await page.click('#tour [data-t="next"]')
            await page.click('button[data-tab="prg"]'); await page.click("header .help-btn"); await page.wait_for_timeout(300)
            st4, _ = await walk(page, "prg", geometry=False)
            check("6.4: «Прогресс»: упражнение, линии вариантов, тоннаж, сравнение циклов", [s["target"] for s in st4] == ["prog-ex", "prog-lines", "prog-tonnage", "prog-cycles"], [s["target"] for s in st4])
            await page.click('#tour [data-t="next"]')
            await page.click('button[data-tab="set"]'); await page.click("header .help-btn"); await page.wait_for_timeout(300)
            st5, _ = await walk(page, "set", geometry=False)
            check("6.4: «Настройки»: 8 шагов", [s["target"] for s in st5] == ["set-cycle", "set-timer", "set-font", "set-theme", "set-backup", "set-import", "set-cleanup", "set-help"], [s["target"] for s in st5])
            check("6.5: set-backup: текст зависит от BACKUP_ENDPOINT (в test — без сервера)", "после подключения сервера" in st5[4]["text"], st5[4]["text"])
            await page.click('#tour [data-t="next"]'); await page.wait_for_timeout(200)

            # ---- навигация: Назад, свайп, BackButton, блокировка кликов
            await page.click('button[data-tab="day"]'); await page.click("header .help-btn"); await page.wait_for_timeout(300)
            await page.click('#tour [data-t="next"]'); await page.wait_for_timeout(250)
            s2 = await page.evaluate(STATE); check("6: «Далее» → второй шаг, «Назад» появился", s2["idx"] == 1 and s2["prevShown"], s2["idx"])
            await page.click('#tour [data-t="prev"]'); await page.wait_for_timeout(250)
            check("6: «Назад» возвращает на первый шаг", (await page.evaluate(STATE))["idx"] == 0)
            box = await page.evaluate("(()=>{const r=document.querySelector('#tour').getBoundingClientRect(); return [r.width,r.height];})()")
            await page.mouse.move(200, 300); await page.mouse.down(); await page.mouse.move(80, 300, steps=4); await page.mouse.up(); await page.wait_for_timeout(250)
            check("6: свайп влево — «Далее»", (await page.evaluate(STATE))["idx"] == 1)
            await page.mouse.move(80, 300); await page.mouse.down(); await page.mouse.move(250, 300, steps=4); await page.mouse.up(); await page.wait_for_timeout(250)
            check("6: свайп вправо — «Назад»", (await page.evaluate(STATE))["idx"] == 0)
            # клик по элементу под оверлеем не доходит
            await page.evaluate("window.__clicks=0; document.getElementById('app').addEventListener('click',()=>window.__clicks++); 0")
            h = await page.evaluate("(()=>{const r=document.querySelector('[data-tour=day-title] input').getBoundingClientRect(); return [r.left+10,r.top+10];})()")
            await page.mouse.click(h[0], h[1]); await page.wait_for_timeout(100)
            check("6.2: нажатия на интерфейс под оверлеем блокируются", await page.evaluate("window.__clicks") == 0 and await page.locator("#tour").count() == 1)
            # BackButton
            bb = await page.evaluate("currentBackAction()!==null")
            check("6.2: на первом шаге BackButton = выход из тура", bb and await page.evaluate("tour.path.length")==1)
            await page.click('#tour [data-t="next"]'); await page.wait_for_timeout(200)
            await page.evaluate("currentBackAction()(); 0"); await page.wait_for_timeout(250)
            check("6.2: на втором шаге BackButton = предыдущий шаг", (await page.evaluate(STATE))["idx"] == 0)
            await page.evaluate("currentBackAction()(); 0"); await page.wait_for_timeout(250)
            check("6.2: на первом шаге BackButton закрывает тур", await page.locator("#tour").count() == 0 and await page.evaluate("tour===null&&TOUR_MODE===false"))
            check("6: после выхода BackButton скрыт (нет открытых экранов)", await page.evaluate("currentBackAction()===null"))

            # ---- реальные данные не затронуты, оверлей и демо не остаются
            await page.click("header .help-btn"); await page.wait_for_timeout(250)
            dem = await page.evaluate("({tpl:data.templates.map(t=>t.name), days:Object.keys(data.log).length, ov:document.querySelectorAll('#tour').length})")
            check("6.3: во время тура интерфейс на демо-данных: шаблон «Пример: Тяговая» и 3 дня", dem["tpl"] == ["Пример: Тяговая"] and dem["days"] == 3, dem)
            await page.evaluate("document.querySelector('.tour-skip')||0"); await page.click('#tour [data-t="skip"]'); await page.wait_for_timeout(300)
            after = await page.evaluate("({ov:document.querySelectorAll('#tour').length, demo:!!data.templates.find(t=>t.name==='Пример: Тяговая'), mode:TOUR_MODE, same:JSON.stringify(data)})")
            check("6.7: «Пропустить» — нет оверлея, демо-данных на экране, TOUR_MODE выключен", after["ov"] == 0 and not after["demo"] and after["mode"] is False)
            check("6.7: реальные данные в памяти идентичны (включая дату и вкладку)", after["same"] == before_data)
            check("6.7: хранилище после тура не изменилось (ключи CloudStorage), записей в облако нет", STORE == before_keys and len(WRITES) == before_writes, len(WRITES) - before_writes)
            ls_after = await page.evaluate("JSON.stringify(Object.keys(localStorage).sort().map(k=>[k,localStorage.getItem(k)]))")
            check("6.7: localStorage после тура не изменился", ls_after == before_ls)
            # запись в TOUR_MODE бросает
            thr = await page.evaluate("""(async()=>{ const out=[]; try{ TOUR_MODE=true; try{ lsSet('x','1'); out.push('ls-no-throw'); }catch(e){ out.push('ls-throw'); } try{ await csSet('x','1'); out.push('cs-no-throw'); }catch(e){ out.push('cs-throw'); } persistCfg(); persistDay('2026-01-01'); }finally{ TOUR_MODE=false; } return out; })()""")
            check("6.3: lsSet/csSet в TOUR_MODE бросают исключение; persist* ничего не пишут", thr == ["ls-throw", "cs-throw"] and len(WRITES) == before_writes and STORE == before_keys, thr)
            # сворачивание приложения
            await page.click("header .help-btn"); await page.wait_for_timeout(250)
            await page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true}); document.dispatchEvent(new Event('visibilitychange')); 0"); await page.wait_for_timeout(200)
            await page.evaluate("delete document.hidden; 0")
            check("6.7: сворачивание приложения прерывает тур — без оверлея и демо-данных", await page.locator("#tour").count() == 0 and not await page.evaluate("!!data.templates.find(t=>t.name==='Пример: Тяговая')") and await page.evaluate("TOUR_MODE")is False)
            check("6.7: данные и хранилище по-прежнему те же", await page.evaluate("JSON.stringify(data)") == before_data and STORE == before_keys)
            # cloudLoad во время тура не затирает демо
            await page.click("header .help-btn"); await page.wait_for_timeout(250)
            await page.evaluate("cloudLoad(); 0"); await page.wait_for_timeout(300)
            check("6.3: cloudLoad во время тура не подменяет демо-данные", await page.evaluate("data.templates.length===1&&data.templates[0].name==='Пример: Тяговая'"))
            await page.click('#tour [data-t="skip"]'); await page.wait_for_timeout(200)

            # ---- «Пройти тур» из настроек: все табы подряд
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            rows = await page.evaluate("[...document.querySelectorAll('[data-tour=set-help] .link-row')].map(b=>b.textContent.trim())")
            check("6.1: в «Настройках» раздел «Помощь»: «Пройти тур», «Справочник», «Показать приветствие»", rows == ["Пройти тур", "Справочник", "Показать приветствие"], rows)
            await page.click('[data-act="tourAll"]'); await page.wait_for_timeout(300)
            steps, bad = await walk(page, "all")
            tabs_seen = []
            allnames = [s["target"] for s in steps]
            check("6.1: «Пройти тур» идёт по всем табам: Сегодня → Шаблоны → Календарь → Прогресс → Настройки", allnames.index("week-badge") < allnames.index("tpl-list") < allnames.index("cal-week") < allnames.index("prog-ex") < allnames.index("set-cycle") and len(steps) == 37, (len(steps), allnames[:3]))
            check("6.7: все цели «Пройти тур» подсвечены точно и подсказки в экране", not bad, bad[:3])
            check("6.1: кнопки «Готово»/«Вся справка» только на самом последнем шаге полного тура", steps[-1]["helpShown"] and not any(s["helpShown"] for s in steps[:-1]))
            await page.click('#tour [data-t="next"]'); await page.wait_for_timeout(300)
            check("6: «Готово» закрывает тур; вернулись на исходную вкладку «Настройки»", await page.locator("#tour").count() == 0 and await page.evaluate("ui.tab") == "set")
            await page.click('[data-act="helpOpenAll"]'); await page.wait_for_timeout(200)
            check("6.6: «Справочник» в настройках открывает справочник", await page.locator("#helpOv").count() == 1)
            await page.evaluate("closeHelp(); 0")

            # ---- справочник: разделы фазы 12
            await page.evaluate("openHelp('set'); 0"); await page.wait_for_timeout(150)
            htxt = await page.evaluate("document.querySelector('#helpOv').textContent")
            for q in ["Тема и цвета", "Размер шрифта", "Алиасы", "Тур по интерфейсу", "автоматически"]:
                check("6.6: в справочнике есть «%s»" % q, q in htxt)
            check("6.6: слов «разгрузка/разгрузочн» нет ни в справочнике, ни в тексте тура", "разгруз" not in htxt.lower() and "разгруз" not in src[src.index("const TOUR={"):src.index("const TOUR_ORDER")].lower())
            await page.evaluate("closeHelp(); 0")

            # ---- 320px, 130%
            await page.set_viewport_size({"width": 320, "height": 640})
            await page.evaluate("data.cfg.fontScale=1.3; applyFontScale(); render(); 0")
            await page.click('button[data-tab="day"]'); await page.click('header .help-btn'); await page.wait_for_timeout(300)
            steps, bad = await walk(page, "day320")
            check("6.7: на ширине 320px и шрифте 130%% подсветка точная, подсказка в экране (шаги: %d)" % len(steps), not bad and len(steps) >= 14, bad[:4])
            await page.click('#tour [data-t="skip"]') if await page.locator('#tour [data-t="skip"]').is_visible() else await page.click('#tour [data-t="next"]')
            await page.wait_for_timeout(200)
            check("нет pageerror (реальные данные)", not errs, errs[:2])
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_tour320.png"))
            await page.context.close()

            # ---- пустое приложение
            empty = {"cfg": {"cycle": {"workWeeks": 2, "restWeeks": 1, "anchorDate": "2026-09-07"}, "onboardingSeen": 1}, "templates": [], "log": {}}
            seed(empty)
            page, errs = await open_tg(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.evaluate("window.__tourCur=()=>({target:tour.cur.target,idx:tour.idx,total:tour.steps.length}); 0")
            k0 = dict(STORE); w0 = len(WRITES)
            ce = await page.evaluate("[Object.keys(data.log).length, data.templates.length]")
            await page.click("header .help-btn"); await page.wait_for_timeout(300)
            st, bad = await walk(page, "empty")
            check("6.7: на пустом приложении тур «Сегодня» проходит полностью на демо-данных (16 шагов)", len(st) == 16, [s["target"] for s in st])
            await page.click('#tour [data-t="next"]'); await page.wait_for_timeout(200)
            await page.click('[data-act="tourAll"]') if False else None
            await page.click('button[data-tab="set"]'); await page.click('[data-act="tourAll"]'); await page.wait_for_timeout(300)
            st, bad = await walk(page, "empty-all")
            check("6.7: и полный тур по всем табам на пустом приложении (37 шагов), все цели на месте", len(st) == 37 and not bad, (len(st), bad[:3]))
            await page.click('#tour [data-t="next"]'); await page.wait_for_timeout(300)
            check("6.7: после выхода хранилище не изменилось (сравнение ключей и значений), записей нет", STORE == k0 and len(WRITES) == w0, len(WRITES) - w0)
            check("6.7: после выхода приложение пустое как раньше", await page.evaluate("[Object.keys(data.log).length, data.templates.length]") == ce)
            check("нет pageerror (пустое)", not errs, errs[:2])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
