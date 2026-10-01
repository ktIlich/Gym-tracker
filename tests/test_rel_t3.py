"""Релиз/prod, задача 3: мастер — только для физически пустого хранилища; LOAD_OK; сбои чтения → экран ошибки, без записей."""
import asyncio, copy, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, WRITES, check, RESULTS, REPO, BASE, SEEN_JS, MOCK, cs_handler, log_handler
from test_task7 import seed, open_tg
from test_p11_t1 import seed_cfg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
URL = BASE + "/test/index.html"
ERR_TXT = "Не удалось загрузить данные. Они не удалены — ничего не нажимай, кроме кнопок ниже."

FAILWRAP = """(()=>{ const CS=window.Telegram.WebApp.CloudStorage; const gk=CS.getKeys, gi=CS.getItems; window.__fail=window.__fail||{keys:false,items:false,hang:false};
  CS.getKeys=cb=>{ if(window.__fail.hang) return; if(window.__fail.keys) return cb('BOOM_KEYS'); return gk.call(CS,cb); };
  CS.getItems=(k,cb)=>{ if(window.__fail.items) return cb('BOOM_ITEMS'); return gi.call(CS,k,cb); }; })();"""

BREAK_ROUTE_JS = lambda txt: txt.replace("function normalizeData(d){", "function normalizeData(d){ if(window.__breakParse) throw new Error('BOOM_PARSE');", 1)

async def tg_page(browser, init=None, break_parse=False):
    page, errs = await open_tg(browser)
    await page.context.add_init_script(FAILWRAP)
    if init: await page.context.add_init_script(init)
    if break_parse:
        async def index(route):
            resp = await route.fetch(); await route.fulfill(response=resp, body=BREAK_ROUTE_JS(await resp.text()))
        await page.route(re.compile(r".*/test/index\.html(\?.*)?$"), index)
    return page, errs

def snap(): return copy.deepcopy(STORE)

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            src = open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read()
            check("3.3: флаг LOAD_OK; guardKey бросает исключение для записи данных до загрузки (служебные ключи — исключение)", "let LOAD_OK=false" in src and "Запись заблокирована: данные ещё не загружены" in src)

            # ---------- 3.1 Telegram: хранилище пустое → мастер, запись разрешена
            STORE.clear()
            page, errs = await tg_page(browser); await page.goto(URL); await page.wait_for_timeout(2500)
            st = await page.evaluate("({ok:LOAD_OK, wiz:!!document.querySelector('.setup .btn-main, .setup #startInput, #startInput'), err:!!ui.loadError, tabbar:getComputedStyle(document.getElementById('tabbar')).display})")
            check("3.1: Telegram, CloudStorage без ключей → LOAD_OK, мастер показан, экрана ошибки нет", st["ok"] and st["wiz"] and not st["err"] and st["tabbar"] == "none", st)
            await page.evaluate("document.getElementById('startInput').value=new Date().toISOString().slice(0,10); 0"); await page.click('[data-act="setupNext"]'); await page.wait_for_timeout(200); await page.click('[data-act="setupSkip"]'); await page.wait_for_timeout(800)
            check("3.1: мастер доходит до конца и пишет cfg (запись после LOAD_OK разрешена)", '"anchorDate"' in STORE.get("tst_cfg", "") and await page.locator("#tabbar button").count() == 5, list(STORE)[:3])
            await page.context.close()

            # ключи есть, но только служебные (marker клонирования) — данных нет → «пусто»
            STORE.clear(); STORE["tst_clone_state"] = "done"
            page, errs = await tg_page(browser); await page.goto(URL); await page.wait_for_timeout(2500)
            check("3.1: в хранилище только служебный ключ (не cfg/tpl_/w_) — считается пустым: мастер, не ошибка", await page.evaluate("LOAD_OK && !ui.loadError && !!document.getElementById('startInput')"))
            await page.context.close()

            # ---------- данные есть, кэша нет → без мастера
            seed_cfg(dump, lastBackup=None)
            page, errs = await tg_page(browser); await page.goto(URL); await page.wait_for_timeout(2500)
            check("Telegram, данные в облаке, кэша нет: «Загрузка…» → данные, мастера нет", await page.evaluate("LOAD_OK && !ui.loadError && Object.keys(data.log).length===35") and await page.locator("#startInput").count() == 0)
            await page.context.close()

            # ---------- 3.2/3.3 getKeys упал
            seed(dump); before = snap(); w0 = len(WRITES)
            page, errs = await tg_page(browser, init="window.__fail={keys:true,items:false,hang:false};"); await page.goto(URL); await page.wait_for_timeout(2500)
            e1 = await page.evaluate("({ok:LOAD_OK, err:ui.loadError&&ui.loadError.msg, txt:document.getElementById('app').textContent, wiz:!!document.getElementById('startInput'), tabbar:getComputedStyle(document.getElementById('tabbar')).display, btns:[...document.querySelectorAll('#app [data-act]')].map(b=>b.textContent.trim())})")
            check("3.3: getKeys упал → экран ошибки (не мастер): текст ТЗ, кнопка «Повторить», табов нет, LOAD_OK=false", not e1["ok"] and e1["err"] and ERR_TXT in e1["txt"] and "Повторить" in e1["btns"] and not e1["wiz"] and e1["tabbar"] == "none" and "BOOM_KEYS" in e1["err"], e1)
            check("5 (приёмка): при сбое чтения в хранилище ни одной записи — ключи и значения до и после совпадают", STORE == before and len(WRITES) == w0, (len(WRITES) - w0,))
            thr = await page.evaluate("""(async()=>{ const out=[]; try{ await csSet('cfg','{}'); out.push('cs-no-throw'); }catch(e){ out.push('cs-throw'); }
                try{ lsSet('gt2:cache','{}'); out.push('ls-no-throw'); }catch(e){ out.push('ls-throw'); } try{ lsSet('lastSeenVersion','x'); out.push('svc-ok'); }catch(e){ out.push('svc-throw'); }
                persistCfg(); persistDay('2026-01-01'); persistTpl({id:'zz'}); saveCache(); return out; })()""")
            check("3.3: до LOAD_OK csSet/lsSet данных бросают исключение, служебный ключ пишется, persist*/saveCache тихо ничего не пишут", thr == ["cs-throw", "ls-throw", "svc-ok"] and STORE == before and len(WRITES) == w0, thr)
            # «Повторить»: после исправления — загрузка
            await page.evaluate("window.__fail.keys=false; 0"); await page.click('[data-act="loadRetry"]'); await page.wait_for_timeout(2500)
            check("3.3: «Повторить» после устранения причины — данные загружаются (35 дней), экран ошибки исчез, LOAD_OK", await page.evaluate("LOAD_OK && !ui.loadError && Object.keys(data.log).length===35") and await page.locator("#tabbar button").count() == 5)
            await page.context.close()

            # getItems упал
            seed(dump); before = snap(); w0 = len(WRITES)
            page, errs = await tg_page(browser, init="window.__fail={keys:false,items:true,hang:false};"); await page.goto(URL); await page.wait_for_timeout(2500)
            check("3.3: getItems упал → экран ошибки, без мастера и записей", await page.evaluate("!LOAD_OK && !!ui.loadError && !document.getElementById('startInput')") and STORE == before and len(WRITES) == w0 and ERR_TXT in await page.inner_text("#app"))
            await page.context.close()

            # значения не разобрались (мусор вместо JSON)
            seed(dump)
            for k in list(STORE):
                if k.startswith(("tst_w_", "tst_tpl_")) or k == "tst_cfg": STORE[k] = "{мусор"
            before = snap(); w0 = len(WRITES)
            page, errs = await tg_page(browser); await page.goto(URL); await page.wait_for_timeout(2500)
            check("3.2: ключи есть, но ни cfg, ни шаблонов, ни дней не разобрались → экран ошибки, не мастер; ничего не записано", await page.evaluate("!LOAD_OK && !!ui.loadError && !document.getElementById('startInput')") and STORE == before and len(WRITES) == w0, (len(WRITES) - w0,))
            await page.context.close()

            # приёмка 5: испорченный разбор (исключение в normalizeData)
            seed(dump); before = snap(); w0 = len(WRITES)
            page, errs = await tg_page(browser, init="window.__breakParse=true;", break_parse=True); await page.goto(URL); await page.wait_for_timeout(2500)
            e5 = await page.evaluate("({ok:LOAD_OK, err:ui.loadError&&ui.loadError.msg, wiz:!!document.getElementById('startInput'), txt:document.getElementById('app').textContent})")
            check("приёмка 5: исключение в normalizeData → вместо мастера экран ошибки с причиной, в хранилище ни одной записи (ключи и значения до/после)", not e5["ok"] and e5["err"] and "BOOM_PARSE" in e5["err"] and not e5["wiz"] and ERR_TXT in e5["txt"] and STORE == before and len(WRITES) == w0, (e5["err"], len(WRITES) - w0))
            await page.context.close()

            # таймаут getKeys
            seed(dump); before = snap()
            page, errs = await tg_page(browser, init="window.__fail={keys:false,items:false,hang:true};"); await page.goto(URL); await page.wait_for_timeout(12000)
            check("3.3: getKeys не отвечает 10 с → экран ошибки (не бесконечная загрузка и не мастер)", await page.evaluate("!LOAD_OK && !!ui.loadError && /нет ответа/.test(ui.loadError.msg)") and STORE == before, await page.evaluate("ui.loadError&&ui.loadError.msg"))
            await page.context.close()

            # кэш есть → работаем сразу, даже если облако упало
            seed(dump)
            page, errs = await tg_page(browser)
            await page.goto(URL); await page.wait_for_timeout(2500)
            await page.evaluate("window.__fail.keys=true; 0"); await page.reload(); await page.wait_for_timeout(2500)
            check("есть локальный кэш, облако недоступно: приложение работает (LOAD_OK), без экрана ошибки", await page.evaluate("LOAD_OK && !ui.loadError && Object.keys(data.log).length===35") and await page.locator("#tabbar button").count() == 5)
            await page.context.close()

            # ---------- браузер
            async def bpage(ls, init=None):
                ctx = await browser.new_context(viewport={"width": 390, "height": 844})
                await ctx.add_init_script(SEEN_JS)
                await ctx.add_init_script("if(!localStorage.getItem('__seeded')){ localStorage.setItem('__seeded','1'); const c=%s; for(const k of Object.keys(c)) localStorage.setItem(k,c[k]); }" % json.dumps(ls))
                if init: await ctx.add_init_script(init)
                pg = await ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
                await pg.route("**/telegram.org/**", lambda r: r.abort()); await pg.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
                return pg, errs
            LS = "(()=>{ const o={}; for(let i=0;i<localStorage.length;i++){ const k=localStorage.key(i); if(!k.startsWith('__')) o[k]=localStorage.getItem(k); } return JSON.stringify(Object.keys(o).sort().map(k=>[k,o[k]])); })()"
            page, errs = await bpage({}); await page.goto(URL); await page.wait_for_timeout(1800)
            check("3.1: браузер, нет ни одного ключа данных → LOAD_OK, мастер", await page.evaluate("LOAD_OK && !ui.loadError && !!document.getElementById('startInput') ||  LOAD_OK && !ui.loadError && !data.cfg.cycle.anchorDate"))
            await page.context.close()
            page, errs = await bpage({"tst_gt2:cache": "{повреждено"}); await page.goto(URL); await page.wait_for_timeout(1800)
            b0 = await page.evaluate(LS)
            check("3.2: браузер, кэш есть, но не читается → экран ошибки, не мастер; кэш не перезаписан", await page.evaluate("!LOAD_OK && !!ui.loadError && !document.getElementById('startInput')") and ERR_TXT in await page.inner_text("#app") and "повреждено" in b0, await page.evaluate("ui.loadError&&ui.loadError.msg"))
            await page.reload(); await page.wait_for_timeout(1500)
            check("3.2: после перезагрузки то же — значения в localStorage те же (ничего не записано)", await page.evaluate(LS) == b0)
            await page.context.close()
            page, errs = await bpage({"tst_gym-tracker-v1": "{не json"}); await page.goto(URL); await page.wait_for_timeout(1800)
            check("3.2: браузер, данные v1 есть, но не читаются → экран ошибки, не мастер", await page.evaluate("!LOAD_OK && !!ui.loadError"))
            await page.context.close()
            good = {"tst_gt2:cache": json.dumps({"cfg": dict(dump["cfg"], backupSnooze=int(time.time() * 1000) + 365 * 86400000), "templates": dump["templates"], "log": dump["log"]})}
            page, errs = await bpage(good); await page.goto(URL); await page.wait_for_timeout(1800)
            check("браузер, кэш в порядке: приложение открывается без мастера и ошибок", await page.evaluate("LOAD_OK && !ui.loadError && Object.keys(data.log).length===35") and await page.locator("#startInput").count() == 0)
            check("нет pageerror (браузер)", not errs, errs[:2])
            await page.context.close()
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
