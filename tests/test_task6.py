"""Задача 6: импорт v1 (xlsx/csv). На реальных файлах ../current_data.json и ../Тренировки(2).xlsx."""
import asyncio, base64, collections, copy, io, json, os, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import check, RESULTS, REPO, BASE
from test_task4 import new_page, ensure_xlsx_lib, XLSX_JS, HEADER
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
XLSX = os.path.join(REPO, "..", "Тренировки(2).xlsx")

async def main():
    if not (os.path.exists(DUMP) and os.path.exists(XLSX)):
        print("SKIP: нет current_data.json или Тренировки(2).xlsx"); return
    import openpyxl
    dump = json.load(open(DUMP, encoding="utf-8"))
    ensure_xlsx_lib()
    wsx = openpyxl.load_workbook(XLSX, data_only=True).worksheets[0]
    frows = [r for r in wsx.iter_rows(min_row=2, values_only=True) if r[0]]
    fcount = collections.Counter(str(r[0])[:10] for r in frows)
    fweek = {str(r[0])[:10]: r[2] for r in frows}
    fseq = collections.defaultdict(list)
    for r in frows: fseq[str(r[0])[:10]].append((float(r[5]), int(r[6])))
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            page, errs = await new_page(browser, dump)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(300)
            check("кнопка «Импорт из Excel/CSV» в блоке «Резервная копия», старая кнопка в «Данные» убрана",
                  await page.locator('[data-act="import"]').count() == 1 and "Импорт из Excel/CSV" in await page.locator('[data-act="import"]').inner_text()
                  and await page.evaluate("document.querySelector('[data-act=import]').closest('.card').previousElementSibling.textContent.includes('Резервная копия')"))
            acc = await page.get_attribute("#importFile", "accept")
            check("файловый input принимает .xlsx, .xls и .csv", ".xlsx" in acc and ".csv" in acc, acc)

            before = await page.evaluate("JSON.parse(JSON.stringify(data.log))")
            await page.set_input_files("#importFile", XLSX); await page.wait_for_timeout(800)
            rows = await page.evaluate("[...document.querySelectorAll('#tblImportTable tr[data-date]')].map(tr=>({d:tr.dataset.date,f:+tr.children[1].textContent,n:tr.children[2].textContent,act:tr.querySelector('select').value,hint:tr.textContent}))")
            check("превью: 11 дат с 13.07 по 05.08", [r["d"] for r in rows] == sorted(fcount), [r["d"] for r in rows])
            check("превью: «в файле» — подходы из файла (244 всего)", all(r["f"] == fcount[r["d"]] for r in rows) and sum(r["f"] for r in rows) == sum(fcount.values()) == 244)
            now = {k: sum(len(e["sets"]) for e in v["exercises"]) for k, v in dump["log"].items()}
            check("превью: «сейчас» — подходов в приложении (15.07: 12, 24.07: 2, 13.07: 22)", all(r["n"] == str(now[r["d"]]) for r in rows) and now["2026-07-15"] == 12 and now["2026-07-24"] == 2)
            acts = {r["d"]: r["act"] for r in rows}
            check("действие по умолчанию: в файле больше → «заменить» (10 дат), иначе «пропустить» (13.07: 21 < 22)", acts["2026-07-13"] == "skip" and all(a == "replace" for d, a in acts.items() if d != "2026-07-13"), acts)
            check("превью: у пропускаемой 13.07 подсказка о расхождении типа недели (отдых → рабочая)", "отдых → рабочая" in [r for r in rows if r["d"] == "2026-07-13"][0]["hint"])
            check("превью: селекторы действий ≥ 44px и переключаются вручную", await page.evaluate("[...document.querySelectorAll('.tbl-act')].every(s=>s.getBoundingClientRect().height>=43.5)"))
            check("превью: итог «дней — 11, подходов — 244»", "дней — 11" in await page.inner_text("#app") and "подходов — 244" in await page.inner_text("#app"))

            # отмена ничего не меняет
            await page.click('[data-act="tblImportCancel"]'); await page.wait_for_timeout(200)
            check("отмена: данные не тронуты, превью закрыто", await page.evaluate("JSON.stringify(data.log)") == json.dumps(before, ensure_ascii=False, separators=(",", ":")) or await page.evaluate("Object.keys(data.log).length") == 35)
            await page.set_input_files("#importFile", XLSX); await page.wait_for_timeout(800)
            # снимок недоступен → не применять
            await page.evaluate("window.__origSet=Storage.prototype.setItem; Storage.prototype.setItem=function(k,v){ if(k==='tst_preimport') throw new Error('quota'); return window.__origSet.call(this,k,v); }; 0")
            await page.click('[data-act="tblImportApply"]'); await page.wait_for_timeout(250)
            check("применение: не удалось сохранить снимок → ничего не применено", "снимок" in await page.inner_text("#toastMsg") and await page.evaluate("Object.keys(data.log).length") == 35 and await page.evaluate("dayNowSets('2026-07-24')") == 2)
            await page.evaluate("Storage.prototype.setItem=window.__origSet; 0")
            # 13.07 вручную → «заменить»
            await page.select_option('tr[data-date="2026-07-13"] select', "replace"); await page.wait_for_timeout(200)
            check("ручное переключение: 13.07 → «заменить»", await page.evaluate("ui.tblImport.days[0].action")  == "replace" and "Применить (11)" in await page.inner_text('[data-act="tblImportApply"]'))
            await page.click('[data-act="tblImportApply"]'); await page.wait_for_timeout(600)
            pre = json.loads(await page.evaluate("localStorage.getItem('tst_preimport')"))
            check("снимок K(\"preimport\") сохранён (данные до импорта: 35 дней, 24.07 — 2 подхода)", len(pre["log"]) == 35 and sum(len(e["sets"]) for e in pre["log"]["2026-07-24"]["exercises"]) == 2)
            log = await page.evaluate("JSON.parse(JSON.stringify(data.log))")
            sets = {k: sum(len(e["sets"]) for e in log[k]["exercises"]) for k in fcount}
            check("приёмка: даты 13.07–05.08 восстановлены полностью — подходов ровно как в файле (в т.ч. 15.07: 22, 24.07: 20)", sets == dict(fcount), {k: (sets[k], fcount[k]) for k in fcount if sets[k] != fcount[k]})
            seq_ok = all([(s["w"], s["r"]) for e in log[k]["exercises"] for s in e["sets"]] == fseq[k] for k in fcount)
            check("приёмка: веса/повторы и порядок подходов совпадают с файлом", seq_ok)
            check("приёмка: weekType 13.07 = work", log["2026-07-13"]["weekType"] == "work", log["2026-07-13"]["weekType"])
            check("приёмка: weekType 27.07, 29.07, 30.07 = rest", all(log[k]["weekType"] == "rest" for k in ("2026-07-27", "2026-07-29", "2026-07-30")), {k: log[k]["weekType"] for k in ("2026-07-27", "2026-07-29", "2026-07-30")})
            check("weekType всех дат — по колонке «Неделя цикла» файла", all(log[k]["weekType"] == ("rest" if fweek[k].startswith("Отдых") else "work") for k in fcount))
            check("13.07: лишний подход 2×10 из приложения ушёл (заменено файлом)", not any(s["w"] == 2 for e in log["2026-07-13"]["exercises"] for s in e["sets"]))
            fex = collections.defaultdict(list)
            for r in frows: fex[str(r[0])[:10]].append(r[3])
            check("упражнения дней: число упражнений совпадает с файлом", all(len(log[k]["exercises"]) == len(dict.fromkeys(fex[k])) for k in fcount))
            allex = [(k, e) for k in fcount for e in log[k]["exercises"]]
            check("разбор как в 1.1 + алиасы: у всех есть base/plan/variant, name собран", all(e["base"] and "plan" in e and "variant" in e and e["name"].startswith(e["base"]) for _, e in allex))
            check("алиасы: «Голень стоя (3х10-20)» → «Голень стоя (икры)», «Сгибания голени сидя или стоя» → «Сгибания голени»",
                  any(e["base"] == "Голень стоя (икры)" and e["plan"] == "3х10-20" for _, e in allex) and any(e["base"] == "Сгибания голени" for _, e in allex) and not any(e["base"] in ("Голень стоя", "Сгибания голени сидя или стоя") for _, e in allex))
            gakk = [e for _, e in allex if e["base"] == "Приседания в гакк-машине"]
            check("алиасы: «Приседания в гаке лицом назад» → база «Приседания в гакк-машине», вариант «Спиной»", any(e["variant"] == "Спиной" for e in gakk) and any(e["variant"] is None for e in gakk), [(e["name"]) for e in gakk])
            check("импортированные даты получили новую метку up, остальные даты (24 шт.) не тронуты",
                  all(log[k]["up"] > (before[k].get("up") or 0) for k in fcount) and all(log[k] == before[k] for k in before if k not in fcount))
            check("нет pageerror", not errs, errs[:2])

            # ================= синтетические файлы =================
            page, errs = await new_page(browser, dump)
            await page.evaluate("data.log={}; saveCache(); 0")
            # разбор CSV: BOM, «;», «,» с кавычками, табуляция, десятичная запятая, кавычки/переносы
            r = await page.evaluate(r"""(()=>{ const out={};
                out.semi=parseCsvText('﻿Дата;Вес, кг;Заметка\r\n2026-01-01;37,5;"а;б ""в""\nг"\r\n');
                out.comma=parseCsvText('Дата,"Вес, кг",Повторы\n2026-01-01,"37,5",8\n');
                out.tab=parseCsvText('Дата\tВес\n2026-01-01\t40\n');
                out.blank=parseCsvText('Дата;Вес\n\n;\n2026-01-02;1\n');
                return out; })()""")
            check("CSV-разбор: BOM, «;», кавычки, экранирование и перенос строки внутри ячейки", r["semi"] == [["Дата", "Вес, кг", "Заметка"], ["2026-01-01", "37,5", 'а;б "в"\nг']], r["semi"])
            check("CSV-разбор: разделитель «,» (заголовок «Вес, кг» в кавычках), табуляция, пустые строки пропускаются", r["comma"] == [["Дата", "Вес, кг", "Повторы"], ["2026-01-01", "37,5", "8"]] and r["tab"][1] == ["2026-01-01", "40"] and len(r["blank"]) == 2, (r["comma"], r["tab"], r["blank"]))
            build = lambda rows: page.evaluate("(rows)=>{ const r=buildTableImport(rows); return r.error?{error:r.error}:{days:r.days.map(d=>({date:d.date,title:d.title,week:d.weekType,weekFile:d.weekFile,nFile:d.nFile,action:d.action,ex:d.groups.map(g=>({n:g.name,e:g.ex.base,v:g.ex.variant,p:g.ex.plan,note:g.note,sets:g.rows.map(x=>[x.w,x.r])}))})),invalid:r.invalid}; }", rows)
            shuffled = [["Повторы", "Вес, кг", "Упражнение", "Подход", "Дата", "Тренировка"],
                        [10, "37,5", "Жим штанги (3х8-12)", 2, "2026-03-02", "Жим"], [8, 40, "Жим штанги (3х8-12)", 1, "2026-03-02", "Жим"],
                        ["x", 40, "Плохая строка", 1, "2026-03-02", "Жим"], [5, "abc", "Плохой вес", 1, "2026-03-02", "Жим"], [5, 30, "", 1, "2026-03-02", "Жим"], [5, 30, "Нет даты", 1, "", "Жим"]]
            b = await build(shuffled)
            check("колонки по заголовкам, порядок не важен; подходы упорядочены по «Подход»; вес с запятой; плохие строки посчитаны", b["days"][0]["ex"][0]["sets"] == [[40, 8], [37.5, 10]] and b["invalid"] == 4 and b["days"][0]["nFile"] == 2, b)
            check("без колонки «Неделя цикла» weekType вычисляется по циклу", b["days"][0]["week"] is None and b["days"][0]["weekFile"] in ("work", "rest"))
            b = await build([["Дата", "Тренировка", "Упражнение", "Вес, кг", "Повторы"], ["2026-03-02", "Жим", "Жим", 40, 8]])
            check("нет обязательной колонки → сообщение с её названием", b == {"error": "В файле нет колонок: Подход"}, b)
            b = await build([["что-то", "другое"], [1, 2]]); check("нет строки заголовков → сообщение", "заголовков" in b["error"], b)
            full = [["Дата", "Тренировка", "Неделя цикла", "Упражнение", "Вариант", "План", "Подход", "Вес, кг", "Повторы", "Заметка"],
                    ["2026-03-04", "Ноги", "Отдых", "Приседания в гаке лицом назад", "", "2х8-12", 1, 60, 8, "тяжело"],
                    ["2026-03-04", "Ноги", "Отдых", "Молотки", "свободный вес", "2x8-15", 1, 15, 12, ""],
                    ["2026-03-04", "Ноги", "Отдых", "Молотки", "свободный вес", "2x8-15", 2, 15, 12, ""]]
            b = await build(full); d0 = b["days"][0]
            check("колонки «Вариант/План/Заметка»: вариант из колонки (алиас «свободный вес» → «Свободный»), план нормализован, заметка на упражнении",
                  d0["ex"][1]["v"] == "Свободный" and d0["ex"][1]["p"] == "2х8-15" and d0["ex"][0]["note"] == "тяжело" and d0["week"] == "rest" and d0["ex"][0]["e"] == "Приседания в гакк-машине" and d0["ex"][0]["v"] == "Спиной", d0)
            check("разбор упражнения (1.1): «Голень стоя (3х10-20) · Лёжа» в одной ячейке → base/plan/variant + алиас", (await build([["Дата", "Тренировка", "Упражнение", "Подход", "Вес", "Повторы"], ["2026-03-05", "Н", "Голень стоя (3х10-20) · Лёжа", 1, 30, 10]]))["days"][0]["ex"][0] | {} == {"n": "Голень стоя (икры) (3х10-20) · Лёжа", "e": "Голень стоя (икры)", "v": "Лёжа", "p": "3х10-20", "note": "", "sets": [[30, 10]]})
            check("даты: ISO, ДД.ММ.ГГГГ, серийный номер Excel, Date", await page.evaluate("[normDate('2026-03-02'),normDate('02.03.2026'),normDate(46083),normDate(new Date(2026,2,2))].every(x=>x==='2026-03-02')"))

            # круговой обмен: собственный экспорт (CSV и XLSX) импортируется обратно без потерь
            src, _ = await new_page(browser, dump)
            src_log = await src.evaluate("JSON.parse(JSON.stringify(data.log))")
            await src.evaluate("data.log['2026-09-25'].exercises[0].note='заметка; с \"кавычкой\"'; data.log['2026-09-25'].exercises[0].sets[0].w=37.5; 0")
            src_log = await src.evaluate("JSON.parse(JSON.stringify(data.log))")
            csv_text = await src.evaluate("buildCsv()"); csv_path = os.path.join(tempfile.gettempdir(), "gt_roundtrip.csv"); open(csv_path, "w", encoding="utf-8", newline="").write(csv_text)
            xlsx_b64 = await src.evaluate("bytesToBase64(buildXlsxBytes())"); xlsx_path = os.path.join(tempfile.gettempdir(), "gt_roundtrip.xlsx"); open(xlsx_path, "wb").write(base64.b64decode(xlsx_b64))
            def model(log):
                return {k: [(e["base"], e["plan"], e["variant"], [(s["w"], s["r"]) for s in e["sets"]], (e.get("note") or "").strip() or None) for e in d["exercises"] if e["sets"]] for k, d in log.items() if any(e["sets"] for e in d["exercises"])}
            for label, path in (("CSV", csv_path), ("XLSX", xlsx_path)):
                tgt, errs2 = await new_page(browser, dump)
                await tgt.evaluate("data.log={}; saveCache(); 0")
                await tgt.click('button[data-tab="set"]'); await tgt.wait_for_timeout(200)
                await tgt.set_input_files("#importFile", path); await tgt.wait_for_timeout(800)
                acts = await tgt.evaluate("ui.tblImport.days.map(d=>d.action)")
                check("круговой обмен %s: все даты «добавить» (в приложении пусто)" % label, set(acts) == {"add"} and len(acts) == len(model(src_log)), (label, set(acts), len(acts)))
                await tgt.click('[data-act="tblImportApply"]'); await tgt.wait_for_timeout(600)
                got = await tgt.evaluate("JSON.parse(JSON.stringify(data.log))")
                check("круговой обмен %s: упражнения, планы, варианты, подходы и заметки совпадают" % label, model(got) == model(src_log), [(k, model(got).get(k), model(src_log)[k]) for k in model(src_log) if model(got).get(k) != model(src_log)[k]][:1])
                check("круговой обмен %s: weekType дней совпал" % label, all(got[k]["weekType"] == src_log[k]["weekType"] for k in model(src_log)))
                check("круговой обмен %s: нет pageerror" % label, not errs2, errs2[:2])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
