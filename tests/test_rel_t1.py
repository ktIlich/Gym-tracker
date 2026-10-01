"""Релиз/prod, задача 1: копия (сырой дамп) при каждой новой версии — Telegram и браузер, восстановление."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, WRITES, check, RESULTS, REPO, BASE, SEEN_JS, APP_VER
from test_task7 import seed
from test_p11_t1 import open_ep, seed_cfg, iso_ago, DAY
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
GATE = BASE + "/test/index.html?gate=1"
NOTE = "Копия перед обновлением до v" + APP_VER
FNAME = re.compile(r"^gym-tracker-before-%s-\d{4}-\d\d-\d\d\.json$" % re.escape(APP_VER))

def cloud_keys():
    return {k[4:]: v for k, v in STORE.items() if k.startswith("tst_")}

async def bpage(browser, ls, init=None, viewport=(390, 844)):
    """страница вне Telegram, localStorage предзаполнен (ключи с tst_)"""
    ctx = await browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, accept_downloads=True)
    await ctx.add_init_script(SEEN_JS)      # без ?gate версия считается «уже виденной»
    await ctx.add_init_script("if(!localStorage.getItem('__seeded')){ localStorage.setItem('__seeded','1'); const c=%s; for(const k of Object.keys(c)) localStorage.setItem(k,c[k]); }" % json.dumps(ls))
    if init: await ctx.add_init_script(init)
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    await page.route("**/telegram.org/**", lambda r: r.abort()); await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
    return page, errs

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
            check("1.1: lastSeenVersion хранится в localStorage (K(\"lastSeenVersion\")), не в CloudStorage; шлюз вызывается первым в init", 'lsGet("lastSeenVersion")' in src and 'lsSet("lastSeenVersion",APP_VERSION)' in src and "await versionGate()" in src and src.index("await versionGate()") < src.index("const hadCache=loadCache();"))

            # ============ Telegram, разрешение есть ============
            seed_cfg(dump, lastBackup=iso_ago(1), backupReminderDays=14, writeAccess=True)
            before = cloud_keys(); w0 = len(WRITES)
            page, st, errs = await open_ep(browser)
            await page.goto(GATE); await page.wait_for_timeout(2500)
            check("1.1: версия не совпала — в чат ушёл один JSON с подписью «%s»; запуск не заблокирован (интерфейс на месте, диалога нет)" % NOTE, len(st["reqs"]) == 1 and st["reqs"][0]["format"] == "json" and st["reqs"][0]["note"] == NOTE and await page.locator("#tabbar button").count() == 5 and await page.locator("#dlg").count() == 0, (len(st["reqs"]), st["reqs"][0].get("note") if st["reqs"] else None))
            r = st["reqs"][0]; raw = json.loads(r["content"])
            check("1.2: сырой дамп: kind=raw-dump, app, version, prevVersion, env=test, source=cloud, created (ISO), keys", raw["kind"] == "raw-dump" and raw["app"] == "gym-tracker" and raw["version"] == APP_VER and "prevVersion" in raw and raw["env"] == "test" and raw["source"] == "cloud" and re.match(r"\d{4}-\d\d-\d\dT", raw["created"]) and isinstance(raw["keys"], dict), {k: raw[k] for k in ("kind", "version", "prevVersion", "env", "source")})
            check("1.2: keys — все ключи данных «как есть»: те же имена (без tst_) и те же строки, без разбора (cfg, tpl_*, w_*)", raw["keys"] == before and all(isinstance(v, str) for v in raw["keys"].values()) and any(k.startswith("w_") for k in raw["keys"]) and any(k.startswith("tpl_") for k in raw["keys"]), (len(raw["keys"]), len(before)))
            check("1.2: имя файла gym-tracker-before-<версия>-<дата>.json", FNAME.match(r["filename"]), r["filename"])
            ls = await page.evaluate("localStorage.getItem('tst_lastSeenVersion')")
            check("1.1: после успешной отправки lastSeenVersion = APP_VERSION (в localStorage)", ls == APP_VER and "lastSeenVersion" not in "".join(STORE.keys()), ls)
            await page.goto(GATE); await page.wait_for_timeout(1800)
            check("1.1: повторный запуск той же версии — копия не делается", len(st["reqs"]) == 1)
            await page.context.close()

            # prevVersion попадает в дамп
            seed_cfg(dump, lastBackup=iso_ago(1), writeAccess=True)
            page, st, errs = await open_ep(browser)
            await page.add_init_script("localStorage.setItem('tst_lastSeenVersion','2.9.1');")   # после MOCK: переопределяет «уже виденную»
            await page.goto(GATE); await page.wait_for_timeout(2500)
            check("1.2: prevVersion — предыдущая виденная версия (2.9.1)", len(st["reqs"]) == 1 and json.loads(st["reqs"][0]["content"])["prevVersion"] == "2.9.1")
            await page.context.close()

            # ============ Telegram, разрешения нет ============
            seed_cfg(dump, lastBackup=iso_ago(1), backupReminderDays=14)
            before = cloud_keys(); w0 = len(WRITES)
            page, st, errs = await open_ep(browser)
            await page.goto(GATE); await page.wait_for_timeout(1500)
            d1 = await page.evaluate("(()=>{ const d=document.getElementById('dlg'); return d&&{t:d.querySelector('.dlg-title').textContent, x:d.querySelector('.dlg-text').textContent, b:[...d.querySelectorAll('[data-dlg]')].map(b=>b.textContent)}; })()")
            check("1.3: диалог «Приложение обновилось» с текстом и кнопками «Разрешить и сохранить» / «Продолжить без копии»", d1 and d1["t"] == "Приложение обновилось" and d1["x"] == "Перед обновлением сохраним копию твоих данных в чат с ботом — на случай сбоя." and d1["b"] == ["Разрешить и сохранить", "Продолжить без копии"], d1)
            ui_state = await page.evaluate("({tabbar:getComputedStyle(document.getElementById('tabbar')).display, app:document.getElementById('app').textContent.trim().slice(0,20), cache:localStorage.getItem('tst_gt2:cache'), wa:window.__wa||0})")
            check("1.1: до ответа в диалоге ничего не записано: нет кэша данных, нет записей в облако, запрос разрешения не вызывался, интерфейс данных не показан", ui_state["cache"] is None and len(WRITES) == w0 and cloud_keys() == before and ui_state["wa"] == 0 and "Загрузка" in ui_state["app"], (ui_state, len(WRITES) - w0))
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(300)
            d2 = await page.evaluate("(()=>{ const d=document.getElementById('dlg'); return d&&{t:d.querySelector('.dlg-title').textContent, x:d.querySelector('.dlg-text').textContent, b:[...d.querySelectorAll('[data-dlg]')].map(b=>b.textContent)}; })()")
            check("1.3: «Продолжить без копии» — подтверждение «Без копии данные нельзя будет восстановить при сбое. Продолжить?»", d2 and d2["x"] == "Без копии данные нельзя будет восстановить при сбое. Продолжить?" and len(d2["b"]) == 2, d2)
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(300)
            check("1.3: «Назад» из подтверждения возвращает к первому диалогу", (await page.inner_text("#dlg .dlg-title")) == "Приложение обновилось")
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(200); await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(1800)
            check("1.3: подтверждённый отказ — копия не отправляется, lastSeenVersion записан, приложение запустилось с данными", len(st["reqs"]) == 0 and await page.evaluate("localStorage.getItem('tst_lastSeenVersion')") == APP_VER and await page.locator("#tabbar button").count() == 5 and await page.evaluate("Object.keys(data.log).length") == 35)
            await page.context.close()

            seed_cfg(dump, lastBackup=iso_ago(1), backupReminderDays=14)
            before = cloud_keys(); cfg_before = json.loads(STORE["tst_cfg"])
            page, st, errs = await open_ep(browser)
            await page.goto(GATE); await page.wait_for_timeout(1500)
            await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(2500)
            cfg_after = json.loads(STORE["tst_cfg"])
            check("1.3: «Разрешить и сохранить» — requestWriteAccess(), при согласии дамп уходит в чат (1 запрос, source=cloud, все ключи)", await page.evaluate("window.__wa") == 1 and len(st["reqs"]) == 1 and json.loads(st["reqs"][0]["content"])["keys"] == before and st["reqs"][0]["note"] == NOTE, (len(st["reqs"]),))
            check("1.3: результат разрешения сохранён в cfg.writeAccess=true уже после загрузки (cfg в облаке не затёрт: цикл, тема, остальные поля на месте)", cfg_after.get("writeAccess") is True and cfg_after["cycle"] == cfg_before["cycle"] and all(k in cfg_after for k in cfg_before if k not in ("up",)), {k: cfg_after.get(k) for k in ("writeAccess",)})
            check("1.1: lastSeenVersion записан", await page.evaluate("localStorage.getItem('tst_lastSeenVersion')") == APP_VER)
            await page.context.close()

            # разрешение не дали
            seed_cfg(dump, lastBackup=iso_ago(1), backupReminderDays=14)
            page, st, errs = await open_ep(browser); await page.context.add_init_script("window.__waAllow=false;")
            await page.goto(GATE); await page.wait_for_timeout(1500)
            await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(2500)
            rd = await page.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('tst_rawdump_'))")
            check("1.3: разрешение не получено — в чат ничего не уходит, дамп сохранён локально rawdump_<версия>, тост «Копия сохранена только на этом устройстве», cfg.writeAccess=false", len(st["reqs"]) == 0 and rd == ["tst_rawdump_" + APP_VER] and "Копия сохранена только на этом устройстве" in await page.inner_text("#toastMsg") and json.loads(STORE["tst_cfg"]).get("writeAccess") is False, (rd,))
            await page.context.close()

            # отправка не удалась
            seed_cfg(dump, lastBackup=iso_ago(1), backupReminderDays=14, writeAccess=True)
            page, st, errs = await open_ep(browser, mode="fail")
            await page.context.add_init_script("localStorage.setItem('tst_rawdump_2.9.0','{}'); localStorage.setItem('tst_rawdump_2.9.1','{}');")
            await page.goto(GATE); await page.wait_for_timeout(2800)
            rd = sorted(await page.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('tst_rawdump_'))"))
            loc = json.loads(await page.evaluate("localStorage.getItem('tst_rawdump_%s')" % APP_VER))
            toast_txt = await page.inner_text("#toastMsg")
            check("1.3: ошибка отправки — дамп в localStorage как rawdump_<версия>, хранятся два последних (2.9.1 и текущая)", rd == sorted(["tst_rawdump_2.9.1", "tst_rawdump_" + APP_VER]) and loc["kind"] == "raw-dump", rd)
            check("1.3: ошибка отправки — тост «Копия сохранена только на этом устройстве», запуск не заблокирован", "Копия сохранена только на этом устройстве" in toast_txt and await page.locator("#tabbar button").count() == 5, toast_txt)
            check("1.1: после локальной копии lastSeenVersion записан; дамп и флаг не попадают в сам дамп (служебные ключи исключены)", await page.evaluate("localStorage.getItem('tst_lastSeenVersion')") == APP_VER and not any(k.startswith(("rawdump_", "premig_")) or k == "lastSeenVersion" for k in loc["keys"]), list(loc["keys"])[:3])
            await page.context.close()

            # ============ Telegram, новый пользователь / версия уже видна ============
            STORE.clear()
            page, st, errs = await open_ep(browser)
            await page.goto(GATE); await page.wait_for_timeout(2500)
            check("1.1/приёмка 6: новый пользователь (пустое хранилище) — ни диалога копии, ни отправки; сразу приветствие/мастер; lastSeenVersion записан", len(st["reqs"]) == 0 and await page.evaluate("localStorage.getItem('tst_lastSeenVersion')") == APP_VER and ("Приложение обновилось" not in await page.inner_text("body")), (len(st["reqs"]),))
            check("приёмка 6: у нового пользователя показан мастер (нет экрана ошибки)", await page.locator(".setup").count() >= 1)
            await page.context.close()

            # ============ браузер ============
            tcache = {"tst_gt2:cache": json.dumps({"cfg": dict(dump["cfg"], backupSnooze=int(time.time() * 1000) + 365 * DAY), "templates": dump["templates"], "log": dump["log"]}), "tst_premig_x": "{}", "tst_prerestore": "{}", "other_app_key": "x"}
            page, errs = await bpage(browser, tcache)
            await page.goto(GATE); await page.wait_for_timeout(1500)
            dl = await page.evaluate("(()=>{ const d=document.getElementById('dlg'); return d&&{t:d.querySelector('.dlg-title').textContent, x:d.querySelector('.dlg-text').textContent, big:d.querySelector('.wide-btn.primary').textContent, link:d.querySelector('.link-btn').textContent, linkFs:parseFloat(getComputedStyle(d.querySelector('.link-btn')).fontSize)/parseFloat(getComputedStyle(d.querySelector('.wide-btn')).fontSize), linkDeco:getComputedStyle(d.querySelector('.link-btn')).textDecorationLine, block:getComputedStyle(d).position}; })()")
            check("1.4: браузер: блокирующий диалог «Приложение обновилось — скачай копию данных» с текстом ТЗ, большая кнопка «Скачать копию», маленькая ссылка «Продолжить без копии»", dl and dl["t"] == "Приложение обновилось — скачай копию данных" and dl["x"] == "Обязательно скачай файл, чтобы не потерять данные, если что-то пойдёт не так. Данные в браузере хранятся только на этом устройстве, другой копии нет." and dl["big"] == "Скачать копию" and dl["link"] == "Продолжить без копии" and dl["linkFs"] < 1 and dl["linkDeco"] == "underline", dl)
            check("1.4: пока диалог открыт, приложение не загружено (нет данных и записей)", await page.evaluate("localStorage.getItem('tst_lastSeenVersion')") is None and "Загрузка" in await page.inner_text("#app"))
            async with page.expect_download(timeout=8000) as dlw:
                await page.click('#dlg [data-dlg="0"]')
            f = await dlw.value; raw = json.load(open(await f.path(), encoding="utf-8")); await page.wait_for_timeout(800)
            check("1.2/1.4: «Скачать копию» скачивает gym-tracker-before-<версия>-<дата>.json с сырым дампом (source=local; env=test; ключи данных без префикса tst_ и без служебных premig_/prerestore)", FNAME.match(f.suggested_filename) and raw["kind"] == "raw-dump" and raw["source"] == "local" and raw["env"] == "test" and set(raw["keys"]) == {"gt2:cache"} and raw["keys"]["gt2:cache"] == tcache["tst_gt2:cache"], (f.suggested_filename, list(raw["keys"])))
            check("1.4: после скачивания запуск продолжается (данные загружены), lastSeenVersion записан, копия дополнительно в localStorage rawdump_<версия>", await page.evaluate("Object.keys(data.log).length") == 35 and await page.evaluate("localStorage.getItem('tst_lastSeenVersion')") == APP_VER and await page.evaluate("localStorage.getItem('tst_rawdump_%s')" % APP_VER) is not None)
            check("нет pageerror (браузер, скачивание)", not errs, errs[:2])
            await page.context.close()

            page, errs = await bpage(browser, tcache)
            downloads = []; page.on("download", lambda d: downloads.append(d))
            await page.goto(GATE); await page.wait_for_timeout(1500)
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(250)
            c = await page.evaluate("(()=>{ const d=document.getElementById('dlg'); return {x:d.querySelector('.dlg-text').textContent, b:[...d.querySelectorAll('[data-dlg]')].map(b=>b.textContent)}; })()")
            check("1.4: «Продолжить без копии» — подтверждение (как в 1.3)", c["x"] == "Без копии данные нельзя будет восстановить при сбое. Продолжить?", c)
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(250)
            check("1.4: «Назад» — снова диалог со скачиванием", (await page.inner_text("#dlg .dlg-title")).startswith("Приложение обновилось — скачай"))
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(250); await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(1500)
            check("1.4: подтверждённый отказ — файл не скачан, запуск продолжен, lastSeenVersion записан, локальная копия rawdump_<версия> всё равно сохранена", not downloads and await page.evaluate("Object.keys(data.log).length") == 35 and await page.evaluate("localStorage.getItem('tst_lastSeenVersion')") == APP_VER and await page.evaluate("localStorage.getItem('tst_rawdump_%s')" % APP_VER) is not None)
            await page.context.close()

            # QuotaExceededError при сохранении rawdump — молча
            page, errs = await bpage(browser, tcache, init="(()=>{ const s=Storage.prototype.setItem; Storage.prototype.setItem=function(k,v){ if(String(k).indexOf('rawdump_')>=0){ const e=new Error('quota'); e.name='QuotaExceededError'; throw e; } return s.apply(this,arguments); }; })();")
            await page.goto(GATE); await page.wait_for_timeout(1500)
            async with page.expect_download(timeout=8000):
                await page.click('#dlg [data-dlg="0"]')
            await page.wait_for_timeout(800)
            check("1.4: при QuotaExceededError локальная копия пропускается молча — скачивание и запуск работают, ошибок нет", await page.evaluate("Object.keys(data.log).length") == 35 and not errs and await page.evaluate("localStorage.getItem('tst_lastSeenVersion')") == APP_VER, errs[:2])
            await page.context.close()

            # браузер: новый пользователь и «версия уже видна»
            page, errs = await bpage(browser, {})
            await page.goto(GATE); await page.wait_for_timeout(1500)
            check("1.1: браузер, новый пользователь (хранилище пусто) — диалога нет, lastSeenVersion записан", await page.locator("#dlg").count() == 0 and await page.evaluate("localStorage.getItem('tst_lastSeenVersion')") == APP_VER)
            await page.context.close()
            page, errs = await bpage(browser, dict(tcache, **{"tst_lastSeenVersion": APP_VER}))
            await page.goto(GATE); await page.wait_for_timeout(1500)
            check("1.1: версия уже видна — копия не делается, диалога нет", await page.locator("#dlg").count() == 0)
            await page.context.close()

            # ============ восстановление сырого дампа ============
            seed_cfg(dump, lastBackup=iso_ago(1), writeAccess=True)
            page, st, errs = await open_ep(browser); await page.goto(GATE); await page.wait_for_timeout(2500)
            cloud_raw = st["reqs"][0]["content"]; await page.context.close()
            STORE.clear(); STORE["tst_cfg"] = json.dumps({"cycle": {"workWeeks": 2, "restWeeks": 1, "anchorDate": time.strftime("%Y-%m-%d")}, "onboardingSeen": 1, "up": 1})
            STORE["tst_tpl_anchor"] = json.dumps({"id": "anchor", "name": "Якорь", "title": "Якорь", "up": 1, "blocks": [{"type": "single", "items": [{"name": "Якорное упражнение", "plan": "3х8-12"}]}]})   # чтобы не создавались шаблоны по умолчанию
            page, st, errs = await open_ep(browser, endpoint="")
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            await page.click('[data-act="backupRestoreToggle"]'); await page.wait_for_timeout(200)
            await page.fill("#backupText", cloud_raw); await page.click('[data-act="backupParseText"]'); await page.wait_for_timeout(300)
            prev = await page.inner_text("#app")
            await page.click('[data-act="backupApplyGo"]'); await page.wait_for_timeout(2500)
            rs = await page.evaluate("({days:Object.keys(data.log).length, tpl:data.templates.length, mig:migTodo(data).length})")
            check("приёмка 4: сырой дамп из Telegram восстанавливается через «Восстановить из копии» (вставкой текста) на test без данных: 35 дней, 12 шаблонов (+1 исходный), миграция применена, данные в облаке", rs["days"] == 35 and rs["tpl"] == 13 and rs["mig"] == 0 and len([k for k in STORE if k.startswith("tst_w_")]) == 35, (rs, "35" in prev))
            await page.context.close()
            # дамп из браузера — файлом
            page, errs = await bpage(browser, tcache)
            await page.goto(GATE); await page.wait_for_timeout(1500)
            async with page.expect_download(timeout=8000) as dlw:
                await page.click('#dlg [data-dlg="0"]')
            f = await dlw.value; fpath = os.path.join(os.environ.get('TEMP', '.'), 'gt_rawdump_browser.json'); await f.save_as(fpath); await page.context.close()
            page, errs = await bpage(browser, {"tst_gt2:cache": json.dumps({"cfg": {"cycle": {"workWeeks": 2, "restWeeks": 1, "anchorDate": time.strftime("%Y-%m-%d")}, "onboardingSeen": 1}, "templates": [], "log": {}})})
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(1800)
            await page.click('button[data-tab="set"]'); await page.click('[data-act="backupRestoreToggle"]'); await page.wait_for_timeout(200)
            await page.set_input_files("#backupFile", fpath); await page.wait_for_timeout(500)
            await page.click('[data-act="backupApplyGo"]'); await page.wait_for_timeout(1500)
            rs = await page.evaluate("({days:Object.keys(data.log).length, tpl:data.templates.length, mig:migTodo(data).length})")
            check("приёмка 4: сырой дамп из браузера восстанавливается файлом на пустом test: 35 дней, 12 шаблонов, миграция применена", rs["days"] == 35 and rs["tpl"] == 12 and rs["mig"] == 0, rs)
            await page.evaluate("ui.tab='set'; render(); 0")
            await page.click('[data-act="backupRestoreToggle"]') if await page.locator("#backupText").count() == 0 else None
            await page.fill("#backupText", json.dumps({"kind": "raw-dump", "app": "gym-tracker", "version": "1", "source": "cloud", "keys": {"foo": "bar"}})); await page.click('[data-act="backupParseText"]'); await page.wait_for_timeout(300)
            check("«Восстановить из копии»: сырой дамп без данных приложения — понятное сообщение, ничего не применяется", "В копии нет данных приложения" in await page.inner_text("#toastMsg"))
            check("нет pageerror (восстановление)", not errs, errs[:2])
            await page.context.close()
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
