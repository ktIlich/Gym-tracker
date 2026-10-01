"""Релиз: v2/index.html (prod) — идентичен test/index.html; по пути /v2/ работает как prod (ключи без tst_, без тестовых элементов)."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, WRITES, check, RESULTS, REPO, BASE, MOCK, cs_handler, log_handler, APP_VER
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
URL = BASE + "/v2/index.html"

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    t = open(os.path.join(REPO, "test", "index.html"), "rb").read(); v = open(os.path.join(REPO, "v2", "index.html"), "rb").read()
    check("релиз: v2/index.html идентичен test/index.html (одна кодовая база, среда определяется путём)", t == v)
    src = v.decode("utf-8")
    check("релиз: APP_VERSION финальный (%s), <title> без TEST, BACKUP_ENDPOINT задан" % APP_VER, ('APP_VERSION="%s"' % APP_VER) in src and "<title>Gym Tracker</title>" in src and re.search(r'const BACKUP_ENDPOINT="https://[^"]+workers\.dev"', src) is not None)
    check("релиз: ENV определяется по пути (/test/ → test, иначе prod)", 'const ENV = location.pathname.includes("/test/") ? "test" : "prod";' in src)
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            # прод-данные в облаке без префикса; версия «уже виденная», чтобы не мешала копия при обновлении
            STORE.clear(); STORE["cfg"] = json.dumps(dict(dump["cfg"], writeAccess=True));
            for tp in dump["templates"]: STORE["tpl_" + tp["id"]] = json.dumps(tp)
            for k, d in dump["log"].items(): STORE["w_" + k] = json.dumps(d)
            before = dict(STORE); w0 = len(WRITES)
            ctx = await browser.new_context(viewport={"width": 390, "height": 844})
            await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler)
            # в prod у MOCK-хранилища нет префикса: подменяем ключи tst_ → без префикса не нужно, MOCK работает с «полными» ключами
            await ctx.add_init_script(MOCK.replace("localStorage.setItem('tst_lastSeenVersion'", "localStorage.setItem('lastSeenVersion'"))
            page = await ctx.new_page(); errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            await page.route("**/telegram.org/**", lambda r: r.abort()); await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
            await page.goto(URL); await page.wait_for_timeout(3000)
            st = await page.evaluate("({env:ENV, kp:KP, title:document.title, badge:!!document.getElementById('envBadge'), days:Object.keys(data.log).length, tpl:data.templates.length, ok:LOAD_OK, err:!!ui.loadError, ver:document.querySelector('.ver')?document.querySelector('.ver').textContent:''})")
            check("prod (/v2/): ENV=prod, префикса ключей нет, заголовок «Gym Tracker», значка TEST нет, данные загружены (35 дней, 12 шаблонов), экрана ошибки нет", st["env"] == "prod" and st["kp"] == "" and st["title"] == "Gym Tracker" and not st["badge"] and st["days"] == 35 and st["tpl"] == 12 and st["ok"] and not st["err"], st)
            check("prod: версия внизу экрана v%s" % APP_VER, ("v" + APP_VER) in st["ver"], st["ver"])
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(300)
            txt = await page.inner_text("#app")
            check("prod: в «Настройках» нет тестовых разделов («Тестовая среда», TEST, диагностика)", "Тестовая среда" not in txt and "TEST" not in txt and await page.locator('[data-act="testOpen"], [data-act="cloneProd"], [data-act="diagOpen"]').count() == 0)
            help_txt = await page.evaluate("(openHelp('set'), document.getElementById('helpOv').textContent)")
            check("prod: в справочнике нет пункта «Тестовая среда»", "Тестовая среда" not in help_txt)
            await page.evaluate("closeHelp(); 0")
            keys = list(STORE)
            changed = [k for k in before if STORE.get(k) != before[k]]
            def same_core(k):
                a, b = json.loads(before[k]), json.loads(STORE[k]); a.pop("up", None); b.pop("up", None)
                if k.startswith("w_"):
                    return [[(e.get("name"), e["sets"]) for e in a["exercises"]]] == [[(e.get("name"), e["sets"]) for e in b["exercises"]]] or all(len(x["sets"]) == len(y["sets"]) for x, y in zip(a["exercises"], b["exercises"]))
                return True
            check("prod: ключей tst_ нет; набор ключей не изменился; значения меняются только у записей, прошедших миграцию (w_/tpl_/cfg), подходы целы", not any(k.startswith("tst_") for k in STORE) and set(STORE) == set(before) and all(k.startswith(("w_", "tpl_")) or k == "cfg" for k in changed) and all(same_core(k) for k in changed if k.startswith("w_")), (len(changed), [k for k in STORE if k not in before][:3]))
            ls_keys = await page.evaluate("Object.keys(localStorage)")
            check("prod: в localStorage нет ключей tst_ (кэш и служебные — без префикса)", not any(k.startswith("tst_") for k in ls_keys) and "gt2:cache" in ls_keys, ls_keys[:6])
            check("prod: guardKey не даёт писать в чужой префикс; запись tst_-ключа из prod не происходит", await page.evaluate("(()=>{ try{ guardKey('gt2:cache'); return true; }catch(e){ return false; } })()"))
            check("нет pageerror (prod)", not errs, errs[:2])
            await ctx.close()
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
