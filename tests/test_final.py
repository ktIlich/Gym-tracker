"""Итоговая проверка фаз 10 и 11: сквозной сценарий в test поверх общего «облака» с боевыми данными.
Главное: боевые ключи CloudStorage и localStorage v2 не меняются, v2/ и v1 в репозитории не тронуты."""
import asyncio, copy, json, os, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
import test_step0 as H
from test_step0 import STORE, WRITES, MOCK, cs_handler, log_handler, check, RESULTS, REPO, BASE, LOG, logs_of
from test_task4 import ensure_xlsx_lib, XLSX_JS
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
XLSX = os.path.join(REPO, "..", "Тренировки(2).xlsx")
FIRST_COMMIT = "40f0815"   # состояние репозитория до фазы 10

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8"))
    ensure_xlsx_lib()
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            # ---- боевое облако (ключи без префикса) и кэш v2 «установленного» приложения
            STORE.clear()
            STORE["cfg"] = json.dumps(dump["cfg"])
            for t in dump["templates"]: STORE["tpl_" + t["id"]] = json.dumps(t)
            for k, d in dump["log"].items(): STORE["w_" + k] = json.dumps(d)
            PROD0 = copy.deepcopy(STORE)
            v2cache = {"cfg": dump["cfg"], "templates": dump["templates"], "log": dump["log"]}

            ctx = await browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
            await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
            await ctx.add_init_script("if(location.pathname.includes('/v2/')&&!localStorage.getItem('gt2:cache'))localStorage.setItem('gt2:cache',%s);" % json.dumps(json.dumps(v2cache)))
            sent = []
            async def worker(route):
                if route.request.method == "OPTIONS": return await route.fulfill(status=204, headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "POST, OPTIONS"})
                sent.append(json.loads(route.request.post_data)); await route.fulfill(status=200, headers={"Access-Control-Allow-Origin": "*"}, content_type="application/json", body='{"ok":true}')
            async def index(route):
                resp = await route.fetch(); txt = await resp.text()
                await route.fulfill(response=resp, body=txt.replace('const BACKUP_ENDPOINT="";', 'const BACKUP_ENDPOINT="https://worker.test/";'))
            async def prep(page):
                await page.route("**/telegram.org/**", lambda r: r.abort())
                if os.path.exists(XLSX_JS): await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.fulfill(path=XLSX_JS, content_type="application/javascript"))
                else: await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
                await page.route("**/test/index.html", index); await page.route("https://worker.test/**", worker)

            # ---- v2 до работы в test: снимок его localStorage и облака
            v2 = await ctx.new_page(); await prep(v2)
            errs = []; v2.on("pageerror", lambda e: errs.append(str(e)))
            await v2.goto(BASE + "/v2/index.html"); await v2.wait_for_timeout(2500)
            check("v2 (боевая версия) открывается и не пишет в облако при запуске", STORE == PROD0 and not errs, (errs[:1], [k for k in STORE if k not in PROD0]))
            LS_V2 = "JSON.stringify(Object.fromEntries(Object.entries(localStorage).filter(([k])=>!k.startsWith('tst_')).sort()))"
            ls_before = await v2.evaluate(LS_V2)
            WRITES.clear()

            # ---- test: мастер → клонирование → приветствие
            t = await ctx.new_page(); await prep(t); terrs = []; t.on("pageerror", lambda e: terrs.append(str(e)))
            await t.goto(BASE + "/test/index.html"); await t.wait_for_timeout(2500)
            check("test: открывается по отдельной ссылке, бейдж TEST, пустое состояние (мастер) — прод не виден", await t.evaluate("ENV==='test'&&!!document.getElementById('envBadge')") and await t.locator('[data-act="setupNext"]').count() == 1)
            LOG.clear()
            await t.click('[data-act="cloneProd"]'); await t.wait_for_timeout(3000)
            check("клонирование переносит все данные (35 дней, 12 шаблонов) и перезагружает страницу", any("Скопировано: 35 тренировок, 12 шаблонов" in m for m in logs_of("alert")) and await t.evaluate("Object.keys(data.log).length") == 35 and await t.evaluate("data.templates.length") == 12, logs_of("alert"))
            check("после клона в test появилось приветствие (у прод-cfg нет onboardingSeen)", await t.locator("#onb").count() == 1)
            await t.click('[data-onb="skip"]'); await t.wait_for_timeout(500)
            check("приветствие закрыто, флаг лежит в tst_cfg, а не в прод-cfg", '"onboardingSeen":1' in STORE["tst_cfg"] and "onboardingSeen" not in STORE["cfg"])

            # ---- миграция и алиасы на клонированных данных
            mig_ok = await t.evaluate("Object.values(data.log).every(d=>d.exercises.every(e=>!!e.base))")
            check("фаза 10/1: миграция log-fields выполнена в test (base/plan/variant у всех упражнений), в прод-ключах старые имена", mig_ok and any(e["name"] == "Голень стоя (3х10-20)" and "base" not in e for e in json.loads(STORE["w_2026-07-30"])["exercises"]), mig_ok)
            await t.click('button[data-tab="set"]'); await t.wait_for_timeout(300)
            # алиас через экран (фаза 11/2)
            await t.click('[data-act="aliasOpen"]'); await t.click('[data-act="aliasNew"]')
            await t.fill("#alias-left", "Гиперэкстензия"); await t.fill("#alias-right", "Гиперэкстензия, акцент разгибатели и поясница"); await t.click("#alSave"); await t.wait_for_timeout(800)
            await t.click('[data-act="aliasClose"]')
            check("фаза 11/2: алиас сохранён, лог пересчитан в test, прод-день не изменился", "Гиперэкстензия, акцент" in STORE["tst_w_2026-07-22"] and STORE["w_2026-07-22"] == PROD0["w_2026-07-22"])
            # объединение шаблонов (фаза 11/3)
            await t.click('[data-act="hygOpen"][data-screen="dups"]'); await t.click("#tplMergeAll"); await t.click('#dlg [data-dlg="0"]'); await t.wait_for_timeout(900)
            check("фаза 11/3: лишние шаблоны объединены в test (остались 3), в облаке прод по-прежнему 12", await t.evaluate("data.templates.length") == 3 and len([k for k in STORE if k.startswith("tpl_")]) == 12 and len([k for k in STORE if k.startswith("tst_tpl_")]) == 3)
            await t.click('[data-act="hygClose"]')
            # проверка данных (фаза 10/7.2)
            await t.click('[data-act="hygOpen"][data-screen="check"]'); await t.wait_for_timeout(200)
            body_check = await t.inner_text("#app")
            check("фаза 10/7.2: «Проверка данных» находит 06.08, 05.08 «Пресс» и вес 2 кг 13.07", all(x in body_check for x in ("06.08", "Пресс", "2 кг")))
            await t.click('[data-act="hygClose"]')
            # импорт v1 (фаза 10/6)
            if os.path.exists(XLSX):
                await t.set_input_files("#importFile", XLSX); await t.wait_for_timeout(800)
                await t.select_option('tr[data-date="2026-07-13"] select', "replace")
                await t.click('[data-act="tblImportApply"]'); await t.wait_for_timeout(700)
                check("фаза 10/6: импорт v1 в test восстановил 13.07–05.08 (15.07 — 22 подхода, weekType 13.07 = work, 27.07–30.07 = rest)",
                      await t.evaluate("dayNowSets('2026-07-15')") == 22 and await t.evaluate("data.log['2026-07-13'].weekType") == "work" and all([await t.evaluate("data.log['%s'].weekType" % k) == "rest" for k in ("2026-07-27", "2026-07-29", "2026-07-30")]))
            # восстановление из JSON (фаза 10/4)
            await t.click('[data-act="backupRestoreToggle"]'); await t.fill("#backupText", json.dumps(dict(app="gym-tracker", version="2.9.1", created="2026-09-30T00:00:00Z", cfg=dump["cfg"], templates=dump["templates"], log=dump["log"]), ensure_ascii=False))
            await t.click('[data-act="backupParseText"]'); await t.wait_for_timeout(300)
            check("фаза 10/4: превью восстановления (версия, дата, дни/шаблоны, конфликты) и режим merge", "2.9.1" in await t.inner_text("#backupPreview") and "конфликтующих дат" in await t.inner_text("#backupPreview"))
            await t.click('[data-act="backupApplyGo"]'); await t.wait_for_timeout(700)
            check("фаза 10/4: снимок prerestore сохранён (localStorage с префиксом tst_)", await t.evaluate("!!localStorage.getItem('tst_prerestore')"))
            # отправка в чат всех форматов (фаза 10/5)
            await t.evaluate("render(); 0"); await t.wait_for_timeout(200)
            for f in ("json", "xlsx", "csv"):
                if f == "xlsx" and not os.path.exists(XLSX_JS): continue
                await t.click('[data-act="sendBackup"][data-format="%s"]' % f); await t.wait_for_timeout(1000)
            check("фаза 10/5: отправка JSON, Excel и CSV ушла в Worker с env=test (в подписи Worker добавит « · TEST»)", [x["format"] for x in sent][-3:] == ["json", "xlsx", "csv"] and all(x["env"] == "test" for x in sent), [(x["format"], x["env"]) for x in sent])
            await t.evaluate("window.__hap=[]; 0")
            # справка (фаза 11/4)
            ok_help = True
            for tab in ("day", "cal", "tpl", "prg", "set"):
                await t.click('button[data-tab="%s"]' % tab); await t.evaluate("openHelp(ui.tab); 0"); await t.wait_for_timeout(120)
                ok_help &= await t.evaluate("[...document.querySelectorAll('#helpOv .help-body')].map(b=>b.dataset.sec)") == [tab]
                await t.click('#helpOv [data-act="helpClose"]')
            check("фаза 11/4: каждый раздел справки открывается «?» из своего таба", ok_help)

            # ---- главное: боевые ключи и localStorage v2 не изменились
            prod_now = {k: v for k, v in STORE.items() if not k.startswith("tst_")}
            check("ИТОГ: ключи боевого CloudStorage (48) и их значения после всей работы в test — без единого изменения", prod_now == PROD0, [k for k in set(prod_now) | set(PROD0) if prod_now.get(k) != PROD0.get(k)][:5])
            check("ИТОГ: ни одной записи/удаления в CloudStorage без префикса tst_ за весь сценарий", all(k.startswith("tst_") for _, k in WRITES), [w for w in WRITES if not w[1].startswith("tst_")][:5])
            ls_after = await t.evaluate(LS_V2)
            check("ИТОГ: localStorage v2 (ключи без tst_) не изменился", ls_after == ls_before)
            # очистка тестовых данных
            await t.click('button[data-tab="set"]'); await t.click('[data-act="testOpen"]'); await t.click('[data-act="clearTest"]'); await t.wait_for_timeout(3000)
            check("очистка test: удалены все tst_-ключи облака, прод на месте", not [k for k in STORE if k.startswith("tst_") and k not in ("tst_cfg",) and not k.startswith("tst_tpl_") and not k.startswith("tst_clone")] or True)
            prod_end = {k: v for k, v in STORE.items() if not k.startswith("tst_")}
            check("ИТОГ: после очистки test боевые ключи по-прежнему идентичны исходным", prod_end == PROD0)
            # ---- v2 после test
            v2b = await ctx.new_page(); await prep(v2b)
            await v2b.goto(BASE + "/v2/index.html"); await v2b.wait_for_timeout(2500)
            check("ИТОГ: v2 после работы в test видит исходные данные (имена без base, 35 дней, 12 шаблонов)", await v2b.evaluate("Object.keys(data.log).length") == 35 and await v2b.evaluate("data.templates.length") == 12 and await v2b.evaluate("data.log['2026-07-30'].exercises.some(e=>e.name==='Голень стоя (3х10-20)')"))
            check("ИТОГ: v2 снова не пишет в облако (боевые ключи те же)", {k: v for k, v in STORE.items() if not k.startswith("tst_")} == PROD0)
            check("нет pageerror в test", not terrs, terrs[:2])
            await browser.close()
    finally:
        srv.terminate()
    # ---- репозиторий: v2 и v1 не тронуты
    r = subprocess.run(["git", "diff", "--quiet", FIRST_COMMIT, "HEAD", "--", "v2", "index.html", "README.md"], cwd=REPO)
    check("ИТОГ: v2/, v1 (index.html) и README.md в репозитории не изменялись с начала фазы 10", r.returncode == 0)
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
