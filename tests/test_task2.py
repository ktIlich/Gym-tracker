"""Задача 2: прошлая тренировка и рекомендации с учётом варианта (findPrev)."""
import asyncio, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, open_page, check, RESULTS, REPO
from playwright.async_api import async_playwright

def ex(i, base, plan, variant, sets):
    name = base + (" (%s)" % plan if plan else "") + (" · %s" % variant if variant else "")
    return {"id": "x%s" % i, "name": name, "base": base, "plan": plan, "variant": variant, "sets": sets}

CUR = "2026-09-30"
DAYS = {
    "2026-08-26": ("work", [ex(1, "Сгибания с гантелями стоя по 1 руке", "2х8-15", None, [{"w": 15, "r": 12}]),
                            ex(2, "Молотки", "2х8-15", "Свободный", [{"w": 15, "r": 12}]),
                            ex(3, "Жим", "3х8-12", None, [{"w": 60, "r": 8}])]),
    "2026-09-16": ("rest", [ex(4, "Сгибания с гантелями стоя по 1 руке", "2х8-15", "Блок", [{"w": 30, "r": 10}])]),
    "2026-09-23": ("work", [ex(5, "Сгибания с гантелями стоя по 1 руке", "2х8-15", "Блок", [{"w": 45, "r": 12}]),
                            ex(6, "Молотки", "2х8-15", "Блок", [{"w": 45, "r": 12}]),
                            ex(7, "Жим", "2х8-12", None, [{"w": 62.5, "r": 8}])]),   # другой план — не мешает
    "2026-10-05": ("work", [ex(8, "Молотки", "2х8-15", "Свободный", [{"w": 99, "r": 9}])]),   # будущее — не учитывается
}

def seed():
    STORE.clear()
    STORE["tst_cfg"] = json.dumps({"cycle": {"workWeeks": 2, "restWeeks": 1, "anchorDate": "2026-07-01"}, "up": 1000, "schema": 2, "onboardingSeen": 1})
    STORE["tst_tpl_a"] = json.dumps({"id": "a", "name": "Тяга", "title": "Тяга", "up": 1, "blocks": [
        {"type": "single", "items": [{"name": "Молотки", "plan": "2х8-15", "vars": ["Свободный", "Блок"], "alt": 1}]}]})
    for d, (wt, exs) in DAYS.items():
        STORE["tst_w_" + d] = json.dumps({"title": "Д", "up": 100, "weekType": wt, "exercises": exs})

async def main():
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            ctx = await browser.new_context(viewport={"width": 390, "height": 900})
            await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
            seed()
            t, logs = await open_page(ctx, "/test/index.html")
            await t.wait_for_timeout(1500)
            await t.evaluate("curDate='%s'; ui.tab='day'; 0" % CUR)
            fp = lambda b, v, wt, ms=None: t.evaluate("(()=>{ const r=findPrev(%s,%s,%s,%s); return r&&{date:r.date,str:r.str,step:r.step,variant:r.variant}; })()" % (json.dumps(b), json.dumps(v), json.dumps(wt), json.dumps(ms)))

            # ---- приёмка из ТЗ
            r = await fp("Сгибания с гантелями стоя по 1 руке", "Блок", "work")
            check("«Сгибания…», вариант «Блок» → прошлая рабочая 23.09: 45×12 (шаг 1)", r == {"date": "2026-09-23", "str": "45×12", "step": 1, "variant": "Блок"}, r)
            r = await fp("Сгибания с гантелями стоя по 1 руке", None, "work")
            check("«Сгибания…» без варианта → 26.08: 15×12 (шаг 3 не сработал, есть запись без варианта)", r and r["date"] == "2026-08-26" and r["str"] == "15×12" and r["step"] == 1, r)
            r = await fp("Молотки", "Свободный", "work")
            check("«Молотки», «Свободный» → 26.08: 15×12", r and (r["date"], r["str"], r["step"]) == ("2026-08-26", "15×12", 1), r)
            r = await fp("Молотки", "блок", "work")
            check("«Молотки», «блок» (регистр) → 23.09: 45×12", r and (r["date"], r["str"], r["step"]) == ("2026-09-23", "45×12", 1), r)
            # ---- порядок шагов
            r = await fp("Сгибания с гантелями стоя по 1 руке", "Свободный", "work")
            check("шаг 2: варианта «Свободный» нет → запись без варианта 26.08, а не более новый «Блок»", r and (r["date"], r["step"]) == ("2026-08-26", 2), r)
            r = await fp("Молотки", None, "work")
            check("шаг 3: у записей только варианты → самый свежий другой вариант «Блок» (23.09)", r and (r["date"], r["step"], r["variant"]) == ("2026-09-23", 3, "Блок"), r)
            check("тип недели раздельно: рабочая ≠ отдых", (await fp("Сгибания с гантелями стоя по 1 руке", "Блок", "rest")) == {"date": "2026-09-16", "str": "30×10", "step": 1, "variant": "Блок"})
            check("даты строго раньше текущей: будущая 05.10 и текущая не учитываются", (await fp("Молотки", "Свободный", "work"))["date"] == "2026-08-26" and (await fp("Молотки", "Свободный", "work", 2))["date"] == "2026-08-26")
            check("план не влияет на поиск: «Жим» 3х8-12 и 2х8-12 — одно упражнение (23.09: 62.5×8)", (await fp("Жим", None, "work"))["str"] in ("62.5×8", "62,5×8"), await fp("Жим", None, "work"))
            check("максимум шага 2: шаг 3 отбрасывается (для рекомендаций)", await fp("Молотки", None, "work", 2) is None and await fp("Молотки", "Новый", "work", 2) is None)

            # ---- рекомендации: только шаги 1–2
            rec = lambda b, v, plan: t.evaluate("calcRec({base:%s,plan:%s,variant:%s,name:'x',sets:[]},false)" % (json.dumps(b), json.dumps(plan), json.dumps(v)))
            check("рекомендация «Молотки»/«Блок»: от 45×12 (→ 45×14)", await rec("Молотки", "Блок", "2х8-15") == {"w": 45, "r": 14}, await rec("Молотки", "Блок", "2х8-15"))
            check("рекомендация «Молотки»/«Свободный»: от 15×12 (→ 15×14)", await rec("Молотки", "Свободный", "2х8-15") == {"w": 15, "r": 14})
            check("рекомендация: только шаг 3 (гантели 15 кг vs блок 45 кг) → не показывается", await rec("Молотки", None, "2х8-15") is None and await rec("Молотки", "Новый", "2х8-15") is None)
            check("рекомендация: шаг 2 (записи без варианта) допустима", await rec("Сгибания с гантелями стоя по 1 руке", "Свободный", "2х8-15") == {"w": 15, "r": 14})
            check("рекомендация разгрузки: тоже по варианту (Блок → от 45×12)", (await t.evaluate("calcRec({base:'Молотки',plan:'2х8-15',variant:'Блок',name:'x',sets:[]},true)"))["w"] <= 45)

            # ---- карточка: подпись «другой вариант», отсутствие рекомендации
            def card(name_base, variant):
                return ("data.log[curDate]={title:'Д',up:1,weekType:'work',exercises:[newEx(%s,'2х8-15',%s)]}; render(); "
                        "return ({last:[...document.querySelectorAll('.ex-last')].map(e=>e.textContent), rec:!!document.querySelector('.rec-btn')})") % (json.dumps(name_base), json.dumps(variant))
            c = await t.evaluate("(()=>{ " + card("Молотки", None) + " })()")
            check("карточка: шаг 3 — «Рабочая 23.09 (другой вариант: Блок): 45×12», рекомендации нет", any("23.09" in x and "другой вариант: Блок" in x and "45×12" in x for x in c["last"]) and not c["rec"], c)
            c = await t.evaluate("(()=>{ " + card("Молотки", "Блок") + " })()")
            check("карточка: тот же вариант — без «другой вариант», рекомендация есть", any("23.09" in x and "45×12" in x and "другой вариант" not in x for x in c["last"]) and c["rec"], c)

            # ---- баг: смена варианта не должна менять ничего кроме своей записи (и не влиять на другие карточки)
            await t.evaluate("data.log[curDate]={title:'Д',up:1,weekType:'work',exercises:[newEx('Сгибания с гантелями стоя по 1 руке','2х8-15','Блок'),newEx('Молотки','2х8-15','Блок'),newEx('Жим','2х8-12',null)]}; render(); 0")
            cards = "[...document.querySelectorAll('.card')].filter(c=>c.querySelector('.ex-name')).map(c=>({n:c.querySelector('.ex-name').textContent,l:[...c.querySelectorAll('.ex-last')].map(e=>e.textContent),r:(c.querySelector('.rec-btn')||{}).textContent||''}))"
            other_before = await t.evaluate("JSON.stringify(Object.fromEntries(Object.entries(data.log).filter(([k])=>k!==curDate)))")
            cards_before = await t.evaluate(cards)
            exid = await t.evaluate("getDay().exercises[0].id")
            await t.evaluate("doAction('applyVariant',{id:'%s',variant:'Свободный'}); 0" % exid)
            mid = await t.evaluate(cards)
            check("смена варианта: у переключённого упражнения «прошлая» обновилась (шаг 2: 26.08 15×12)", any("26.08" in x and "15×12" in x for x in mid[0]["l"]) and mid[0]["l"] != cards_before[0]["l"], mid[0])
            check("смена варианта: у остальных упражнений отображение прошлой тренировки и рекомендаций не изменилось", mid[1:] == cards_before[1:], (mid[1:], cards_before[1:]))
            await t.evaluate("doAction('applyVariant',{id:'%s',variant:'Блок'}); 0" % exid)
            back = await t.evaluate(cards)
            other_after = await t.evaluate("JSON.stringify(Object.fromEntries(Object.entries(data.log).filter(([k])=>k!==curDate)))")
            check("переключение туда-обратно: записи других дат — JSON до и после равны", other_before == other_after)
            check("переключение туда-обратно: карточки как были", back == cards_before)
            e0 = await t.evaluate("getDay().exercises[0]")
            check("смена варианта меняет только variant и name текущей записи", e0["variant"] == "Блок" and e0["name"] == "Сгибания с гантелями стоя по 1 руке (2х8-15) · Блок" and e0["sets"] == [])
            check("нет pageerror", not [l for l in logs if l.startswith("pageerror")], logs[:3])
            await t.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_prev.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
