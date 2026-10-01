"""Задача 3: варианты в редакторе шаблона (чипы, «+ вариант»), alt и выбор варианта. На реальном дампе ../current_data.json."""
import asyncio, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, open_page, check, RESULTS, REPO
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8"))
    dump["cfg"]["onboardingSeen"] = 1
    STORE.clear()
    STORE["tst_cfg"] = json.dumps(dump["cfg"])
    for tpl in dump["templates"]: STORE["tst_tpl_" + tpl["id"]] = json.dumps(tpl)
    for k, day in dump["log"].items(): STORE["tst_w_" + k] = json.dumps(day)
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            ctx = await browser.new_context(viewport={"width": 390, "height": 900})
            await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
            t, logs = await open_page(ctx, "/test/index.html")
            await t.wait_for_timeout(2500)
            await t.evaluate("curDate='2026-09-30'; 0")

            # ---- alt: семантика и нормализация индекса
            r = await t.evaluate("""[variantIndex(0,4,2),variantIndex(3,4,2),variantIndex(4,4,2),variantIndex(8,4,2),variantIndex(5,1,2),variantIndex(7,0,3),variantIndex(7,'x',3),variantIndex(7,-5,3),
                                     variantIndex(9,4,1),variantIndex(9,4,0),variantIndex(-3,1,2), pickVariant({vars:[]},5), pickVariant({},5), pickVariant({vars:['A','B'],alt:4},4)]""")
            check("alt = период «каждые N тренировок»: idx = floor(count/alt) по кругу", r[:5] == [0, 0, 1, 0, 1], r[:5])
            check("alt: индекс всегда нормализован (alt 0/мусор/отрицательный → шаг 1; n=1 → 0; отрицательный счёт не выходит за диапазон)", r[5:8] == [1, 1, 1] and r[8] == 0 and r[10] in (0, 1), r[5:])
            check("alt: при n=0 вариант равен null", r[9] == -1 and r[11] is None and r[12] is None and r[13] == "B", r[9:])
            n_mol = await t.evaluate("countBase('Молотки, свободный вес или блок')")
            check("счёт тренировок — по base, без учёта плана и варианта (8 дней «Молотков» до 30.09)", n_mol == 8, n_mol)
            await t.evaluate("ui.tab='day'; delete data.log[curDate]; delete ui.drafts[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); 0")
            mol = await t.evaluate("getDay().exercises.find(e=>e.base.startsWith('Молотки'))")
            check("applyTemplate: «Молотки» (alt 4, 2 варианта, 8 тренировок) → idx 0 = «Свободный»", mol["variant"] == "Свободный" and mol["name"] == "Молотки, свободный вес или блок (2х8-15) · Свободный", mol)
            vert = await t.evaluate("getDay().exercises.find(e=>e.base.startsWith('Вертикальная'))")
            check("вариант из одного значения валиден: «Прямая изогнутая» подставляется", vert["variant"] == "Прямая изогнутая", vert)

            # ---- редактор шаблона
            await t.evaluate("ui.tab='tpl'; ui.editTpl=JSON.parse(JSON.stringify(data.templates.find(x=>x.id==='fb6c7mc'))); render(); 0")
            find_item = lambda name: t.evaluate("(()=>{ const t=ui.editTpl; for(let k=0;k<t.blocks.length;k++) for(let i=0;i<t.blocks[k].items.length;i++) if(t.blocks[k].items[i].name.startsWith(%s)) return [k,i]; })()" % json.dumps(name))
            k, i = await find_item("Молотки")
            box = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k, i)))
            chips = await box.locator(".et-chip").all_inner_texts()
            check("редактор: варианты — чипы «Свободный», «блок»; строки через запятую нет", [c.strip() for c in chips] == ["Свободный", "блок"] and await box.locator('[data-et="vars"]').count() == 0, chips)
            check("редактор: у чипов кнопка-крестик, зона ≥ 44px", await box.locator(".chip-x").count() == 2 and await box.evaluate("e=>[...e.querySelectorAll('.chip-x,.et-vadd,.et-chip,input[id^=etv-]')].every(x=>x.getBoundingClientRect().height>=43.5&&(!x.classList.contains('chip-x')||x.getBoundingClientRect().width>=43.5))"))
            check("редактор: чип «Сейчас по очереди» подсвечен (Свободный) и подпись", await box.locator(".et-chip.on").inner_text() == "Свободный" and "Сейчас по очереди: Свободный" in await box.inner_text())
            check("редактор: кнопка «+ вариант» и поле ввода", await box.locator('.et-vadd').count() == 1 and await box.locator('input[id^="etv-"]').count() == 1)
            inp = box.locator('input[id^="etv-"]')
            # пусто
            await box.locator(".et-vadd").click(); await t.wait_for_timeout(150)
            check("«+ вариант»: пустое значение не добавляется", await t.evaluate("ui.editTpl.blocks[%d].items[%d].vars.length" % (k, i)) == 2 and "Введите" in await t.inner_text("#toastMsg"))
            # дубль без учёта регистра, дубль через алиас
            await inp.fill("СВОБОДНЫЙ"); await box.locator(".et-vadd").click(); await t.wait_for_timeout(150)
            check("«+ вариант»: дубль без учёта регистра не добавляется", await t.evaluate("ui.editTpl.blocks[%d].items[%d].vars.length" % (k, i)) == 2 and "уже есть" in await t.inner_text("#toastMsg"))
            box = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k, i))); inp = box.locator('input[id^="etv-"]')
            await inp.fill("свободный вес"); await box.locator(".et-vadd").click(); await t.wait_for_timeout(150)
            check("«+ вариант»: дубль через алиас («свободный вес» → «Свободный») не добавляется", await t.evaluate("ui.editTpl.blocks[%d].items[%d].vars.length" % (k, i)) == 2)
            # добавить по одному (кнопка и Enter)
            box = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k, i))); inp = box.locator('input[id^="etv-"]')
            await inp.fill("  Канат  "); await box.locator(".et-vadd").click(); await t.wait_for_timeout(150)
            box = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k, i)))
            await box.locator('input[id^="etv-"]').fill("Резина"); await box.locator('input[id^="etv-"]').press("Enter"); await t.wait_for_timeout(150)
            vars_now = await t.evaluate("ui.editTpl.blocks[%d].items[%d].vars" % (k, i))
            check("«+ вариант»: добавляет по одному (кнопка и Enter), значение обрезано", vars_now == ["Свободный", "блок", "Канат", "Резина"], vars_now)
            check("после добавления фокус в поле ввода (можно добавлять подряд)", await t.evaluate("document.activeElement&&document.activeElement.id==='etv-%d-%d'" % (k, i)))
            # удалить
            box = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k, i)))
            await box.locator(".et-chip").nth(2).locator(".chip-x").click(); await t.wait_for_timeout(150)
            check("крестик на чипе удаляет вариант", await t.evaluate("ui.editTpl.blocks[%d].items[%d].vars" % (k, i)) == ["Свободный", "блок", "Резина"])
            # alt
            box = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k, i)))
            await box.locator("input.alt").fill("2"); await box.locator("input.alt").press("Tab"); await t.wait_for_timeout(150)
            check("«чередовать каждые N тр.»: alt меняется (2) и не ниже 1", await t.evaluate("ui.editTpl.blocks[%d].items[%d].alt" % (k, i)) == 2)
            await t.evaluate("(()=>{ const it=ui.editTpl.blocks[%d].items[%d]; it.alt=0; 0 })(); 0" % (k, i))
            # сохранение
            await t.evaluate("doAction('etSave',{}); 0"); await t.wait_for_timeout(600)
            saved = await t.evaluate("data.templates.find(x=>x.id==='fb6c7mc').blocks.flatMap(b=>b.items).find(i=>i.name.startsWith('Молотки'))")
            cloud = json.loads(STORE["tst_tpl_fb6c7mc"])
            cit = [it for b in cloud["blocks"] for it in b["items"] if it["name"].startswith("Молотки")][0]
            check("сохранение: варианты и alt (нормализован ≥1) записаны в шаблон и в облако", saved["vars"] == ["Свободный", "блок", "Резина"] and saved["alt"] == 1 and cit["vars"] == saved["vars"], (saved, cit))
            # единственный вариант — не трогать
            await t.evaluate("ui.tab='tpl'; ui.editTpl=JSON.parse(JSON.stringify(data.templates.find(x=>x.id==='fb6c7mc'))); render(); 0")
            k2, i2 = await find_item("Вертикальная тяга")
            box2 = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k2, i2)))
            check("единственный вариант «Прямая изогнутая»: один чип, без изменений", [c.strip() for c in await box2.locator(".et-chip").all_inner_texts()] == ["Прямая изогнутая"])
            await t.evaluate("doAction('etSave',{}); 0"); await t.wait_for_timeout(300)
            check("сохранение шаблона не трогает вариант из одного значения", (await t.evaluate("data.templates.find(x=>x.id==='fb6c7mc').blocks.flatMap(b=>b.items).find(i=>i.name.startsWith('Вертикальная'))")) ["vars"] == ["Прямая изогнутая"])
            # удаление всех вариантов → vars/alt убираются, панель остаётся
            await t.evaluate("ui.tab='tpl'; ui.editTpl=JSON.parse(JSON.stringify(data.templates.find(x=>x.id==='fb6c7mc'))); render(); 0")
            k3, i3 = await find_item("Сгибания с гантелями")
            b3 = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k3, i3)))
            await b3.locator(".chip-x").first.click(); await t.wait_for_timeout(150)
            it3 = await t.evaluate("ui.editTpl.blocks[%d].items[%d]" % (k3, i3))
            b3 = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k3, i3)))
            check("удалён последний вариант: vars и alt убираются, поле «+ вариант» остаётся", "vars" not in it3 and "alt" not in it3 and await b3.locator(".et-vadd").count() == 1, it3)
            # удаление варианта, выбранного «по очереди»: индекс всегда в диапазоне
            await t.evaluate("ui.tab='tpl'; ui.editTpl=JSON.parse(JSON.stringify(data.templates.find(x=>x.id==='fb6c7mc'))); render(); 0")
            k, i = await find_item("Молотки")
            box = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k, i)))
            await box.locator(".et-chip.on .chip-x").click(); await t.wait_for_timeout(150)
            box = t.locator(".et-item").filter(has=t.locator('[data-et="name"][data-k="%d"][data-i="%d"]' % (k, i)))
            check("удалён выбранный по очереди вариант: подсвечен ровно один чип из оставшихся", await box.locator(".et-chip").count() == 2 and await box.locator(".et-chip.on").count() == 1)
            await t.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_tpl_vars.png"))
            check("нет pageerror", not [l for l in logs if l.startswith("pageerror")], logs[:3])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
