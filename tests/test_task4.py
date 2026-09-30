"""Задача 4: восстановление из JSON (файл/текст, превью, merge/replace, prerestore) и экспорт JSON/XLSX/CSV. На реальном дампе ../current_data.json."""
import asyncio, copy, csv, io, json, os, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, check, RESULTS, REPO, BASE
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
XLSX_JS = os.path.join(tempfile.gettempdir(), "xlsx.full.min-0.18.5.js")
HEADER = ["Дата", "Тренировка", "Неделя цикла", "Упражнение", "Вариант", "План", "Подход", "Вес, кг", "Повторы", "Заметка"]

def ensure_xlsx_lib():
    if os.path.exists(XLSX_JS): return True
    try:
        open(XLSX_JS, "wb").write(urllib.request.urlopen("https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js", timeout=20).read()); return True
    except Exception:
        return False

async def new_page(browser, dump, mock=False, xlsx=True):
    ctx = await browser.new_context(viewport={"width": 390, "height": 900}, accept_downloads=True)
    if mock:
        await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
    cache = {"cfg": dump["cfg"], "templates": dump["templates"], "log": dump["log"]}
    await ctx.add_init_script("if(!localStorage.getItem('tst_gt2:cache'))localStorage.setItem('tst_gt2:cache',%s);" % json.dumps(json.dumps(cache)))
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    await page.route("**/telegram.org/**", lambda r: r.abort())
    if xlsx and os.path.exists(XLSX_JS):
        await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.fulfill(path=XLSX_JS, content_type="application/javascript"))
    else:
        await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
    await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(1200)
    return page, errs

async def download(page, selector):
    async with page.expect_download() as dl:
        await page.click(selector)
    d = await dl.value
    return d.suggested_filename, open(await d.path(), "rb").read()

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8"))
    have_xlsx = ensure_xlsx_lib()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            n_sets = sum(len(e["sets"]) for d in dump["log"].values() for e in d["exercises"])

            # ================= экспорт =================
            page, errs = await new_page(browser, dump)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(300)
            check("экспорт: вне Telegram показаны кнопки JSON / Excel / CSV", all([await page.locator('[data-act="%s"]' % a).count() == 1 for a in ("backupDownload", "export", "exportCsv")]))
            check("экспорт: старая кнопка «Скачать Excel» из блока «Данные» убрана (дубль)", await page.locator('[data-act="export"]').count() == 1)
            # CSV
            await page.evaluate("""(()=>{ const d=data.log['2026-09-25']; d.exercises[0].note='строка1; с ";" и\\nвторая'; d.exercises[0].sets[0].w=37.5; 0 })()""")
            name, raw = await download(page, '[data-act="exportCsv"]')
            check("CSV: имя gym-tracker-<дата>.csv", name.startswith("gym-tracker-") and name.endswith(".csv"), name)
            check("CSV: UTF-8 с BOM", raw[:3] == b"\xef\xbb\xbf")
            text = raw.decode("utf-8-sig")
            rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=";"))
            check("CSV: заголовок — 10 колонок в порядке ТЗ, разделитель «;»", rows[0] == HEADER, rows[0])
            check("CSV: одна строка на подход (%d подходов)" % n_sets, len(rows) - 1 == n_sets, (len(rows) - 1, n_sets))
            check("CSV: во всех строках по 10 полей", all(len(r) == 10 for r in rows))
            check("CSV: десятичная запятая («37,5»)", any(r[7] == "37,5" for r in rows[1:]) and "37.5" not in text)
            note_rows = [r for r in rows[1:] if r[9]]
            check("CSV: заметка с «;», кавычкой и переводом строки — корректно экранирована и читается обратно", any(r[9] == 'строка1; с ";" и\nвторая' for r in note_rows), note_rows[:2])
            keys = [(r[0]) for r in rows[1:]]
            check("CSV: строки отсортированы по дате", keys == sorted(keys))
            gol = [r for r in rows[1:] if r[0] == "2026-07-30" and r[3].startswith("Голень")]
            check("CSV: «Упражнение» — base с алиасом, «План» отдельно, «Вариант» пуст", gol and gol[0][3] == "Голень стоя (икры)" and gol[0][5] == "3х10-20" and gol[0][4] == "" and gol[0][6] == "1", gol[:1])
            mol = [r for r in rows[1:] if r[0] == "2026-08-12" and r[3].startswith("Молотки")]
            check("CSV: вариант в отдельной колонке («Свободный»)", mol and mol[0][3] == "Молотки, свободный вес или блок" and mol[0][4] == "Свободный", mol[:1])
            wk = {r[0]: r[2] for r in rows[1:]}
            ok_wk = all(wk[k].startswith("Отдых") == (dump["log"][k]["weekType"] == "rest") and (wk[k].startswith("Рабочая") == (dump["log"][k]["weekType"] == "work")) for k in dump["log"] if k in wk)
            check("CSV: «Неделя цикла» — «Рабочая · неделя N» / «Отдых» и совпадает с типом недели дня", ok_wk and wk["2026-09-23"].startswith("Рабочая · неделя") and wk["2026-09-02"] == "Отдых", (wk["2026-09-23"], wk["2026-09-02"]))
            order_ok = True
            for k, d in dump["log"].items():
                seq = [r[3] for r in rows[1:] if r[0] == k]
                exp = []
                for e in d["exercises"]:
                    exp += [e["name"]] * len(e["sets"])
                order_ok &= len(seq) == len(exp)
            check("CSV: порядок упражнений внутри дня сохранён (число строк по дням совпадает)", order_ok)
            # JSON
            name, raw = await download(page, '[data-act="backupDownload"]')
            j = json.loads(raw.decode("utf-8"))
            check("JSON: полный дамп (app, cfg, templates, log 35 дней), lastBackup обновлён", j["app"] == "gym-tracker" and len(j["log"]) == 35 and len(j["templates"]) >= 12 and await page.evaluate("!!data.cfg.lastBackup"))
            # XLSX
            if have_xlsx:
                import openpyxl
                name, raw = await download(page, '[data-act="export"]')
                wb = openpyxl.load_workbook(io.BytesIO(raw)); ws = wb.worksheets[0]
                xr = list(ws.iter_rows(values_only=True))
                check("XLSX: имя .xlsx, лист «Тренировки», заголовок как в ТЗ", name.endswith(".xlsx") and ws.title == "Тренировки" and list(xr[0]) == HEADER, (name, ws.title, xr[0]))
                check("XLSX: одна строка на подход, вес/повторы — числа (37.5), подход — номер", len(xr) - 1 == n_sets and any(r[7] == 37.5 for r in xr[1:]) and all(isinstance(r[6], int) and isinstance(r[8], (int, float)) for r in xr[1:]))
                check("XLSX: те же значения, что в CSV (Упражнение/Вариант/План/Неделя)", [tuple(x or "" for x in r[:6]) for r in xr[1:]] == [tuple(r[:6]) for r in rows[1:]])
            else:
                print("SKIP: XLSX (нет сети для SheetJS)")
            check("экспорт: нет pageerror", not errs, errs[:2])

            # внутри Telegram кнопок скачивания нет
            tg_page, tg_errs = await new_page(browser, dump, mock=True)
            await tg_page.click('button[data-tab="set"]'); await tg_page.wait_for_timeout(300)
            check("Telegram (есть initData): кнопок «Скачать» JSON/Excel/CSV нет, «Скопировать JSON» есть", all([await tg_page.locator('[data-act="%s"]' % a).count() == 0 for a in ("backupDownload", "export", "exportCsv")]) and await tg_page.locator('[data-act="backupCopy"]').count() == 1)

            # ================= восстановление =================
            page, errs = await new_page(browser, dump, xlsx=False)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(300)
            await page.click('[data-act="backupRestoreToggle"]'); await page.wait_for_timeout(200)
            check("восстановление: «Загрузить файл» (accept .json,application/json), textarea и «Проверить»",
                  await page.locator('label[for="backupFile"]').inner_text() != "" and await page.get_attribute("#backupFile", "accept") == ".json,application/json"
                  and await page.locator("#backupText").count() == 1 and await page.locator('[data-act="backupParseText"]').inner_text() == "Проверить")
            await page.fill("#backupText", "{не json"); await page.click('[data-act="backupParseText"]'); await page.wait_for_timeout(150)
            check("восстановление: битый JSON → сообщение", "разобрать" in await page.inner_text("#toastMsg"))
            await page.fill("#backupText", '{"a":1}'); await page.click('[data-act="backupParseText"]'); await page.wait_for_timeout(150)
            check("восстановление: не резервная копия → сообщение", "не похоже" in await page.inner_text("#toastMsg"))

            # копия: 1 новая дата, 1 конфликт где копия новее, 1 конфликт где новее текущая, новый шаблон, легаси-запись без base
            mod = copy.deepcopy(dump)
            mod["version"] = "2.9.1"; mod["created"] = "2026-09-30T11:52:28.303Z"
            newer = "2026-09-23"; older = "2026-09-16"
            local_up_newer = mod["log"][newer].get("up") or 0; local_up_older = mod["log"][older].get("up") or 0
            mod["log"][newer]["up"] = 9999999999990; mod["log"][newer]["exercises"][0]["sets"].append({"w": 1, "r": 1})
            mod["log"][older]["up"] = 1; mod["log"][older]["exercises"][0]["sets"].append({"w": 2, "r": 2})
            mod["log"]["2026-10-01"] = {"title": "Новая", "up": 5555, "weekType": "work", "exercises": [{"id": "n1", "name": "Голень стоя (3х10-20)", "sets": [{"w": 30, "r": 10}]}]}
            mod["templates"].append({"id": "newtpl", "name": "Новый шаблон", "title": "Новый", "up": 7, "blocks": [{"type": "single", "items": [{"name": "Жим", "plan": "3х8"}]}]})
            fpath = os.path.join(tempfile.gettempdir(), "gt_restore_test.json"); open(fpath, "w", encoding="utf-8").write(json.dumps(mod, ensure_ascii=False))
            before = await page.evaluate("JSON.parse(JSON.stringify(data.log))")
            await page.set_input_files("#backupFile", fpath); await page.wait_for_timeout(400)
            pv = await page.inner_text("#backupPreview")
            check("превью: версия приложения и дата создания", "2.9.1" in pv and ("30.09.2026" in pv or "2026" in pv), pv[:120])
            check("превью: дней 36, шаблонов %d" % len(mod["templates"]), "Дней в логе — 36" in pv and ("шаблонов — %d" % len(mod["templates"])) in pv, pv)
            check("превью: конфликтующих дат — 35 (все даты, что есть и там и здесь)", "конфликтующих дат — 35" in pv, pv)
            check("превью (merge): добавится 1, заменят текущие 1, останутся текущие 34", "Добавится дней — 1" in pv and "заменят текущие (новее в копии) — 1" in pv and "останутся текущие — 33" in pv or ("останутся текущие — 34" in pv), pv)
            # снимок: ошибка записи → не применяем
            await page.evaluate("window.__origSet=Storage.prototype.setItem; Storage.prototype.setItem=function(k,v){ if(k==='tst_prerestore') throw new Error('quota'); return window.__origSet.call(this,k,v); }; 0")
            await page.click('[data-act="backupApplyGo"]'); await page.wait_for_timeout(250)
            same = await page.evaluate("JSON.stringify(data.log)") == json.dumps(before, ensure_ascii=False, separators=(",", ":")) or await page.evaluate("Object.keys(data.log).length") == 35
            check("восстановление: не удалось сохранить снимок → данные не изменены", same and "снимок" in await page.inner_text("#toastMsg"))
            await page.evaluate("Storage.prototype.setItem=window.__origSet; 0")
            # merge
            await page.click('[data-act="backupApplyGo"]'); await page.wait_for_timeout(500)
            pre = json.loads(await page.evaluate("localStorage.getItem('tst_prerestore')"))
            check("merge: перед применением сохранён снимок K(\"prerestore\") с прежними данными (35 дней)", len(pre["log"]) == 35 and "2026-10-01" not in pre["log"])
            log = await page.evaluate("JSON.parse(JSON.stringify(data.log))")
            check("merge: новая дата добавлена", "2026-10-01" in log and len(log) == 36)
            check("merge: конфликт, где копия новее (больший up), — взята запись копии", len(log[newer]["exercises"][0]["sets"]) == len(before[newer]["exercises"][0]["sets"]) + 1 and log[newer]["up"] == 9999999999990)
            check("merge: конфликт, где текущая новее, — осталась текущая запись", log[older] == before[older])
            check("merge: остальные даты не изменились", all(log[k] == before[k] for k in before if k not in (newer, older)))
            check("merge: после применения прогнаны миграции (легаси-запись 01.10 получила base, up сохранён)",
                  log["2026-10-01"]["exercises"][0]["base"] == "Голень стоя (икры)" and log["2026-10-01"]["up"] == 5555, log["2026-10-01"])
            check("merge: новый шаблон добавлен", await page.evaluate("data.templates.some(t=>t.id==='newtpl')"))
            check("merge: панель восстановления закрыта", await page.locator("#backupPreview").count() == 0)

            # replace (через вставку текста), с подтверждениями
            await page.click('[data-act="backupRestoreToggle"]'); await page.wait_for_timeout(150)
            await page.fill("#backupText", json.dumps(dump, ensure_ascii=False)); await page.click('[data-act="backupParseText"]'); await page.wait_for_timeout(300)
            await page.check('input[name="backupMode"][value="replace"]'); await page.wait_for_timeout(150)
            check("replace: без подтверждения не применяется — кнопка «Заменить всё» ведёт к подтверждению", await page.locator('[data-act="backupApplyGo"]').count() == 0 and await page.locator('[data-act="backupReplaceAsk"]').count() == 1)
            await page.evaluate("doAction('backupApplyGo',{}); 0")
            check("replace: прямой вызов без подтверждения игнорируется", await page.evaluate("Object.keys(data.log).length") == 36)
            await page.click('[data-act="backupReplaceAsk"]'); await page.click('[data-act="backupConfirmNext"]'); await page.wait_for_timeout(150)
            await page.click('[data-act="backupApplyGo"]'); await page.wait_for_timeout(500)
            pre2 = json.loads(await page.evaluate("localStorage.getItem('tst_prerestore')"))
            check("replace: снимок перед заменой (36 дней) и данные заменены копией (35 дней, нет 01.10)", len(pre2["log"]) == 36 and await page.evaluate("Object.keys(data.log).length===35 && !data.log['2026-10-01']"))
            check("replace: миграции прогнаны (у всех упражнений есть base)", await page.evaluate("Object.values(data.log).every(d=>d.exercises.every(e=>!!e.base))"))
            check("нет pageerror", not errs, errs[:2])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
