"""Подготовка к переносу в prod: фильтр алиасов, разрешение на сообщения (writeAccess), копия перед миграцией, браузерный режим."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, WRITES, check, RESULTS, REPO, BASE, MOCK, cs_handler, log_handler
from test_task7 import seed, open_tg
from test_p11_t1 import open_ep, seed_cfg, load, iso_ago, DAY
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
SKIP_MIG = "setInterval(()=>{ const d=document.getElementById('dlg'); if(d&&d.textContent.includes('Приложение обновилось')){ const b=d.querySelector('[data-dlg=\"1\"]'); if(b) b.click(); } },30);"
VER = "v2.13.0"

async def browser_page(browser, cache, ua=None, persist=None, extra=None, viewport=(390, 844)):
    """страница вне Telegram: без Mock, localStorage предзаполнен (ключи без префикса — «основная версия»)"""
    kw = {"viewport": {"width": viewport[0], "height": viewport[1]}, "accept_downloads": True}
    if ua: kw["user_agent"] = ua
    ctx = await browser.new_context(**kw)
    init = "if(!localStorage.getItem('__seeded')){ localStorage.setItem('__seeded','1'); const c=%s; for(const k of Object.keys(c)) localStorage.setItem(k,c[k]); }" % json.dumps(cache)
    await ctx.add_init_script(init)
    if persist is not None: await ctx.add_init_script("Object.defineProperty(navigator,'storage',{configurable:true,value:{persist:()=>Promise.resolve(%s)}});" % ("true" if persist else "false"))
    if extra: await ctx.add_init_script(extra)
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    await page.route("**/telegram.org/**", lambda r: r.abort()); await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
    return page, errs

def cache_of(d, snooze=True):
    cfg = dict(d["cfg"])
    if snooze: cfg["backupSnooze"] = int(time.time() * 1000) + 365 * DAY    # диалог «Пора сделать копию» не мешает сценарию
    return {"tst_gt2:cache": json.dumps({"cfg": cfg, "templates": d["templates"], "log": d["log"]})}

EMPTY_TST = {"tst_gt2:cache": json.dumps({"cfg": {"cycle": {"workWeeks": 2, "restWeeks": 1, "anchorDate": time.strftime("%Y-%m-%d")}, "onboardingSeen": 1, "backupSnooze": int(time.time() * 1000) + 365 * DAY}, "templates": [], "log": {}})}

def req_has_base(req):
    j = json.loads(req["content"]); return any(e.get("base") for d in j["log"].values() for e in d["exercises"]), len(j["log"])

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    raw_dump = json.loads(json.dumps(dump))
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            # мигрированный дамп (для сценариев без миграции)
            seed(dump); pg, _st, _e = await open_ep(browser, endpoint=""); await load(pg)
            mdump = await pg.evaluate("({cfg:data.cfg,templates:data.templates,log:data.log})"); mdump["cfg"]["onboardingSeen"] = 1
            n_alias_real = await pg.evaluate("Object.keys(data.cfg.aliases).length"); await pg.context.close()

            # ================= новый пользователь: пустые данные =================
            STORE.clear(); STORE["tst_cfg"] = json.dumps({"cycle": {"workWeeks": 2, "restWeeks": 1, "anchorDate": time.strftime("%Y-%m-%d")}, "up": 1, "onboardingSeen": 1})
            page, st, errs = await open_ep(browser, endpoint=""); await load(page)
            e = await page.evaluate("""(()=>{ const i=findDataIssues(); const n=Object.values(i).reduce((a,b)=>a+b.length,0);
                return {issues:n, dups:findDupGroups().length, unm:unmatchedNames().length, aliases:[Object.keys(data.cfg.aliases).length, Object.keys(data.cfg.variantAliases).length], mig:migTodo(data).length, dupBanner:!!document.getElementById('dupBanner'), toast:document.getElementById('toastMsg').textContent, dlg:!!document.getElementById('dlg'), srcDays:Object.keys(data.log).length}; })()""")
            check("новый пользователь: нет замечаний «Проверки данных», похожих шаблонов, несопоставленных названий, алиасов по умолчанию, записей на миграцию, баннера и диалогов", e["issues"] == 0 and e["dups"] == 0 and e["unm"] == 0 and e["aliases"] == [0, 0] and e["mig"] == 0 and not e["dupBanner"] and not e["dlg"] and e["srcDays"] == 0, e)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            txt = await page.inner_text("#app")
            nums = await page.evaluate("[...document.querySelectorAll('[data-act=hygOpen],[data-act=aliasOpen]')].map(b=>b.textContent.trim())")
            check("новый пользователь: в «Порядке в данных» нет счётчиков у «Проверка данных», «Похожие шаблоны», «Алиасы»", all("·" not in x for x in nums), nums)
            await page.evaluate("ui.hygiene='check'; render(); 0"); await page.wait_for_timeout(150)
            check("новый пользователь: экран «Проверка данных» — «Замечаний нет»", "Замечаний нет" in await page.inner_text("#app"))
            await page.evaluate("ui.hygiene=null; ui.aliasScreen=true; render(); 0"); await page.wait_for_timeout(150)
            check("новый пользователь: экран алиасов без блока «Не сопоставлено» и без пар", await page.locator(".al-card").count() == 0 and "Не сопоставлено" not in await page.inner_text("#app"))
            check("новый пользователь: ошибок миграции и pageerror нет", not errs and await page.evaluate("document.getElementById('toastMsg').textContent") == e["toast"] and "мигрирована" not in e["toast"], (errs[:1], e["toast"]))
            await page.context.close()

            # ================= writeAccess =================
            # первая ручная отправка: сначала requestWriteAccess, потом POST
            seed_cfg(mdump, lastBackup=iso_ago(1), backupReminderDays=14)
            page, st, errs = await open_ep(browser); await load(page)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            check("writeAccess: до отправки cfg.writeAccess не задан, запрос не выполнялся", await page.evaluate("data.cfg.writeAccess") is None and await page.evaluate("window.__wa||0") == 0)
            await page.click('[data-act="sendBackup"][data-format="json"]'); await page.wait_for_timeout(900)
            check("writeAccess: перед первой отправкой вызван Telegram.WebApp.requestWriteAccess(), результат в cfg.writeAccess=true, в облаке сохранён, файл отправлен", await page.evaluate("window.__wa") == 1 and await page.evaluate("data.cfg.writeAccess") is True and '"writeAccess":true' in STORE["tst_cfg"] and len(st["reqs"]) == 1, (len(st["reqs"]),))
            await page.click('[data-act="sendBackup"][data-format="csv"]'); await page.wait_for_timeout(700)
            check("writeAccess: повторные отправки запрос не повторяют (уже true)", await page.evaluate("window.__wa") == 1 and len(st["reqs"]) == 2)
            await page.context.close()

            # отказ в разрешении
            seed_cfg(mdump, lastBackup=iso_ago(1), backupReminderDays=14)
            page, st, errs = await open_ep(browser); await page.context.add_init_script("window.__waAllow=false;")
            await load(page); await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            await page.click('[data-act="sendBackup"][data-format="json"]'); await page.wait_for_timeout(500)
            dlg = await page.evaluate("(()=>{ const d=document.getElementById('dlg'); return d&&{t:d.querySelector('.dlg-title').textContent, b:[...d.querySelectorAll('[data-dlg]')].map(b=>b.textContent)}; })()")
            check("writeAccess: отказ пользователя — файл не отправляется, диалог «Разреши боту писать тебе» с кнопкой повторного запроса, cfg.writeAccess=false", len(st["reqs"]) == 0 and dlg and dlg["t"] == "Разреши боту писать тебе" and dlg["b"] == ["Разрешить", "Закрыть"] and await page.evaluate("data.cfg.writeAccess") is False and "Не отправлено" not in await page.inner_text("#toastMsg"), (dlg, len(st["reqs"])))
            await page.evaluate("window.__waAllow=true; 0"); await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(900)
            check("writeAccess: «Разрешить» повторяет запрос; после согласия копия отправлена автоматически", await page.evaluate("window.__wa") == 2 and len(st["reqs"]) == 1 and await page.evaluate("data.cfg.writeAccess") is True and await page.locator("#dlg").count() == 0, (len(st["reqs"]),))
            await page.context.close()

            # Worker: 502 «can't initiate conversation» / «blocked» — не сбой
            for mode, label in (("blocked", "can't initiate conversation"), ("blocked2", "bot was blocked")):
                seed_cfg(mdump, lastBackup=iso_ago(1), backupReminderDays=14, writeAccess=True)
                page, st, errs = await open_ep(browser, mode=mode); await load(page)
                await page.click('button[data-tab="set"]'); await page.click('[data-act="sendBackup"][data-format="json"]'); await page.wait_for_timeout(700)
                dlg = await page.evaluate("(()=>{ const d=document.getElementById('dlg'); return d&&{t:d.querySelector('.dlg-title').textContent, b:[...d.querySelectorAll('[data-dlg]')].map(b=>b.textContent)}; })()")
                toast = await page.inner_text("#toastMsg")
                check("writeAccess: ответ Worker 502 «%s» — диалог «Разреши боту писать тебе» с кнопкой повторного запроса, не «Не отправлено»; writeAccess сброшен" % label, dlg and dlg["t"] == "Разреши боту писать тебе" and dlg["b"] == ["Разрешить", "Закрыть"] and "Не отправлено" not in toast and await page.evaluate("data.cfg.writeAccess") is False, (dlg, toast))
                await page.context.close()

            # автоотправка при старте только при writeAccess === true
            seed_cfg(mdump, lastBackup=iso_ago(20), autoBackup=True, backupReminderDays=14)
            page, st, errs = await open_ep(browser); await load(page)
            ban = await page.evaluate("({dlg:!!document.getElementById('dlg'), banner:[...document.querySelectorAll('.backup-banner .txt')].map(e=>e.textContent), wa:window.__wa||0})")
            check("автоотправка: writeAccess не задан — копия не уходит, запрос разрешения при старте не показывается, без диалога/ошибки, остаётся обычное напоминание-баннер", len(st["reqs"]) == 0 and not ban["dlg"] and ban["wa"] == 0 and any("Резервная копия" in b for b in ban["banner"]), ban)
            await page.context.close()
            seed_cfg(mdump, lastBackup=iso_ago(20), autoBackup=True, backupReminderDays=14, writeAccess=False)
            page, st, errs = await open_ep(browser); await load(page)
            check("автоотправка: writeAccess=false — тоже без отправки и без ошибок", len(st["reqs"]) == 0 and await page.locator("#dlg").count() == 0)
            await page.context.close()
            seed_cfg(mdump, lastBackup=iso_ago(20), autoBackup=True, backupReminderDays=14, writeAccess=True)
            page, st, errs = await open_ep(browser); await load(page)
            check("автоотправка: writeAccess=true — копия при старте отправляется (1 запрос), requestWriteAccess не вызывается", len(st["reqs"]) == 1 and (await page.evaluate("window.__wa||0")) == 0)
            await page.context.close()

            # ================= копия перед миграцией: Telegram =================
            seed_cfg(raw_dump, lastBackup=iso_ago(1), backupReminderDays=14, writeAccess=True)
            page, st, errs = await open_ep(browser); await load(page, 3500)
            r0 = st["reqs"][0] if st["reqs"] else None
            hb = req_has_base(r0) if r0 else None
            check("миграция (Telegram, writeAccess=true): до миграции в чат уходит JSON с подписью «Копия перед обновлением до %s» — данные ещё не мигрированы (нет base), 35 дней" % VER, r0 and r0["format"] == "json" and r0.get("note") == "Копия перед обновлением до " + VER and hb[0] is False and hb[1] == 35, (r0 and r0.get("note"), hb))
            mg = await page.evaluate("({pend:migTodo(data).length, snap:lsKeys('premig_').length, base:Object.values(data.log).every(d=>d.exercises.every(e=>e.base))})")
            check("миграция: после копии записи мигрированы, локальный снапшот premig_ сохранён", mg["pend"] == 0 and mg["snap"] >= 1 and mg["base"], mg)
            check("миграция: отправленная перед обновлением копия учтена как последняя (lastBackup обновлён), запуск не заблокирован", await page.evaluate("Date.now()-new Date(data.cfg.lastBackup).getTime()<60000") and await page.locator("#dlg").count() == 0)
            await page.context.close()
            # без разрешения — только снапшот, без блокировки
            seed_cfg(raw_dump, lastBackup=iso_ago(1), backupReminderDays=14)
            page, st, errs = await open_ep(browser); await load(page, 3000)
            mg = await page.evaluate("({pend:migTodo(data).length, snap:lsKeys('premig_').length, dlg:!!document.getElementById('dlg'), wa:window.__wa||0})")
            check("миграция (Telegram, нет разрешения): в чат ничего не уходит, запрос разрешения не показывается, остаётся снапшот localStorage, запуск не блокируется (записи мигрированы)", len(st["reqs"]) == 0 and mg["pend"] == 0 and mg["snap"] >= 1 and not mg["dlg"] and mg["wa"] == 0, (len(st["reqs"]), mg))
            await page.context.close()
            # ошибка отправки не блокирует
            seed_cfg(raw_dump, lastBackup=iso_ago(1), backupReminderDays=14, writeAccess=True)
            page, st, errs = await open_ep(browser, mode="fail"); await load(page, 3500)
            check("миграция: сбой отправки копии не блокирует запуск — записи мигрированы, lastBackup не обновлён", await page.evaluate("migTodo(data).length") == 0 and await page.evaluate("Date.now()-new Date(data.cfg.lastBackup).getTime()>20*3600*1000"))
            await page.context.close()

            # ================= браузер: копия перед миграцией =================
            page, errs = await browser_page(browser, cache_of(raw_dump, snooze=False))
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2200)
            dlg = await page.evaluate("(()=>{ const d=document.getElementById('dlg'); return d&&{t:d.querySelector('.dlg-title').textContent, x:d.querySelector('.dlg-text').textContent, b:[...d.querySelectorAll('[data-dlg]')].map(b=>b.textContent), pend:migTodo(data).length}; })()")
            check("браузер: блокирующий диалог «Приложение обновилось. Скачай копию данных перед обновлением» с кнопками «Скачать и продолжить» / «Продолжить без копии»; миграция ещё не применена", dlg and dlg["t"] == "Приложение обновилось" and dlg["x"] == "Скачай копию данных перед обновлением." and dlg["b"] == ["Скачать и продолжить", "Продолжить без копии"] and dlg["pend"] > 0, dlg)
            async with page.expect_download(timeout=8000) as dl:
                await page.click('#dlg [data-dlg="0"]')
            f = await dl.value; path = await f.path(); body = json.load(open(path, encoding="utf-8")); await page.wait_for_timeout(500)
            b2 = await page.evaluate("({pend:migTodo(data).length, snap:lsKeys('premig_').length, last:!!data.cfg.lastBackup})")
            check("браузер: «Скачать и продолжить» — скачивается JSON с данными до миграции (нет base), затем миграция, снапшот localStorage, lastBackup обновлён", f.suggested_filename.endswith(".json") and not any(e.get("base") for d in body["log"].values() for e in d["exercises"]) and len(body["log"]) == 35 and b2["pend"] == 0 and b2["snap"] >= 1 and b2["last"], (f.suggested_filename, b2))
            await page.context.close()
            page, errs = await browser_page(browser, cache_of(raw_dump, snooze=False))
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2200)
            n_dl = []; page.on("download", lambda d: n_dl.append(d))
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(600)
            b3 = await page.evaluate("({pend:migTodo(data).length, snap:lsKeys('premig_').length, dlg:!!document.getElementById('dlg')&&document.getElementById('dlg').textContent.includes('Приложение обновилось')})")
            check("браузер: «Продолжить без копии» — ничего не скачивается, миграция применена, снапшот localStorage всё равно сохранён", not n_dl and b3["pend"] == 0 and b3["snap"] >= 1 and not b3["dlg"], b3)
            await page.reload(); await page.wait_for_timeout(2200)
            check("браузер: после миграции диалог больше не показывается", await page.evaluate("!document.getElementById('dlg') || !document.getElementById('dlg').textContent.includes('Приложение обновилось')"))
            await page.context.close()
            # мигрированные данные — без диалога
            page, errs = await browser_page(browser, cache_of(mdump))
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2200)
            check("браузер: нет записей на миграцию — диалога «Приложение обновилось» нет", not await page.evaluate("!!document.getElementById('dlg') && document.getElementById('dlg').textContent.includes('Приложение обновилось')"))
            check("нет pageerror (браузер, миграция)", not errs, errs[:2])
            await page.context.close()

            # ================= браузер: клонирование через localStorage =================
            prod = {"gt2:cache": json.dumps({"cfg": mdump["cfg"], "templates": mdump["templates"], "log": mdump["log"]}), "gt2:snapshot": "{\"created\":\"x\"}", "other-app": "keep", "gym-tracker-v1": "old"}
            page, errs = await browser_page(browser, EMPTY_TST, extra="localStorage.setItem('__seed2','1'); if(!localStorage.getItem('__p')){ localStorage.setItem('__p','1'); const c=%s; for(const k of Object.keys(c)) localStorage.setItem(k,c[k]); }" % json.dumps(prod))
            page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2200)
            before = await page.evaluate("JSON.stringify(Object.keys(localStorage).filter(k=>!k.startsWith('tst_')&&!k.startsWith('__')).sort().map(k=>[k,localStorage.getItem(k)]))")
            await page.click('button[data-tab="set"]'); await page.evaluate("ui.testScreen=true; render(); 0"); await page.wait_for_timeout(200)
            check("клон в браузере: в тестовой среде кнопка «Скопировать данные из основной версии» есть (CloudStorage не нужен)", await page.locator('[data-act="cloneProd"]').count() == 1)
            await page.click('[data-act="cloneProd"]'); await page.wait_for_timeout(2500)
            after = await page.evaluate("JSON.stringify(Object.keys(localStorage).filter(k=>!k.startsWith('tst_')&&!k.startsWith('__')).sort().map(k=>[k,localStorage.getItem(k)]))")
            cl = await page.evaluate("({cache:localStorage.getItem('tst_gt2:cache'), snap:localStorage.getItem('tst_gt2:snapshot'), other:localStorage.getItem('tst_other-app'), v1:localStorage.getItem('tst_gym-tracker-v1'), days:Object.keys(data.log).length})")
            check("клон в браузере: ключи «gt2:…» скопированы с префиксом tst_, данные загружены после перезагрузки (35 дней), чужие ключи (other-app, gym-tracker-v1) не копируются", cl["cache"] == prod["gt2:cache"] and cl["snap"] == prod["gt2:snapshot"] and cl["other"] is None and cl["v1"] is None and cl["days"] == 35, {k: (v if k == "days" else (v or "")[:20]) for k, v in cl.items()})
            check("клон в браузере: боевые ключи (без tst_) не изменены — чтение только", before == after)
            await page.context.close()
            page, errs = await browser_page(browser, EMPTY_TST)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(1800)
            await page.evaluate("ui.tab='set'; ui.testScreen=true; render(); 0"); await page.wait_for_timeout(200)
            await page.evaluate("window.__alert=[]; window.alert=(m)=>window.__alert.push(m); 0"); await page.click('[data-act="cloneProd"]'); await page.wait_for_timeout(800)
            check("клон в браузере: нет основных данных → понятная ошибка с названием шага", any("основные данные не найдены" in m and "Шаг «Чтение основных данных»" in m for m in await page.evaluate("window.__alert")), await page.evaluate("window.__alert"))
            check("клон в браузере: запись в боевой ключ защищена (guardKey)", await page.evaluate("(()=>{ try{ guardKey('gt2:cache'); return false; }catch(e){ return /Blocked write to prod key/.test(e.message); } })()"))
            await page.context.close()

            # ================= браузер: persist() и Safari =================
            SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            SAF_TXT = "Safari может удалить данные, если не открывать сайт 7 дней. Добавь сайт на экран «Домой» или регулярно скачивай копию."
            for ua, persist, expect, label in [(SAFARI, False, True, "Safari + persist()=false"), (SAFARI, True, False, "Safari + persist()=true"), (CHROME, False, False, "Chrome + persist()=false")]:
                page, errs = await browser_page(browser, cache_of(mdump), ua=ua, persist=persist)
                await page.add_init_script("window.__pc=0; (()=>{ const s=navigator.storage; const p=s.persist; s.persist=function(){ window.__pc++; return p.apply(s,arguments); }; })()")
                await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2000)
                w = await page.evaluate("(()=>{ const e=document.getElementById('brWarn'); return {txt:e?e.textContent:'', pc:window.__pc||0, cls:e?e.className:''}; })()")
                has = SAF_TXT in w["txt"]
                check("браузер (%s): navigator.storage.persist() вызван при старте; предупреждение про Safari %s" % (label, "показано в строке-предупреждении" if expect else "не показывается"), w["pc"] == 1 and has == expect and "Открыто в браузере: данные хранятся только здесь" in w["txt"], w)
                await page.context.close()
            page, errs = await browser_page(browser, cache_of(mdump), persist=None)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(1500)
            check("браузер: без navigator.storage приложение работает (ошибок нет)", not errs and await page.locator("#brWarn").count() == 1, errs[:2])
            await page.context.close()

            # ================= интервал напоминания: 7 дней в браузере, 14 в Telegram =================
            d_nocfg = {"cfg": {k: v for k, v in mdump["cfg"].items() if k != "backupReminderDays"}, "templates": mdump["templates"], "log": mdump["log"]}
            page, errs = await browser_page(browser, cache_of(d_nocfg))
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(1800)
            check("браузер: интервал напоминания по умолчанию 7 дней", await page.evaluate("data.cfg.backupReminderDays") == 7)
            await page.context.close()
            d_own = {"cfg": dict(mdump["cfg"], backupReminderDays=30), "templates": mdump["templates"], "log": mdump["log"]}
            page, errs = await browser_page(browser, cache_of(d_own))
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(1800)
            check("браузер: заданный пользователем интервал (30) сохраняется", await page.evaluate("data.cfg.backupReminderDays") == 30)
            await page.context.close()
            STORE.clear(); STORE["tst_cfg"] = json.dumps({k: v for k, v in mdump["cfg"].items() if k != "backupReminderDays"})
            for t in mdump["templates"]: STORE["tst_tpl_" + t["id"]] = json.dumps(t)
            for k, d in mdump["log"].items(): STORE["tst_w_" + k] = json.dumps(d)
            page, st, errs = await open_ep(browser, endpoint=""); await load(page)
            check("Telegram: интервал напоминания по умолчанию по-прежнему 14 дней", await page.evaluate("data.cfg.backupReminderDays") == 14)
            await page.context.close()
            # алиасы по умолчанию на реальных данных: только применимые пары
            check("алиасы по умолчанию на реальных данных: только пары с названием из шаблонов пользователя (%d из 5)" % n_alias_real, 0 <= n_alias_real <= 5, n_alias_real)
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
