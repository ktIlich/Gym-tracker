"""Фаза 11, задача 3: похожие шаблоны — удаление и объединение. На реальном дампе и синтетических шаблонах."""
import asyncio, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")

def tpl(tid, name, items, up=0, **kw):
    """items: [(name, plan, vars|None, alt|None)] или [[...],[...]] для суперсета"""
    blocks = []
    for it in items:
        group = it if isinstance(it, list) else [it]
        blocks.append({"type": "superset" if len(group) > 1 else "single", "items": [dict({"name": n, "plan": p}, **({"vars": v, "alt": a or 1} if v else {})) for n, p, v, a in group]})
    return dict({"id": tid, "name": name, "title": name, "up": up, "blocks": blocks}, **kw)

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8"))
    dump["cfg"]["onboardingSeen"] = 1
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)

            # ================= реальные данные (3.5) =================
            seed(dump)
            page, errs = await open_tg(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            orig = {t["id"]: json.dumps(t["blocks"], sort_keys=True, ensure_ascii=False) for t in dump["templates"]}
            gr = await page.evaluate("findDupGroups().map(g=>({keep:g.keep.id, drop:g.drop.map(t=>t.id).sort(), n:g.members.length}))")
            check("3.5: группы на реальных данных — 3 (пн / ср / пт), 4 шаблона в каждой", len(gr) == 3 and all(g["n"] == 4 for g in gr), gr)
            check("3.5: остаются 5ik1ivc (Жимовая грудь), fb6c7mc (Тяговая спина), ypfivy5 (Ноги)", sorted(g["keep"] for g in gr) == ["5ik1ivc", "fb6c7mc", "ypfivy5"], gr)
            check("3.5: остальные 9 старых шаблонов — под удаление", sum(len(g["drop"]) for g in gr) == 9)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(300)
            check("3.4: «Порядок в данных → Похожие шаблоны · 3»", "· 3" in await page.locator('[data-act="hygOpen"][data-screen="dups"]').inner_text())
            await page.click('[data-act="hygOpen"][data-screen="dups"]'); await page.wait_for_timeout(300)
            txt = await page.inner_text("#app")
            check("3.4: пояснение вверху — текст из ТЗ", "Найдены копии одного тренировочного дня. Одинаковые будут удалены, недостающие упражнения — добавлены в последний использованный шаблон." in txt)
            check("3.5: у всех групп упражнения совпадают — блока «Будут добавлены в основной» нет (добавлений нет)", await page.locator(".dup-extra").count() == 0 and "Будут добавлены" not in txt)
            last = {}
            for k, d in dump["log"].items():
                last[(d.get("title") or "").strip().lower()] = max(last.get((d.get("title") or "").strip().lower(), ""), k)
            cards = await page.evaluate("[...document.querySelectorAll('.dup-group')].map(c=>c.querySelector('.dup-keep').textContent.replace(/\\s+/g,' ').trim())")
            def md(k): return k[8:10] + "." + k[5:7]
            want = {"Жимовая грудь (пн)": md(last["жимовая грудь (пн)"]), "Тяговая спина (ср)": md(last["тяговая спина (ср)"]), "Ноги (пт)": md(last["ноги (пт)"])}
            check("3.4: «Остаётся: <имя> (последняя тренировка ДД.ММ)» — дата последней тренировки с таким title", all(("Остаётся: %s (последняя тренировка %s)" % (n, d)) in cards for n, d in want.items()), (cards, want))
            sels = await page.evaluate("[...document.querySelectorAll('.dup-main')].map(s=>[...s.options].map(o=>o.textContent))")
            check("3.4: можно выбрать другой основной шаблон из группы (select с 4 вариантами, высота ≥ 44px)", all(len(o) == 4 for o in sels) and await page.evaluate("[...document.querySelectorAll('.dup-main')].every(s=>s.getBoundingClientRect().height>=43.5)"))
            btns = await page.evaluate("[...document.querySelectorAll('.dup-group')].map(c=>[...c.querySelectorAll('button')].map(b=>b.textContent.trim()))")
            check("3.4: на карточке кнопки «Объединить» и «Пропустить», внизу «Объединить все»", all(b == ["Объединить", "Пропустить"] for b in btns) and "Объединить все (3)" in await page.inner_text("#tplMergeAll"))
            # пропустить
            await page.locator(".dup-group").first.locator('[data-act="tplMergeSkip"]').click(); await page.wait_for_timeout(150)
            check("3.4: «Пропустить» скрывает группу (без изменений данных)", await page.locator(".dup-group").count() == 2 and await page.evaluate("data.templates.length") == 12)
            await page.evaluate("ui.tplSkip={}; render(); 0")
            # объединить все — с подтверждением, снимок
            await page.evaluate("data.cfg.schedule={mon:'b7hqs5l'}; 0")
            await page.click("#tplMergeAll"); await page.wait_for_timeout(200)
            check("3.4: «Объединить все» — с подтверждением (диалог), «Отмена» ничего не делает", "Объединить все?" in await page.inner_text("#dlg"))
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(150)
            check("3.4: после «Отмена» шаблонов по-прежнему 12", await page.evaluate("data.templates.length") == 12)
            await page.click("#tplMergeAll"); await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(900)
            check("3.4: тост «Удалено 9 шаблонов, добавлено 0 упражнений»", (await page.inner_text("#toastMsg")) == "Удалено 9 шаблонов, добавлено 0 упражнений", await page.inner_text("#toastMsg"))
            ids = sorted(await page.evaluate("data.templates.map(t=>t.id)"))
            check("3.5: остались ровно 5ik1ivc, fb6c7mc, ypfivy5", ids == ["5ik1ivc", "fb6c7mc", "ypfivy5"], ids)
            now = {t["id"]: json.dumps(t["blocks"], sort_keys=True, ensure_ascii=False) for t in await page.evaluate("data.templates")}
            check("3.5: структура, варианты и суперсеты трёх основных не изменились", all(now[i] == orig[i] for i in now), [i for i in now if now[i] != orig[i]])
            check("3.3: ссылка на удалённый шаблон b7hqs5l перенаправлена на основной 5ik1ivc", await page.evaluate("data.cfg.schedule.mon") == "5ik1ivc")
            pre = json.loads(await page.evaluate("localStorage.getItem('tst_pretplmerge')"))
            check("3.4: снимок K(\"pretplmerge\") сохранён до применения (12 шаблонов)", len(pre["templates"]) == 12)
            check("3.3: в облаке остались 3 шаблона, удалённые убраны", sorted(k for k in STORE if k.startswith("tst_tpl_")) == ["tst_tpl_5ik1ivc", "tst_tpl_fb6c7mc", "tst_tpl_ypfivy5"])
            await page.click('[data-act="hygClose"]'); await page.click('button[data-tab="day"]'); await page.wait_for_timeout(200)
            check("баннер о лишних шаблонах исчез", await page.locator("#dupBanner").count() == 0)

            # ================= группировка (3.1) =================
            seed(dump); page2, e2 = await open_tg(browser)
            await page2.goto(BASE + "/test/index.html"); await page2.wait_for_timeout(2500)
            setT = lambda tpls, log=None: page2.evaluate("(a)=>{ data.templates=a[0].map(normalizeTpl); data.log=a[1]||{}; ui.tplMain={}; ui.tplOff={}; ui.tplSkip={}; 0 }", [tpls, log or {}])
            groups = lambda: page2.evaluate("findDupGroups().map(g=>g.members.map(t=>t.id).sort())")
            A = ("A", "3х10", None, None); B = ("B", "3х10", None, None); C = ("C", "3х10", None, None); D = ("D", "3х10", None, None); E = ("E", "3х10", None, None)
            await setT([tpl("t1", "Жимовая грудь (пн)", [A, B]), tpl("t2", "Жимовая (пн)", [C, D])])
            check("3.1: совпадает нормализованное имя (первое слово без «(пн)») → одна группа, даже при разных упражнениях", await groups() == [["t1", "t2"]], await groups())
            await setT([tpl("t1", "Альфа", [A, B, C]), tpl("t2", "Бета", [A, B, C, D])])
            check("3.1: Жаккар 3/4 = 0.75 ≥ 0.6 → группа", await groups() == [["t1", "t2"]])
            await setT([tpl("t1", "Альфа", [A, B, C]), tpl("t2", "Бета", [A, B, C, D, E])])
            check("3.1: Жаккар ровно 3/5 = 0.6 → группа", await groups() == [["t1", "t2"]])
            await setT([tpl("t1", "Альфа", [A, B, C]), tpl("t2", "Бета", [A, B, ("X", "3х10", None, None), ("Y", "3х10", None, None), ("Z", "3х10", None, None)])])
            check("3.1: Жаккар 2/6 < 0.6 и разные имена → не группа; группы из одного не показываются", await groups() == [])
            await setT([tpl("t1", "Голень", [("Голень стоя", "3х10", None, None)]), tpl("t2", "Икры", [("Голень стоя (икры)", "3х10", None, None)])])
            check("3.1: множества base считаются после алиасов («Голень стоя» = «Голень стоя (икры)»)", await groups() == [["t1", "t2"]])
            await setT([tpl("t1", "Ноги", [A]), tpl("t2", "ноги (пт)", [B]), tpl("t3", "Спина", [C])])
            check("3.1: имя — без учёта регистра; «Спина» не попала", await groups() == [["t1", "t2"]])

            # ================= основной шаблон (3.2) =================
            mainof = lambda: page2.evaluate("findDupGroups().map(g=>g.keep.id)")
            day = lambda d, title: {d: {"title": title, "up": 1, "exercises": [{"id": "e", "name": "A", "base": "A", "plan": None, "variant": None, "sets": [{"w": 1, "r": 1}]}]}}
            await setT([tpl("t1", "Ноги А", [A, B], up=500), tpl("t2", "Ноги Б", [A, B], up=100)], day("2026-09-01", "Ноги Б"))
            check("3.2: основной — шаблон, чьё имя совпадает с title самой поздней тренировки (несмотря на меньший up)", await mainof() == ["t2"], await mainof())
            await setT([tpl("t1", "Ноги (пт)", [A, B], up=100), tpl("t2", "Ноги (пт)", [A, B], up=200), tpl("t3", "Ноги (пт)", [A, B])], day("2026-09-01", "Ноги (пт)"))
            check("3.2: несколько шаблонов с совпавшим именем → максимальный up (нет up = 0)", await mainof() == ["t2"], await mainof())
            await setT([tpl("t1", "Ноги А", [A, B], up=100), tpl("t2", "Ноги Б", [A, B], up=300)], day("2026-09-01", "Другое"))
            check("3.2: совпадений нет → максимальный up", await mainof() == ["t2"])
            await setT([tpl("t1", "Ноги А", [A, B], up=100), tpl("t2", "Ноги Б", [A, B])], {**day("2026-09-01", "Ноги Б"), **day("2026-09-10", "Ноги А")})
            check("3.2: берётся самая поздняя тренировка (10.09 «Ноги А» позже 01.09 «Ноги Б»)", await mainof() == ["t1"])

            # ================= объединение (3.3) =================
            seed(dump); page3, e3 = await open_tg(browser)
            await page3.goto(BASE + "/test/index.html"); await page3.wait_for_timeout(2500)
            def setup(tpls, log=None):
                return page3.evaluate("""async (a)=>{ for(const t of data.templates.slice()) { data.templates=data.templates.filter(x=>x.id!==t.id); unpersistTpl(t.id); }
                    data.templates=a[0].map(normalizeTpl); for(const t of data.templates) persistTpl(t); data.log=a[1]||{}; ui.tplMain={}; ui.tplOff={}; ui.tplSkip={}; data.cfg.dupSnooze=null; ui.tab='set'; ui.hygiene='dups'; render(); return 0; }""", [tpls, log or {}])
            FL = lambda n, v=None, a=None: (n, "2х8-12", v, a)
            main = tpl("m", "Ноги (пт)", [FL("Сгибания голени", ["Лёжа"], 3), FL("Приседания в гакк-машине"), FL("Болгарские приседания"), [FL("Разгибания сидя"), FL("Сведения ног сидя")], FL("Голень стоя (икры)")], up=900)
            copy = tpl("c", "Ноги", [FL("Сгибания голени", ["лёжа", "Сидя"], 7), FL("Приседания в гакк-машине"), FL("Болгарские приседания"), ("Выпады", "3х10-12", ["Гантели", "Штанга"], 2), FL("Разгибания сидя"), FL("Сведения ног сидя"), ("Подъём на носки", "4х15", None, None)], up=100)
            await setup([main, copy], day("2026-09-01", "Ноги (пт)"))
            txt = await page3.inner_text("#app")
            check("3.3/3.4: карточка показывает «Будут добавлены в основной»: «Выпады» и «Подъём на носки» с чекбоксами (по умолчанию отмечены)", await page3.locator(".dup-extra input:checked").count() == 2 and "Выпады" in txt and "Подъём на носки" in txt)
            await page3.locator(".dup-extra", has_text="Подъём на носки").locator("input").uncheck(); await page3.wait_for_timeout(100)
            await page3.click('[data-act="tplMergeGo"]'); await page3.wait_for_timeout(700)
            m = await page3.evaluate("data.templates.find(t=>t.id==='m')")
            flat = [[it["name"] for it in b["items"]] for b in m["blocks"]]
            check("3.5: «Выпады» встали в основной сразу после «Болгарских приседаний»", flat == [["Сгибания голени"], ["Приседания в гакк-машине"], ["Болгарские приседания"], ["Выпады"], ["Разгибания сидя", "Сведения ног сидя"], ["Голень стоя (икры)"]], flat)
            vb = m["blocks"][3]
            check("3.3: добавленное упражнение — одиночным блоком со своими plan и vars", vb["type"] == "single" and vb["items"][0]["plan"] == "3х10-12" and vb["items"][0]["vars"] == ["Гантели", "Штанга"], vb)
            check("3.3: снятый чекбокс — упражнение не добавлено; суперсет основного не перестроен", not any("Подъём" in n for b in flat for n in b) and m["blocks"][4]["type"] == "superset")
            it0 = m["blocks"][0]["items"][0]
            check("3.3: у совпадающего упражнения сохранены plan основного, vars объединены без дублей (Лёжа/лёжа → одно, +Сидя), alt основного не меняется", it0["plan"] == "2х8-12" and it0["vars"] == ["Лёжа", "Сидя"] and it0["alt"] == 3, it0)
            check("3.3: копия удалена (локально и в облаке), основной записан в облако с новым блоком",
                  await page3.evaluate("data.templates.map(t=>t.id)") == ["m"] and "tst_tpl_c" not in STORE and "Выпады" in STORE["tst_tpl_m"])
            check("3.4: тост «Удалено 1 шаблон, добавлено 1 упражнение»", (await page3.inner_text("#toastMsg")) == "Удалено 1 шаблон, добавлено 1 упражнение", await page3.inner_text("#toastMsg"))
            # позиция: нет предшествующего совпавшего → в конец; цепочка добавлений сохраняет порядок
            c2 = tpl("c2", "Ноги копия", [("Новое1", "3х8", None, None), FL("Сгибания голени"), ("Новое2", "3х8", None, None), ("Новое3", "3х8", None, None), [FL("Разгибания сидя"), ("Новое4", "3х8", None, None)]], up=50)
            m2 = tpl("m2", "Ноги (пт)", [FL("Сгибания голени"), [FL("Разгибания сидя"), FL("Сведения ног сидя")], FL("Голень стоя (икры)")], up=900)
            await setup([m2, c2], day("2026-09-01", "Ноги (пт)"))
            await page3.click('[data-act="tplMergeGo"]'); await page3.wait_for_timeout(600)
            fl = await page3.evaluate("data.templates.find(t=>t.id==='m2').blocks.map(b=>b.items.map(i=>i.name).join('+'))")
            check("3.3: без предшествующего совпадения — в конец; цепочка — подряд после якоря; после члена суперсета — после всего блока суперсета",
                  fl == ["Сгибания голени", "Новое2", "Новое3", "Разгибания сидя+Сведения ног сидя", "Новое4", "Голень стоя (икры)", "Новое1"], fl)
            # подмножество → просто удаляется
            await setup([tpl("m3", "Ноги (пт)", [FL("A1"), FL("A2"), FL("A3")], up=900), tpl("c3", "Ноги", [FL("A1"), FL("A2")], up=1)], day("2026-09-01", "Ноги (пт)"))
            check("3.3: упражнения копии — подмножество основного → блока «добавить» нет", await page3.locator(".dup-extra").count() == 0)
            before = await page3.evaluate("JSON.stringify(data.templates.find(t=>t.id==='m3'))")
            await page3.click('[data-act="tplMergeGo"]'); await page3.wait_for_timeout(500)
            check("3.3: подмножество → шаблон удалён, основной без изменений", await page3.evaluate("data.templates.map(t=>t.id)") == ["m3"] and await page3.evaluate("JSON.stringify(data.templates[0])") == before)
            # смена основного в группе
            await setup([tpl("p", "Ноги (пт)", [FL("A1"), FL("A2")], up=900), tpl("q", "Ноги", [FL("A1"), FL("A2"), FL("A9")], up=1)], day("2026-09-01", "Ноги (пт)"))
            await page3.select_option(".dup-main", "q"); await page3.wait_for_timeout(200)
            keep = await page3.inner_text(".dup-keep")
            check("3.4: выбор другого основного пересчитывает карточку («Остаётся: Ноги», удаляется «Ноги (пт)», добавлений нет)", "Остаётся: Ноги" in keep and await page3.locator(".dup-drop").inner_text() != "" and await page3.locator(".dup-extra").count() == 0, keep)
            check("нет pageerror", not (errs or e2 or e3), (errs[:1], e2[:1], e3[:1]))
            await page3.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_merge.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
