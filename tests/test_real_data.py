"""Задачи 1–2 на реальных данных: ../current_data.json (дамп v2.9.1 от 30.09.2026). Файл вне репозитория."""
import asyncio, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, open_page, check, RESULTS, REPO
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8"))
    STORE.clear()
    STORE["tst_cfg"] = json.dumps(dump["cfg"])
    for tpl in dump["templates"]: STORE["tst_tpl_" + tpl["id"]] = json.dumps(tpl)
    for k, day in dump["log"].items(): STORE["tst_w_" + k] = json.dumps(day)
    orig = dump["log"]
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            ctx = await browser.new_context(viewport={"width": 390, "height": 900})
            await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
            t, logs = await open_page(ctx, "/test/index.html")
            await t.wait_for_timeout(2500)
            log = await t.evaluate("JSON.parse(JSON.stringify(data.log))")
            ntpl = await t.evaluate("data.templates.length"); real_ids = {x["id"] for x in dump["templates"]}; have = set(await t.evaluate("data.templates.map(x=>x.id)"))
            check("реальные данные: загружено 35 дней и все 12 шаблонов (+3 шаблона по умолчанию от пустого локального кэша — поведение v2)", len(log) == 35 and real_ids <= have and ntpl == 15, (len(log), ntpl))

            # ---- миграция
            exs = [(k, e) for k, d in log.items() for e in d["exercises"]]
            check("миграция: у всех %d упражнений есть base/plan/variant, name собран из полей" % len(exs),
                  all(e.get("base") and "plan" in e and "variant" in e and e["name"] == e["base"] + (" (%s)" % e["plan"] if e["plan"] else "") + (" · %s" % e["variant"] if e["variant"] else "") for _, e in exs))
            check("миграция: даты, подходы, id, ss, note, up, weekType не тронуты",
                  all(log[k]["up"] == orig[k].get("up") and log[k].get("weekType") == orig[k].get("weekType") and
                      [(e["id"], e["sets"], e.get("ss"), e.get("note")) for e in log[k]["exercises"]] == [(e["id"], e["sets"], e.get("ss"), e.get("note")) for e in orig[k]["exercises"]] for k in orig))
            cloud_ok = all(all(e.get("base") for e in json.loads(STORE["tst_w_" + k])["exercises"]) and json.loads(STORE["tst_w_" + k]).get("up") == orig[k].get("up") for k in orig)
            check("миграция: все мигрированные дни дописаны в облако, up прежний", cloud_ok)
            check("миграция: повторный migrateAll — без изменений", await t.evaluate("(()=>{ const a=JSON.stringify(data); migrateAll(data); return a===JSON.stringify(data); })()"))
            bases = {}
            for k, e in exs: bases.setdefault(e["base"], set()).add((e["variant"], e["plan"]))
            check("алиасы на реальных данных: «Голень стоя» → «Голень стоя (икры)» (одна база)", "Голень стоя" not in bases and "Голень стоя (икры)" in bases)
            check("алиасы: гиперэкстензия с «на» → «акцент разгибатели и поясница»", "Гиперэкстензия, акцент на разгибатели и поясница" not in bases and "Гиперэкстензия, акцент разгибатели и поясница" in bases)
            check("алиасы: «Сгибания голени сидя или стоя» → «Сгибания голени»", "Сгибания голени сидя или стоя" not in bases and {v for v, _ in bases["Сгибания голени"]} == {None, "Лёжа", "стоя"}, bases.get("Сгибания голени"))
            check("алиасы: гакк — одна база, варианты «Спиной» и «лицом» (как в шаблоне ypfivy5)", {v for v, _ in bases["Приседания в гакк-машине"]} == {"Спиной", "лицом"} and not any(b.startswith("Приседания в гаке") for b in bases), bases.get("Приседания в гакк-машине"))
            check("варианты «Молотков»: «Свободный» и «блок» — написание из свежего шаблона", {v for v, _ in bases["Молотки, свободный вес или блок"]} == {None, "Свободный", "блок"}, bases.get("Молотки, свободный вес или блок"))

            # ---- Прогресс: линии
            async def group_view(name):
                await t.evaluate("ui.tab='prg'; ui.progMode='ex'; progEx=%s; render(); 0" % json.dumps(name))
                return await t.evaluate("""(()=>{ const it=[...document.querySelectorAll('.prog-ex-item')].find(x=>x.querySelector('.prog-ex-open')); if(!it) return null;
                    return { lines:[...it.querySelectorAll('svg polyline')].map(p=>p.dataset.series||'*'), legend:[...it.querySelectorAll('.series-legend span')].map(s=>s.textContent.trim()),
                             dates:[...it.querySelectorAll('.hist-table tr td:first-child')].map(x=>x.textContent), note:(it.querySelector('.note')||{}).textContent||'' }; })()""")
            v = await group_view("Голень стоя (икры)")
            check("Прогресс: «Голень стоя (икры)» — одна линия (без легенды), 9 тренировок, начиная с июля", v and v["legend"] == [] and v["lines"] == ["*"] and "Тренировок: 9" in v["note"] and "30.07" in v["dates"], v)
            v = await group_view("Гиперэкстензия, акцент разгибатели и поясница")
            check("Прогресс: «Гиперэкстензия, акцент разгибатели и поясница» — одна линия, 8 тренировок", v and v["legend"] == [] and "Тренировок: 8" in v["note"], v)
            v = await group_view("Сгибания с гантелями стоя по 1 руке")
            check("Прогресс: «Сгибания с гантелями…» — две линии: «Блок» и «без варианта»", v and sorted(v["lines"]) == ["Блок", "без варианта"], v)
            v = await group_view("Молотки, свободный вес или блок")
            check("Прогресс: «Молотки» — линии «Свободный» и «блок» (+ одиночная точка без варианта 05.08)", v and sorted(v["lines"]) == ["Свободный", "блок"] and sorted(v["legend"]) == sorted(["Свободный", "блок", "без варианта"]), v)

            # ---- findPrev на реальных данных (текущий день — 30.09, в логе его нет)
            await t.evaluate("curDate='2026-09-30'; 0")
            fp = lambda b, vr, wt="work", ms=None: t.evaluate("(()=>{ const r=findPrev(%s,%s,%s,%s); return r&&{date:r.date,str:r.str,step:r.step}; })()" % (json.dumps(b), json.dumps(vr), json.dumps(wt), json.dumps(ms)))
            r = await fp("Сгибания с гантелями стоя по 1 руке", "Блок")
            check("приёмка: «Сгибания…», «Блок» → 23.09: 45×12", r and r["date"] == "2026-09-23" and r["str"].startswith("45×12") and r["step"] == 1, r)
            r = await fp("Сгибания с гантелями стоя по 1 руке", None)
            check("приёмка: «Сгибания…» без варианта → 26.08: 15×12 (не 23.09/45 кг)", r and r["date"] == "2026-08-26" and r["str"].startswith("15×12") and r["step"] == 1, r)
            r = await fp("Молотки, свободный вес или блок", "Свободный")
            check("приёмка: «Молотки», «Свободный» → 26.08: 15×12", r and r["date"] == "2026-08-26" and r["str"].startswith("15×12"), r)
            r = await fp("Молотки, свободный вес или блок", "блок")
            check("приёмка: «Молотки», «блок» → 23.09: 45×12", r and r["date"] == "2026-09-23" and r["str"].startswith("45×12"), r)
            check("рекомендации: только шаги 1–2 (у «Молотков» без варианта есть 05.08 rest, но не рабочая → шаг 3 → нет)", await fp("Молотки, свободный вес или блок", "Новый", "work", 2) is None)

            # ---- переключение варианта туда-обратно на текущем дне: записи других дат не меняются
            await t.evaluate("ui.tab='day'; delete data.log[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); 0")
            before = await t.evaluate("JSON.stringify(Object.fromEntries(Object.entries(data.log).filter(([k])=>k!==curDate)))")
            ids = await t.evaluate("data.log[curDate].exercises.map(e=>({id:e.id,b:e.base,v:e.variant}))")
            mol = [e for e in ids if e["b"].startswith("Молотки")][0]
            cards = "[...document.querySelectorAll('.card')].filter(c=>c.querySelector('.ex-name')).map(c=>({n:c.querySelector('.ex-name').textContent,l:[...c.querySelectorAll('.ex-last')].map(e=>e.textContent)}))"
            c0 = await t.evaluate("render(); " + cards)
            for vv in ("Свободный", "блок", "Свободный", mol["v"] or ""):
                await t.evaluate("doAction('applyVariant',{id:'%s',variant:%s}); 0" % (mol["id"], json.dumps(vv)))
            after = await t.evaluate("JSON.stringify(Object.fromEntries(Object.entries(data.log).filter(([k])=>k!==curDate)))")
            c1 = await t.evaluate(cards)
            check("реальные данные: переключение варианта туда-обратно — записи других дат (JSON) не изменились", before == after)
            others = lambda cs: [c for c in cs if not c["n"].startswith("Молотки")]
            check("реальные данные: у остальных упражнений дня «прошлая тренировка» не изменилась", others(c0) == others(c1))
            check("нет pageerror", not [l for l in logs if l.startswith("pageerror")], logs[:3])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
