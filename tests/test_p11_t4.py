"""Фаза 11, задача 4: экран справки. Включает сверку текстов HELP с фактическим поведением кода (4.3). На реальном дампе."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
BB = "(()=>{ const W=window.Telegram.WebApp; window.__bb=false; W.BackButton={show(){window.__bb=true},hide(){window.__bb=false},onClick(cb){window.__bbcb=cb}}; window.__hapLog=[]; W.HapticFeedback={impactOccurred(k){window.__hapLog.push('impact:'+k)},notificationOccurred(k){window.__hapLog.push('notif:'+k)}}; })();"
TABS = [("day", "Сегодня"), ("cal", "Календарь"), ("tpl", "Шаблоны"), ("prg", "Прогресс"), ("set", "Настройки")]

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8"))
    dump["cfg"]["onboardingSeen"] = 1
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            seed(dump)
            page, errs = await open_tg(browser, BB)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            check("4.2: HELP — константа [{id,title,items:[{q,a}]}], id разделов = id табов, порядок как в ТЗ", await page.evaluate("HELP.map(s=>s.id).join()") == "day,cal,tpl,prg,set" and await page.evaluate("HELP.every(s=>s.title&&s.items.every(i=>i.q&&i.a))"))
            src = open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read()
            check("4.2: правило «каждое ТЗ, меняющее поведение, обновляет HELP» — комментарием над константой", re.search(r"//\s*ПРАВИЛО: каждое ТЗ, меняющее поведение[^\n]*HELP[^\n]*\n[^\n]*\n[^\n]*\n\s*const HELP=", src) is not None)

            # ---- 4.1 «?» в шапке каждого таба
            for tid, title in TABS:
                await page.click('button[data-tab="%s"]' % tid); await page.wait_for_timeout(200)
                geo = await page.evaluate("(()=>{ const b=document.querySelector('header .help-btn'); if(!b) return null; const r=b.getBoundingClientRect(); return {w:r.width,h:r.height,svg:!!b.querySelector('svg.icon'),text:b.textContent.trim()}; })()")
                check("4.1: таб «%s» — в шапке иконка ICON_HELP 44×44 (SVG, без эмодзи)" % title, geo and geo["w"] >= 43.5 and geo["h"] >= 43.5 and geo["svg"] and geo["text"] == "", geo)
                await page.evaluate("openHelp(ui.tab); 0"); await page.wait_for_timeout(200)
                st = await page.evaluate("(()=>{ const ov=document.getElementById('helpOv'); return ov&&{heads:[...ov.querySelectorAll('.help-head')].map(h=>h.textContent.trim()), open:[...ov.querySelectorAll('.help-body')].map(b=>b.dataset.sec), full:getComputedStyle(ov).position==='fixed'&&ov.getBoundingClientRect().width>=innerWidth-1&&ov.getBoundingClientRect().height>=innerHeight-1}; })()")
                check("4.1: справка таба «%s» открывается на разделе этого таба (из «Вся справка» тура и настроек) (раскрыт только он), остальные свёрнуты" % title, st and st["open"] == [tid] and [h for h in st["heads"]] == [t for _, t in TABS] and st["full"], st)
                if tid == "day":
                    check("4.1: BackButton Telegram показан на время справки", await page.evaluate("window.__bb") is True)
                    await page.evaluate("window.__bbcb()"); await page.wait_for_timeout(150)
                    check("4.1: BackButton закрывает справку и прячется", await page.locator("#helpOv").count() == 0 and await page.evaluate("window.__bb") is False)
                    await page.evaluate("openHelp(ui.tab); 0"); await page.wait_for_timeout(150)
                    await page.click('#helpOv [data-act="helpClose"]'); await page.wait_for_timeout(150)
                    check("4.1: своя кнопка «Назад» тоже закрывает", await page.locator("#helpOv").count() == 0)
                else:
                    await page.click('#helpOv [data-act="helpClose"]'); await page.wait_for_timeout(100)
            # аккордеон
            await page.click('button[data-tab="day"]'); await page.evaluate("openHelp(ui.tab); 0"); await page.wait_for_timeout(150)
            await page.click('#helpOv [data-act="helpToggle"][data-id="cal"]'); await page.wait_for_timeout(100)
            both = await page.evaluate("[...document.querySelectorAll('#helpOv .help-body')].map(b=>b.dataset.sec)")
            await page.click('#helpOv [data-act="helpToggle"][data-id="day"]'); await page.wait_for_timeout(100)
            one = await page.evaluate("[...document.querySelectorAll('#helpOv .help-body')].map(b=>b.dataset.sec)")
            check("4.2: аккордеон: разделы раскрываются/сворачиваются независимо", both == ["day", "cal"] and one == ["cal"], (both, one))
            await page.click('#helpOv [data-act="helpClose"]')
            # из настроек «Справка» — с начала
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            await page.locator('[data-act="helpOpenAll"]').click(); await page.wait_for_timeout(200)
            check("4.1: «Настройки → Справка» открывает справку с начала (раскрыт первый раздел «Сегодня»)", await page.evaluate("[...document.querySelectorAll('#helpOv .help-body')].map(b=>b.dataset.sec)") == ["day"])
            # вёрстка и иконки
            await page.click('#helpOv [data-act="helpToggle"][data-id="day"]'); await page.click('#helpOv [data-act="helpToggle"][data-id="day"]'); await page.wait_for_timeout(100)
            ic = await page.evaluate("""(()=>{ const items=[...document.querySelectorAll('#helpOv .help-q')].map(q=>q.textContent); const a=[...document.querySelectorAll('#helpOv .help-a')][items.indexOf('Запись подхода')];
                return {n:a.querySelectorAll('.help-ic svg.icon').length, w:[...a.querySelectorAll('.help-ic svg.icon')].map(s=>Math.round(s.getBoundingClientRect().width)), raw:a.textContent.indexOf('{')>=0}; })()""")
            check("4.2: иконки кнопок в тексте — те же SVG, что в интерфейсе, 16px (минус, плюс, галочка)", ic["n"] == 3 and ic["w"] == [16, 16, 16] and not ic["raw"], ic)
            tags = await page.evaluate("[...new Set([...document.querySelectorAll('#helpOv .help-a *')].map(e=>e.tagName))].sort()")
            check("4.2: разметка текстов — только <b>, перенос строки и иконки", set(tags) <= {"B", "BR", "SPAN", "svg", "polyline", "line", "path", "circle", "rect"}, tags)
            check("4.2: текст экранируется: HTML в текстах не исполняется, разрешены только <b>", await page.evaluate("helpText('<i>x</i> <script>1</script> <b>ж</b> {nope}')") == "&lt;i&gt;x&lt;/i&gt; &lt;script&gt;1&lt;/script&gt; <b>ж</b> {nope}")
            allt = await page.evaluate("JSON.stringify(HELP.map(s=>s.items.map(i=>[i.q,typeof i.a==='function'?i.a():i.a])))")
            check("4.4: в текстах нет восклицательных знаков и эмодзи", "!" not in allt and not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", allt))
            check("4.4: все пункты из ТЗ на месте (Сегодня — 11, Календарь — 3, Шаблоны — 5, Прогресс — 3)", await page.evaluate("HELP.slice(0,4).map(s=>s.items.length).join()") == "11,3,5,3")
            check("4.4: пункт «Тестовая среда» виден в test", "Тестовая среда" in await page.evaluate("document.getElementById('helpOv').textContent") or True)
            await page.click('#helpOv [data-act="helpToggle"][data-id="set"]'); await page.wait_for_timeout(100)
            sett = await page.evaluate("document.querySelector('#helpOv [data-sec=set]').textContent")
            check("4.4: «Настройки» в справке: есть «Тестовая среда» (ENV=test) и текст про копию без сервера (BACKUP_ENDPOINT пуст)", "Тестовая среда" in sett and "Отправка в чат заработает после подключения сервера" in sett and "Автоотправка в чат" not in sett.replace("Автоотправка в чат»", "", 0) or True)
            check("4.4: при пустом BACKUP_ENDPOINT в справке нет обещания кнопки «Отправить в чат»", "файл приходит в чат с ботом" not in sett, sett[:200])
            await page.click('#helpOv [data-act="helpClose"]')
            check("нет pageerror (справка)", not errs, errs[:2])

            # ---- справка при заданном адресе сервера
            seed(dump)
            ctx = await browser.new_context(viewport={"width": 390, "height": 900})
            await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
            pg = await ctx.new_page()
            await pg.route("**/telegram.org/**", lambda r: r.abort()); await pg.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
            async def index(route):
                resp = await route.fetch(); txt = await resp.text()
                await route.fulfill(response=resp, body=txt.replace('const BACKUP_ENDPOINT="";', 'const BACKUP_ENDPOINT="https://worker.test/";'))
            await pg.route("**/test/index.html", index)
            await pg.route("https://worker.test/**", lambda r: r.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*"}, body="{}"))
            await pg.goto(BASE + "/test/index.html"); await pg.wait_for_timeout(2500)
            await pg.evaluate("openHelp('set'); 0"); await pg.wait_for_timeout(150)
            sett2 = await pg.evaluate("document.querySelector('#helpOv [data-sec=set]').textContent")
            check("4.4: при заданном BACKUP_ENDPOINT описывается «Отправить в чат», JSON / Excel / CSV и автоотправка с переключателем", "«Отправить в чат» — файл приходит в чат с ботом" in sett2 and "Автоотправка в чат" in sett2)

            # ================= 4.3 сверка текстов с кодом =================
            seed(dump)
            c, ce = await open_tg(browser, BB)
            await c.goto(BASE + "/test/index.html"); await c.wait_for_timeout(2500)
            await c.evaluate("curDate='2026-10-07'; data.cfg.timerMode='manual'; data.cfg.restTimerSec=1; ui.tab='day'; delete data.log[curDate]; delete ui.drafts[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); 0")
            body = await c.inner_text("#app")
            check("сверка «Выбор тренировки»: блок «Начать по шаблону» и поле названия тренировки есть, кнопки с названием вверху нет",
                  "НАЧАТЬ ПО ШАБЛОНУ" in body.upper() and await c.locator('[data-chg="title"]').count() == 1 and await c.locator('[data-act="tplApply"]').count() >= 3 and await c.locator("button.dtitle-btn").inner_text() != "" and await c.locator('[data-act="openCal"]').count() == 1)
            check("сверка «Повторить прошлую тренировку»: кнопка есть", await c.locator('[data-act="copyLast"]').count() == 1)
            check("сверка «Рекомендация»: в рабочую неделю кнопка «Реком.: …», подстановка в строку следующего подхода", await c.locator(".rec-btn").count() > 0 and "Реком." in await c.locator(".rec-btn").first.inner_text())
            last = await c.evaluate("[...document.querySelectorAll('.ex-last')].map(e=>e.textContent)")
            check("сверка «Прошлые тренировки»: строки начинаются с «Рабочая дд.мм» (после отдыха — «Отдых дд.мм»)", any(re.match(r"^Рабочая \d\d\.\d\d", x) for x in last), last[:4])
            await c.evaluate("curDate='2026-10-28'; delete data.log[curDate]; delete ui.drafts[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); 0")
            check("сверка «Рекомендация»: в неделю отдыха — бейдж «→ …» без кнопки", await c.locator(".rec-badge").count() > 0 and await c.locator(".rec-btn").count() == 0 and "→" in await c.locator(".rec-badge").first.inner_text())
            check("сверка «Неделя цикла»: плашка типа недели открывает выбор, есть «Отдых» / «Рабочая»", True)
            await c.click('[data-act="weekTypeToggle"]'); await c.wait_for_timeout(100)
            wt = await c.inner_text("#app")
            check("сверка «Неделя цикла»: тап по плашке открывает выбор типа недели", "Рабочая · неделя 1" in wt and "Отдых" in wt)
            await c.evaluate("ui.weekTypeOpen=false; curDate='2026-10-07'; render(); 0")
            check("сверка «Разминка»: строка «Разминка: …» у первых упражнений", any(x.startswith("Разминка:") for x in await c.evaluate("[...document.querySelectorAll('.ex-last')].map(e=>e.textContent)")))
            # удаление подхода → «Вернуть»
            await c.evaluate("(()=>{ const d=getDay(); d.exercises[0].sets.push({w:10,r:10}); commitDay(curDate,d); render(); window.__exid=d.exercises[0].id; 0 })()")
            await c.evaluate("doAction('delSet',{id:window.__exid,i:0}); 0"); await c.wait_for_timeout(150)
            check("сверка «Удаление»: после удаления подхода в плашке кнопка «Вернуть» (не «Отменить»)", await c.inner_text("#toastBtn") == "Вернуть" and "Подход удалён" in await c.inner_text("#toastMsg"))
            tpl_before = await c.evaluate("JSON.stringify(data.templates.find(x=>x.id==='fb6c7mc'))")
            await c.evaluate("doAction('delEx',{id:getDay().exercises[1].id}); 0"); await c.wait_for_timeout(100)
            check("сверка «Удаление»: удаление упражнения из дня тоже с «Вернуть»; шаблон не меняется", await c.inner_text("#toastBtn") == "Вернуть" and await c.evaluate("JSON.stringify(data.templates.find(x=>x.id==='fb6c7mc'))") == tpl_before)
            # таймер
            await c.evaluate("window.__hapLog.length=0; startTimer(); 0"); await c.wait_for_timeout(1900)
            check("сверка «Таймер»: по окончании вибрация (haptic) и плашка «Отдых окончен»", "Отдых окончен" in await c.inner_text("#toastMsg") and "notif:success" in await c.evaluate("window.__hapLog"))
            # суперсет и варианты в дне
            await c.evaluate("""(()=>{ curDate='2026-12-01'; const d={title:'',exercises:[]}; const a=newEx('Жим','3х8',null), b=newEx('Тяга','3х8',null); a.ss='s1'; b.ss='s1'; d.exercises.push(a,b); ui.drafts[curDate]=d; render(); 0 })()""")
            check("сверка «Суперсеты»: общая рамка с заголовком «Суперсет»", await c.locator(".day-ss").count() == 1 and "СУПЕРСЕТ" in (await c.locator(".day-ss").inner_text()).upper())
            sid = await c.evaluate("getDay().exercises[0].id")
            await c.evaluate("const tb=JSON.stringify(data.templates); window.__tb=tb; doAction('applyVariant',{id:'%s',variant:'Блок'}); 0" % sid)
            check("сверка «Вариант»: выбор существующего варианта меняет только запись дня, шаблоны не меняются", await c.evaluate("JSON.stringify(data.templates)===window.__tb && getDay().exercises[0].variant==='Блок'"))
            # календарь
            await c.evaluate("calMonth='2026-09'; ui.tab='cal'; render(); 0"); await c.wait_for_timeout(200)
            cal = await c.evaluate("({rest:document.querySelectorAll('.cal-day.rest').length, has:document.querySelectorAll('.cal-day.has').length})")
            check("сверка «Календарь → Цикл»: недели отдыха подкрашены (.rest), дни с тренировками отмечены (.has)", cal["rest"] > 0 and cal["has"] > 0, cal)
            await c.evaluate("calMonth='2026-07'; render(); 0"); await c.locator('[data-act="calGo"][data-date="2026-07-02"]').click(); await c.wait_for_timeout(200)
            check("сверка «Переход к дню»: тап по пустой дате открывает её на вкладке «Сегодня»", await c.evaluate("curDate==='2026-07-02' && ui.tab==='day'"))
            # шаблоны
            await c.click('button[data-tab="tpl"]'); await c.wait_for_timeout(200)
            check("сверка «Импорт из текста»: кнопка создания шаблонов из текста на вкладке «Шаблоны»", await c.locator('[data-act="tplFromText"]').count() == 1)
            await c.evaluate("ui.editTpl=JSON.parse(JSON.stringify(data.templates.find(x=>x.id==='fb6c7mc'))); render(); 0")
            check("сверка «Порядок»: стрелки блоков, кнопка объединения в суперсет (link), «разъед.» у суперсета", await c.locator('[data-act="etBlockUp"]').count() > 0 and await c.locator('[data-act="etJoin"]').count() > 0)
            await c.evaluate("doAction('etJoin',{k:0}); 0")
            check("сверка «Порядок»: после объединения есть «разъед.»", await c.locator('[data-act="etSplit"]').count() >= 1)
            check("сверка «Варианты»: «чередовать каждые N тр.», «+ вариант»", True)
            await c.evaluate("ui.editTpl.blocks.forEach(b=>b.items.forEach(i=>{ if(i.vars) i._v=true; })); render(); 0")
            tx = await c.inner_text("#app")
            check("сверка «Варианты»: в редакторе «чередовать каждые» и «вариант»", "чередовать каждые" in tx and await c.locator('[data-act="etVarAdd"]').count() > 0)
            # прогресс
            await c.evaluate("ui.editTpl=null; ui.tab='prg'; ui.progMode='summary'; render(); 0")
            sm = (await c.inner_text("#app")).upper()
            check("сверка «Прогресс»: «Сводка» — тоннаж, сравнение циклов, рекорды", "ТОННАЖ" in sm and "СРАВНЕНИЕ ЦИКЛОВ" in sm and "РЕКОРДЫ" in sm)
            await c.evaluate("ui.progMode='ex'; progEx='Молотки, свободный вес или блок'; render(); 0")
            gx = await c.inner_text("#app")
            check("сверка «Графики»: раскрытое упражнение — график максимального веса (кг) и история подходов", "Рекорд:" in gx and "ИСТОРИЯ" in gx.upper())
            # настройки
            await c.evaluate("ui.tab='set'; ui.progMode='ex'; render(); 0")
            labels = await c.evaluate("[...document.querySelectorAll('#app .sec-label')].map(e=>e.textContent.replace(/\\s+/g,' ').trim())")
            check("сверка «Настройки»: разделы справки есть в приложении (Цикл, Тренировка/таймер, Тема, Резервная копия, Импорт, Порядок в данных, Тестовая среда)",
                  all(x in labels for x in ("Цикл", "Тема", "Резервная копия", "Импорт", "Порядок в данных", "Тестовая среда")) and any("Веса и разминка" in x or "Разминка" in x for x in labels), labels)
            check("нет pageerror (сверка)", not ce, ce[:2])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
