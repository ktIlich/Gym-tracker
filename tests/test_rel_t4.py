"""Релиз/prod, задача 4: экран «Не удалось загрузить данные» — «Повторить», «Сохранить сырые данные», «Сообщить об ошибке»."""
import asyncio, copy, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, WRITES, check, RESULTS, REPO, BASE, SEEN_JS, APP_VER
from test_task7 import seed
from test_p11_t1 import open_ep
from test_rel_t3 import FAILWRAP, URL, ERR_TXT
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
CRLF, LF = chr(13) + chr(10), chr(10)
BREAK = lambda txt: txt.replace("function normalizeData(d){", "function normalizeData(d){ if(window.__breakParse) throw new Error('BOOM_PARSE');", 1)

def garbage(prefix="{мусор"):
    for k in list(STORE):
        if k.startswith(("tst_w_", "tst_tpl_")) or k == "tst_cfg": STORE[k] = prefix + k

def raw_keys(before): return {k[4:]: v for k, v in before.items() if k.startswith("tst_")}

async def ep_page(browser, mode="ok", init=None, break_parse=False):
    page, st, errs = await open_ep(browser, mode=mode)
    await page.context.add_init_script(FAILWRAP)
    await page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    if init: await page.context.add_init_script(init)
    if break_parse:
        async def index(route):
            resp = await route.fetch(); txt = await resp.text()
            await route.fulfill(response=resp, body=BREAK(txt.replace('const BACKUP_ENDPOINT="";', 'const BACKUP_ENDPOINT="https://worker.test/";')))
        await page.route(re.compile(r".*/test/index\.html(\?.*)?$"), index)
    return page, st, errs

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            # ---------- Telegram: значения не разобрались; сырые данные уходят в чат
            seed(dump); garbage()
            before = copy.deepcopy(STORE); w0 = len(WRITES)
            page, st, errs = await ep_page(browser)
            await page.goto(URL); await page.wait_for_timeout(2500)
            sc = await page.evaluate("({txt:document.getElementById('app').textContent, btns:[...document.querySelectorAll('#app [data-act]')].map(b=>b.textContent.trim()), tabbar:getComputedStyle(document.getElementById('tabbar')).display, wiz:!!document.getElementById('startInput')})")
            check("4: экран ошибки: текст ТЗ и три кнопки «Повторить», «Сохранить сырые данные», «Сообщить об ошибке»; табы недоступны, мастера нет", ERR_TXT in sc["txt"] and sc["btns"] == ["Повторить", "Сохранить сырые данные", "Сообщить об ошибке"] and sc["tabbar"] == "none" and not sc["wiz"], sc)
            await page.click('[data-act="loadSaveRaw"]'); await page.wait_for_timeout(1500)
            sent = json.loads(st["reqs"][0]["content"]) if st["reqs"] else {}
            check("4.2: Telegram — «Сохранить сырые данные» запрашивает разрешение и отправляет сырой дамп в чат (1 запрос, ключи как есть, мусор не разбирается)", await page.evaluate("window.__wa||0") == 1 and len(st["reqs"]) == 1 and sent.get("kind") == "raw-dump" and sent.get("keys") == raw_keys(before), (len(st["reqs"]),))
            check("4.2: сообщение «Копия отправлена в чат», экран ошибки остаётся, записей в хранилище нет", "Копия отправлена в чат" in await page.inner_text("#app") and await page.evaluate("!LOAD_OK && !!ui.loadError") and STORE == before and len(WRITES) == w0)
            await page.context.close()

            # отправка не удалась → текст для копирования
            seed(dump); garbage()
            before = copy.deepcopy(STORE); w0 = len(WRITES)
            page, st, errs = await ep_page(browser, mode="fail")
            await page.goto(URL); await page.wait_for_timeout(2500)
            await page.click('[data-act="loadSaveRaw"]'); await page.wait_for_timeout(1500)
            ta = await page.evaluate("(()=>{ const t=document.getElementById('loadTxt'); return t&&{v:t.value, ro:t.readOnly}; })()")
            raw = json.loads(ta["v"]) if ta else {}
            check("4.2: отправка не удалась → дамп показан текстом в textarea (валидный сырой дамп, все ключи) с кнопкой «Скопировать»", ta and raw.get("kind") == "raw-dump" and raw["keys"] == raw_keys(before) and await page.locator('[data-act="loadCopy"]').count() == 1, (ta and ta["v"][:60],))
            await page.click('[data-act="loadCopy"]'); await page.wait_for_timeout(300)
            clip = await page.evaluate("navigator.clipboard.readText()")
            check("4.2: «Скопировать» кладёт дамп в буфер обмена; локальная копия rawdump_<версия> сохранена; в хранилище записей нет", json.loads(clip)["kind"] == "raw-dump" and await page.evaluate("localStorage.getItem('tst_rawdump_%s')" % APP_VER) is not None and STORE == before and len(WRITES) == w0, clip[:40])
            await page.context.close()

            # разрешение не дано → тоже текст
            seed(dump); garbage("{мусор")
            page, st, errs = await ep_page(browser, init="window.__waAllow=false;")
            await page.goto(URL); await page.wait_for_timeout(2500)
            await page.click('[data-act="loadSaveRaw"]'); await page.wait_for_timeout(1200)
            check("4.2: нет разрешения писать в чат — запрос не отправляется, дамп показан текстом", len(st["reqs"]) == 0 and await page.locator("#loadTxt").count() == 1)
            await page.context.close()

            # ---------- «Сообщить об ошибке»
            seed(dump); before = copy.deepcopy(STORE); w0 = len(WRITES); nkeys = len([k for k in STORE if k.startswith("tst_")])
            page, st, errs = await ep_page(browser, init="window.__breakParse=true;", break_parse=True)
            await page.goto(URL); await page.wait_for_timeout(2500)
            await page.click('[data-act="loadReport"]'); await page.wait_for_timeout(300)
            rep = await page.evaluate("document.getElementById('loadTxt').value")
            check("4.3: «Сообщить об ошибке»: версия, ENV, IN_TG, платформа, число ключей (%d), полный текст ошибки со стеком" % nkeys, ("Gym Tracker v" + APP_VER) in rep and "ENV: test" in rep and "IN_TG: true" in rep and "Платформа: ios" in rep and ("Ключей в хранилище: %d" % nkeys) in rep and "BOOM_PARSE" in rep and "Стек:" in rep and "at " in rep.split("Стек:")[1], rep[:300])
            await page.click('[data-act="loadCopy"]'); await page.wait_for_timeout(300)
            clip2 = (await page.evaluate("navigator.clipboard.readText()")).replace(CRLF, LF)
            check("4.3: «Скопировать» копирует сведения в буфер; хранилище не тронуто", clip2 == rep.replace(CRLF, LF) and STORE == before and len(WRITES) == w0, (STORE == before, len(WRITES) - w0, clip2[:80]))
            await page.click('[data-act="loadReport"]'); await page.wait_for_timeout(200)
            check("4.3: повторное нажатие скрывает сведения", await page.locator("#loadTxt").count() == 0)
            await page.evaluate("window.__breakParse=false; 0"); await page.click('[data-act="loadRetry"]'); await page.wait_for_timeout(2500)
            check("4.1: «Повторить» после устранения причины — данные загружены, экран ошибки пропал", await page.evaluate("LOAD_OK && !ui.loadError && Object.keys(data.log).length===35") and await page.locator("#tabbar button").count() == 5)
            await page.context.close()

            # ---------- браузер: сырые данные скачиваются файлом
            ctx = await browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
            await ctx.add_init_script(SEEN_JS)
            await ctx.add_init_script("if(!localStorage.getItem('__s')){ localStorage.setItem('__s','1'); localStorage.setItem('tst_gt2:cache','{повреждено'); localStorage.setItem('tst_gt2:snapshot','x'); }")
            page = await ctx.new_page(); errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
            await page.route("**/telegram.org/**", lambda r: r.abort())
            await page.goto(URL); await page.wait_for_timeout(1800)
            check("4: браузер, повреждённый кэш: экран ошибки с тремя кнопками", ERR_TXT in await page.inner_text("#app") and await page.locator("#app [data-act]").count() == 3)
            async with page.expect_download(timeout=8000) as dlw:
                await page.click('[data-act="loadSaveRaw"]')
            f = await dlw.value; fp = os.path.join(os.environ.get("TEMP", "."), "gt_rel4_raw.json"); await f.save_as(fp); body = json.load(open(fp, encoding="utf-8")); await page.wait_for_timeout(300)
            check("4.2: браузер — скачивается файл gym-tracker-before-<версия>-<дата>.json с сырыми значениями (повреждённый кэш как есть)", re.match(r"gym-tracker-before-%s-\d{4}-\d\d-\d\d\.json" % re.escape(APP_VER), f.suggested_filename) and body["kind"] == "raw-dump" and body["source"] == "local" and body["keys"]["gt2:cache"] == "{повреждено" and body["keys"]["gt2:snapshot"] == "x", (f.suggested_filename, body["keys"]))
            check("4.2: после скачивания кэш не перезаписан и приложение остаётся на экране ошибки", await page.evaluate("localStorage.getItem('tst_gt2:cache')") == "{повреждено" and await page.evaluate("!LOAD_OK && !!ui.loadError"))
            check("нет pageerror (браузер)", not errs, errs[:2])
            await ctx.close()
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
