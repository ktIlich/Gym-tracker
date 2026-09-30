"""Задача 1: модель записи в логе (base/plan/variant), алиасы, миграция log-fields, экран «Алиасы»."""
import asyncio, json, os, subprocess, sys, time, copy
sys.path.insert(0, os.path.dirname(__file__))
import test_step0 as H
from test_step0 import STORE, WRITES, LOG, MOCK, cs_handler, log_handler, open_page, check, RESULTS, BASE, REPO
from playwright.async_api import async_playwright

def old_ex(i, name, sets, **kw):
    e = {"id": "e%s" % i, "name": name, "sets": sets}; e.update(kw); return e

def seed():
    STORE.clear()
    STORE["tst_cfg"] = json.dumps({"cycle": {"workWeeks": 2, "restWeeks": 1, "anchorDate": "2026-07-01"}, "up": 1000, "schema": 1})
    STORE["tst_tpl_a"] = json.dumps({"id": "a", "name": "Ноги", "title": "Ноги", "up": 1, "blocks": [
        {"type": "single", "items": [{"name": "Сгибания голени", "plan": "2х8-12", "vars": ["Лёжа", "Сидя"], "alt": 1}]},
        {"type": "single", "items": [{"name": "Молотки", "plan": "2х8-15", "vars": ["Свободный", "Блок"], "alt": 1}]}]})
    days = {
        "2026-07-06": (100, [old_ex(1, "Голень стоя (3х10-20)", [{"w": 20, "r": 15}], note="икры болели"),
                             old_ex(2, "Гиперэкстензия, акцент на разгибатели и поясница (3х12-15)", [{"w": 10, "r": 12}], ss="s1")]),
        "2026-07-20": (200, [old_ex(3, "Сгибания голени сидя или стоя (2х8-12)", [{"w": 30, "r": 10}]),
                             old_ex(4, "Приседания в гаке лицом назад (2х8-12)", [{"w": 60, "r": 8}]),
                             old_ex(5, "Приседания в гаке лицом к тренажёру (2х8-12)", [{"w": 70, "r": 8}])]),
        "2026-08-03": (300, [old_ex(6, "Голень стоя (икры) (3х10-20)", [{"w": 25, "r": 15}]),
                             old_ex(7, "Гиперэкстензия, акцент разгибатели и поясница (3х12-15)", [{"w": 12, "r": 12}]),
                             old_ex(8, "Молотки (2х8-15) · СВОБОДНЫЙ ВЕС", [{"w": 15, "r": 12}])]),
        "2026-09-01": (400, [old_ex(9, "Сгибания голени (2х8-12) · Лёжа", [{"w": 35, "r": 10}]),
                             old_ex(10, "Голень стоя (икры) (3х10-20)", [{"w": 30, "r": 15}])]),
    }
    days["2026-08-17"] = (500, [old_ex(11, "Молотки (2х8-15) · Свободный", [{"w": 15, "r": 12}]), old_ex(12, "Сгибания с гантелями стоя по 1 руке (2х8-15)", [{"w": 15, "r": 12}])])
    days["2026-08-24"] = (510, [old_ex(13, "Молотки (2х8-15) · свободный вес", [{"w": 16, "r": 12}]), old_ex(14, "Сгибания с гантелями стоя по 1 руке (2х8-15)", [{"w": 16, "r": 12}])])
    days["2026-09-08"] = (520, [old_ex(15, "Молотки (2х8-15) · блок", [{"w": 45, "r": 12}]), old_ex(16, "Сгибания с гантелями стоя по 1 руке (3х8-12) · Блок", [{"w": 45, "r": 12}])])
    days["2026-09-15"] = (530, [old_ex(17, "Молотки (2х8-15) · Блок", [{"w": 47.5, "r": 10}]), old_ex(18, "Сгибания с гантелями стоя по 1 руке (2х8-15) · блок", [{"w": 47.5, "r": 10}])])
    for d, (up, exs) in days.items():
        STORE["tst_w_" + d] = json.dumps({"title": "Д", "up": up, "weekType": "work", "exercises": exs})
    return days

async def main():
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            ctx = await browser.new_context(viewport={"width": 390, "height": 800})
            await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
            days = seed()
            orig = {d: json.loads(STORE["tst_w_" + d]) for d in days}
            t, logs = await open_page(ctx, "/test/index.html")
            await t.wait_for_timeout(1500)

            # ---- 1.1 разбор и сборка name
            r = await t.evaluate("""[ 'Сгибания голени (2х8-12) · Лёжа', 'Голень стоя (икры) (3х10-20)', 'Жим', 'Жим (3 x 8 - 12) · Блок',
                                      'Отведения (пек-дек) (икры)', 'Присед (3х10-20) (икры)' ].map(parseExName)""")
            check("разбор: вариант по последнему « · », план — последняя скобка NхM",
                  r[0] == {"base": "Сгибания голени", "plan": "2х8-12", "variant": "Лёжа"} and r[1] == {"base": "Голень стоя (икры)", "plan": "3х10-20", "variant": None}
                  and r[2] == {"base": "Жим", "plan": None, "variant": None} and r[3] == {"base": "Жим", "plan": "3х8-12", "variant": "Блок"}, r)
            check("разбор: скобка не вида NхM остаётся в имени", r[4] == {"base": "Отведения (пек-дек) (икры)", "plan": None, "variant": None} and r[5]["base"] == "Присед (3х10-20) (икры)", r[4:])
            check("сборка: name = base + (plan) + · variant", await t.evaluate("composeName('A','2х8-12','Б')==='A (2х8-12) · Б' && composeName('A',null,null)==='A' && composeName('A',null,'Б')==='A · Б'"))

            # ---- 1.2 алиасы
            r = await t.evaluate("""[ 'Голень стоя', 'Гиперэкстензия, акцент на разгибатели и поясница', 'Сгибания голени сидя или стоя',
                 'Приседания в гаке лицом назад', 'Приседания в гаке лицом к тренажёру', 'голень СТОЯ ' ].map(n=>{ const a=applyAliases(n,null); return [a.base,a.variant]; })""")
            check("алиасы: начальное наполнение (5 пар) применяется к base",
                  r[0] == ["Голень стоя (икры)", None] and r[1] == ["Гиперэкстензия, акцент разгибатели и поясница", None] and r[2] == ["Сгибания голени", None]
                  and r[3][0] == "Приседания в гакк-машине" and r[4][0] == "Приседания в гакк-машине" and r[3][1] != r[4][1] and r[3][1] and r[4][1] and r[5][0] == "Голень стоя (икры)", r)
            check("алиасы: гакк «назад» → вариант «Спиной», «к тренажёру» → «лицом» (как в шаблоне)", (r[3][1], r[4][1]) == ("Спиной", "лицом"), r[3:5])
            check("алиасы вариантов: «свободный вес» → «Свободный» (без учёта регистра и пробелов)", await t.evaluate("canonVariant(' Свободный ВЕС ')==='Свободный' && canonVariant('Лёжа')==='Лёжа' && canonVariant('  ')===null"))
            check("cfg.aliases / cfg.variantAliases заполнены по умолчанию", await t.evaluate("Object.keys(data.cfg.aliases).length>=5 && data.cfg.variantAliases['свободный вес']==='Свободный'"))

            # ---- 1.3 миграция log-fields
            check("миграция: log-fields зарегистрирована, needs по записи (нет base)", await t.evaluate("MIGRATIONS.some(m=>m.id==='log-fields') && MIGRATIONS[0].needs({exercises:[{name:'x'}]},'day')===true && MIGRATIONS[0].needs({exercises:[{name:'x',base:'x'}]},'day')===false"))
            mig = await t.evaluate("JSON.parse(JSON.stringify(data.log))")
            ok_fields = all(e.get("base") and "plan" in e and "variant" in e and e["name"] == (e["base"] + (" (" + e["plan"] + ")" if e["plan"] else "") + (" · " + e["variant"] if e["variant"] else ""))
                            for d in mig.values() for e in d["exercises"])
            check("миграция: у всех упражнений base/plan/variant, name пересобран", ok_fields, mig["2026-07-06"])
            E = {e["id"]: e for d in mig.values() for e in d["exercises"]}
            check("миграция: «Голень стоя (3х10-20)» → base «Голень стоя (икры)», plan 3х10-20", E["e1"]["base"] == "Голень стоя (икры)" and E["e1"]["plan"] == "3х10-20" and E["e1"]["name"] == "Голень стоя (икры) (3х10-20)" == E["e6"]["name"], E["e1"])
            check("миграция: гиперэкстензия — одна каноническая база", E["e2"]["base"] == E["e7"]["base"] == "Гиперэкстензия, акцент разгибатели и поясница", (E["e2"]["base"], E["e7"]["base"]))
            check("миграция: «Сгибания голени сидя или стоя» → «Сгибания голени», варианта нет", E["e3"]["base"] == "Сгибания голени" and E["e3"]["variant"] is None and E["e9"]["variant"] == "Лёжа", (E["e3"], E["e9"]))
            check("миграция: гакк-приседания — база одна, варианты Спиной / лицом", E["e4"]["base"] == E["e5"]["base"] == "Приседания в гакк-машине" and {E["e4"]["variant"], E["e5"]["variant"]} == {"Спиной", "лицом"}, (E["e4"], E["e5"]))
            check("миграция: вариант «СВОБОДНЫЙ ВЕС» → «Свободный»", E["e8"]["variant"] == "Свободный" and E["e8"]["name"] == "Молотки (2х8-15) · Свободный", E["e8"])
            same = True
            for d, dd in orig.items():
                for a, b in zip(dd["exercises"], mig[d]["exercises"]):
                    same &= a["sets"] == b["sets"] and a["id"] == b["id"] and a.get("ss") == b.get("ss") and a.get("note") == b.get("note")
                same &= dd["up"] == mig[d]["up"] and dd["title"] == mig[d]["title"] and dd["weekType"] == mig[d]["weekType"]
            check("миграция: даты, подходы, ss, заметки, id, up не тронуты", same)
            cloud = {d: json.loads(STORE["tst_w_" + d]) for d in days}
            check("миграция: мигрированные дни дописаны в облако (base есть), up прежний", all(all(e.get("base") for e in cloud[d]["exercises"]) and cloud[d]["up"] == orig[d]["up"] for d in days), cloud["2026-07-06"])
            r = await t.evaluate("(()=>{ const a=JSON.stringify(data); const r=migrateAll(data); return a===JSON.stringify(data) && r.days.length===0 && r.snapshot===null; })()")
            check("миграция: повторный migrateAll ничего не меняет", r)
            names = await t.evaluate("""(()=>{ const s={}; for(const k of Object.keys(data.log)) for(const e of data.log[k].exercises){ if(e.base.startsWith('Голень стоя')||e.base.startsWith('Гиперэкстензия')) (s[e.base]=s[e.base]||new Set()).add(e.name); }
                return Object.fromEntries(Object.entries(s).map(([k,v])=>[k,[...v]])); })()""")
            check("приёмка: «Голень стоя (икры)» и «Гиперэкстензия, акцент разгибатели…» — по одному имени с июля", list(names) == ["Голень стоя (икры)", "Гиперэкстензия, акцент разгибатели и поясница"] and all(len(v) == 1 for v in names.values()), names)
            await t.evaluate("ui.tab='prg'; render(); 0")
            prog = await t.evaluate("[...document.querySelectorAll('.prog-ex-btn')].map(b=>b.textContent)")
            n_gol = len([x for x in prog if "Голень стоя" in x]); n_hyp = len([x for x in prog if "Гиперэкстензия" in x])
            check("приёмка: на экране «Прогресс» одна линия голени и одна гиперэкстензии", n_gol == 1 and n_hyp == 1, prog)

            # ---- графики «Прогресса»: группа по base, линия на variant
            async def group_view(name):
                await t.evaluate("ui.tab='prg'; ui.progMode='ex'; progEx=%s; render(); 0" % json.dumps(name))
                return await t.evaluate("""(()=>{ const it=[...document.querySelectorAll('.prog-ex-item')].find(x=>x.querySelector('.prog-ex-open'));
                    if(!it) return null; return { lines:[...it.querySelectorAll('svg polyline')].map(p=>p.dataset.series||''), legend:[...it.querySelectorAll('.series-legend span')].map(s=>s.textContent.trim()),
                      note:(it.querySelector('.note')||{}).textContent||'' , svgs:it.querySelectorAll('svg').length }; })()""")
            v = await group_view("Молотки")
            check("«Молотки»: две линии — «Свободный» и «Блок» (регистр и написание из шаблона)", v and sorted(v["lines"]) == ["Блок", "Свободный"] and sorted(v["legend"]) == ["Блок", "Свободный"], v)
            await t.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_series.png"))
            v = await group_view("Сгибания с гантелями стоя по 1 руке")
            check("«Сгибания с гантелями…»: две линии — с вариантом «Блок» и без варианта (план не влияет)", v and sorted(v["lines"]) == ["Блок", "без варианта"] and sorted(v["legend"]) == ["Блок", "без варианта"], v)
            v = await group_view("Голень стоя (икры)")
            check("«Голень стоя (икры)»: одна линия с июля (3 тренировки: 06.07, 03.08, 01.09)", v and v["legend"] == [] and v["svgs"] == 1 and "Тренировок: 3" in v["note"], v)
            v = await group_view("Гиперэкстензия, акцент разгибатели и поясница")
            check("«Гиперэкстензия…»: одна линия, 2 тренировки", v and v["legend"] == [] and "Тренировок: 2" in v["note"], v)
            listing = await t.evaluate("[...document.querySelectorAll('.prog-ex-item')].map(x=>x.dataset.name)")
            check("список упражнений «Прогресса»: по одной строке на base (нет дублей по плану/варианту)", len(listing) == len(set(n.lower() for n in listing)) and "Молотки" in listing and not any("(3х" in n or "(2х" in n for n in listing), listing)
            await t.evaluate("ui.tab='day'; render(); 0")

            # ---- канонический вариант — как в шаблоне
            check("вариант: написание берётся из шаблона (блок → Блок, свободный вес → Свободный)", await t.evaluate("canonVariant('блок','Молотки')==='Блок' && canonVariant('свободный вес','Молотки')==='Свободный' && canonVariant('лёжа','Сгибания голени')==='Лёжа'"))

            # ---- новые записи создаются сразу с base/plan/variant
            await t.evaluate("ui.tab='day'; ui.aliasScreen=false; curDate=toKey(new Date()); delete data.log[curDate]; render(); 0")
            before_log = await t.evaluate("JSON.stringify(data.log)")
            await t.evaluate("applyTemplate(data.templates.find(t=>t.id==='a')); 0")
            today = await t.evaluate("JSON.parse(JSON.stringify(data.log[curDate].exercises))")
            check("шаблон → запись: base/plan/variant и name из полей", today[0]["base"] == "Сгибания голени" and today[0]["plan"] == "2х8-12" and today[0]["variant"] in ("Лёжа", "Сидя")
                  and today[0]["name"] == "Сгибания голени (2х8-12) · " + today[0]["variant"] and today[1]["base"] == "Молотки" and today[1]["plan"] == "2х8-15", today)
            await t.fill("#newEx", "Пресс (4х12-20)"); await t.click('[data-act="addEx"]'); await t.wait_for_timeout(200)
            press = await t.evaluate("data.log[curDate].exercises.at(-1)")
            check("добавление вручную: имя разбирается на base/plan", press["base"] == "Пресс" and press["plan"] == "4х12-20" and press["variant"] is None and press["name"] == "Пресс (4х12-20)", press)
            await t.fill("#newEx", "Голень стоя (3х10-20)"); await t.click('[data-act="addEx"]'); await t.wait_for_timeout(200)
            check("добавление вручную: алиас применяется", await t.evaluate("data.log[curDate].exercises.at(-1).name")  == "Голень стоя (икры) (3х10-20)")
            exid = today[0]["id"]
            await t.evaluate("doAction('applyVariant',{id:'%s',variant:'свободный вес'}); 0" % exid)
            e0 = await t.evaluate("data.log[curDate].exercises[0]")
            after_log = await t.evaluate("(()=>{const l=JSON.parse(JSON.stringify(data.log)); delete l[curDate]; return JSON.stringify(l);})()")
            check("смена варианта: меняются variant и name записи, base/plan прежние, алиас варианта применён", e0["variant"] == "Свободный" and e0["name"] == "Сгибания голени (2х8-12) · Свободный" and e0["base"] == "Сгибания голени" and e0["plan"] == "2х8-12", e0)
            before_other = json.dumps(json.loads(before_log), sort_keys=True); after_other = json.dumps(json.loads(after_log), sort_keys=True)
            check("смена варианта: записи других дат не изменились", before_other == after_other)
            await t.evaluate("doAction('applyVariant',{id:'%s',variant:''}); 0" % exid)
            check("смена варианта: «без варианта» → variant null, name без « · »", await t.evaluate("(e=>e.variant===null && e.name==='Сгибания голени (2х8-12)')(data.log[curDate].exercises[0])"))
            await t.evaluate("doAction('copyLast',{}); 0") if False else None

            # ---- экран «Алиасы»
            await t.click('button[data-tab="set"]'); await t.wait_for_timeout(300)
            check("настройки: кнопка «Алиасы»", await t.locator('[data-act="aliasOpen"]').count() == 1)
            await t.click('[data-act="aliasOpen"]'); await t.wait_for_timeout(300)
            rows_ex = await t.locator('.alias-row[data-kind="ex"]').count(); rows_var = await t.locator('.alias-row[data-kind="var"]').count()
            check("«Алиасы»: показаны пары упражнений (5) и вариантов (1)", rows_ex == 5 and rows_var == 1, (rows_ex, rows_var))
            big = await t.evaluate("[...document.querySelectorAll('.alias-row input, .alias-del')].every(e=>e.getBoundingClientRect().height>=44-0.5)")
            check("«Алиасы»: зоны нажатия ≥ 44px", big, await t.evaluate("[...document.querySelectorAll('.alias-row input, .alias-del')].map(e=>Math.round(e.getBoundingClientRect().height)).join()"))
            # добавить пару → пересчёт лога, в т.ч. записей, у которых base уже есть
            await t.evaluate("data.log['2026-08-10']={title:'Т',up:5,weekType:'work',exercises:[{id:'z1',name:'Тест старый (2х10)',base:'Тест старый',plan:'2х10',variant:null,sets:[{w:1,r:1}]}]}; saveCache(); 0")
            await t.fill("#alias-old-ex", "тест СТАРЫЙ"); await t.fill("#alias-new-ex", "Тест новый"); await t.click('[data-act="aliasAdd"][data-kind="ex"]'); await t.wait_for_timeout(700)
            z = await t.evaluate("data.log['2026-08-10']")
            check("алиас добавлен: лог пересчитан отдельной функцией (base уже был), name пересобран", z["exercises"][0]["base"] == "Тест новый" and z["exercises"][0]["name"] == "Тест новый (2х10)", z)
            check("алиас добавлен: up изменённого дня обновлён, подходы целы", z["up"] > 5 and z["exercises"][0]["sets"] == [{"w": 1, "r": 1}], z)
            check("алиас добавлен: день и cfg записаны в облако", "Тест новый" in STORE.get("tst_w_2026-08-10", "") and "тест СТАРЫЙ" in STORE["tst_cfg"], STORE.get("tst_w_2026-08-10"))
            check("«Алиасы»: строка добавилась в список (6)", await t.locator('.alias-row[data-kind="ex"]:not(.alias-add)').count() == 6)
            # дубль отклоняется
            await t.fill("#alias-old-ex", "ТЕСТ старый"); await t.fill("#alias-new-ex", "Что-то"); await t.click('[data-act="aliasAdd"][data-kind="ex"]'); await t.wait_for_timeout(200)
            check("«Алиасы»: дубль (без учёта регистра) отклонён", await t.locator('.alias-row[data-kind="ex"]:not(.alias-add)').count() == 6 and "уже есть" in await t.inner_text("#toastMsg"))
            # изменить пару
            row = t.locator('.alias-row[data-kind="ex"]:not(.alias-add)').nth(5)
            await row.locator("input").nth(1).fill("Тест итог"); await row.locator("input").nth(1).press("Tab"); await t.wait_for_timeout(700)
            check("«Алиасы»: изменение пары применяется к логу повторно", await t.evaluate("data.log['2026-08-10'].exercises[0].name")  == "Тест итог (2х10)" and await t.evaluate("data.cfg.aliases['тест СТАРЫЙ']==='Тест итог'"), await t.evaluate("JSON.stringify([data.log['2026-08-10'].exercises[0].name, data.cfg.aliases])"))
            # удалить
            await t.locator('[data-act="aliasDel"][data-kind="ex"]').nth(5).click(); await t.wait_for_timeout(500)
            check("«Алиасы»: удаление пары", await t.locator('.alias-row[data-kind="ex"]:not(.alias-add)').count() == 5 and await t.evaluate("!('тест СТАРЫЙ' in data.cfg.aliases)") and "тест СТАРЫЙ" not in STORE["tst_cfg"])
            # алиас варианта
            await t.evaluate("data.log['2026-08-11']={title:'Т',up:5,weekType:'work',exercises:[{id:'z2',name:'Жим (2х10) · Блочный',base:'Жим',plan:'2х10',variant:'Блочный',sets:[]}]}; saveCache(); 0")
            await t.fill("#alias-old-var", "блочный"); await t.fill("#alias-new-var", "Блок"); await t.click('[data-act="aliasAdd"][data-kind="var"]'); await t.wait_for_timeout(700)
            check("алиас варианта: variant записи пересчитан, name пересобран", await t.evaluate("(e=>e.variant==='Блок'&&e.name==='Жим (2х10) · Блок')(data.log['2026-08-11'].exercises[0])"))
            await t.click('[data-act="aliasClose"]'); await t.wait_for_timeout(200)
            check("«Алиасы»: «Назад» возвращает в настройки", await t.locator('[data-act="aliasOpen"]').count() == 1)
            check("нет pageerror", not [l for l in logs if l.startswith("pageerror")], logs[:3])
            await t.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_alias.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
