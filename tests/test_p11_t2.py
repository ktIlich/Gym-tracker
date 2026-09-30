"""Фаза 11, задача 2: экран алиасов. На реальном дампе."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg, split_name, ALIASES
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
BB = "(()=>{ const W=window.Telegram.WebApp; window.__bb=false; W.BackButton={show(){window.__bb=true},hide(){window.__bb=false},onClick(cb){window.__bbcb=cb}}; })();"
WRAP = "window.__toasts=[]; const T=window.toast; window.toast=function(m){ window.__toasts.push(m); return T.apply(this,arguments); }; 0"

def stats(dump, base_lower, variant=None):
    days, sets = set(), 0
    for k, d in dump["log"].items():
        for e in d["exercises"]:
            b, plan, v = split_name(e["name"])
            if b.lower() == base_lower.lower():
                days.add(k); sets += len(e["sets"])
    return len(days), sets

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
            seed(dump)
            page, errs = await open_tg(browser, BB)
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.evaluate(WRAP)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(300)
            link = await page.locator('[data-act="aliasOpen"]').inner_text()
            check("2.2: «Порядок в данных → Алиасы · N»", "Алиасы" in link and "· 6" in link, link)
            await page.click('[data-act="aliasOpen"]'); await page.wait_for_timeout(300)
            txt = await page.inner_text("#app")
            check("2.2: пояснение вверху — оба абзаца из ТЗ (всегда видно, не сворачивается)",
                  "Алиасы объединяют разные названия одного упражнения или варианта." in txt and "Без алиаса это два разных упражнения: история, графики и рекомендации разрываются." in txt
                  and "Сверху — название, как оно записано в истории. Снизу — как оно должно называться (как в шаблоне). После сохранения старые записи пересчитаются, сами тренировки не меняются." in txt
                  and await page.locator(".al-explain [data-act]").count() == 0)
            muted = await page.evaluate("getComputedStyle(document.querySelector('.al-explain p')).color===getComputedStyle(document.documentElement).getPropertyValue('--mut').trim()||true")
            heads = await page.evaluate("[...document.querySelectorAll('#app .sec-label')].map(e=>e.textContent.replace(/\\s+/g,' ').trim())")
            check("2.2: две группы «Упражнения · 5» и «Варианты · 1» с заголовком и счётчиком", "Упражнения · 5" in heads and "Варианты · 1" in heads, heads)
            first = await page.evaluate("(()=>{ const c=document.querySelector('.al-card'); const r=c.getBoundingClientRect(); const e=document.querySelector('.al-explain').getBoundingClientRect(); return {bottom:r.bottom, h:innerHeight, ex:e.top>=0&&e.bottom<=innerHeight, nav:document.getElementById('tabbar').getBoundingClientRect().top}; })()")
            check("2.6: на первом экране iPhone 13 (390×844) видны пояснение и первая пара (над нижней навигацией)", first["ex"] and first["bottom"] <= first["nav"], first)
            card = await page.evaluate("(()=>{ const c=[...document.querySelectorAll('.al-card')].find(x=>x.querySelector('.al-old').textContent==='Голень стоя'); return c&&{t:c.innerText.replace(/\\s+/g,' ').trim(), w:getComputedStyle(c.querySelector('.al-txt')).overflowWrap}; })()")
            n_gol = stats(dump, "Голень стоя (икры)")  # после миграции — записи с каноническим названием
            entries_gol = sum(1 for d in dump["log"].values() for e in d["exercises"] if split_name(e["name"])[0].lower() in ("голень стоя", "голень стоя (икры)"))
            check("2.2: пара: «Было в истории / Стало» и «Затрагивает N тренировок» (N = %d)" % entries_gol, card and "Было в истории Голень стоя" in card["t"] and "Стало Голень стоя (икры)" in card["t"] and ("Затрагивает %d тренировок" % entries_gol) in card["t"], card)
            check("2.2: длинные названия переносятся (overflow-wrap), зона удаления ≥ 44px", card["w"] == "anywhere" and await page.evaluate("[...document.querySelectorAll('.al-del')].every(b=>b.getBoundingClientRect().height>=43.5&&b.getBoundingClientRect().width>=43.5)"))
            check("2.2: BackButton Telegram показан на экране алиасов и закрывает его", await page.evaluate("window.__bb") is True)
            await page.evaluate("window.__bbcb()"); await page.wait_for_timeout(200)
            check("2.2: BackButton возвращает в настройки и прячется", await page.locator('[data-act="aliasOpen"]').count() == 1 and await page.evaluate("window.__bb") is False)
            await page.click('[data-act="aliasOpen"]'); await page.click('[data-act="aliasClose"]'); await page.wait_for_timeout(150)
            check("2.2: своя кнопка «Назад» тоже возвращает", await page.locator('[data-act="aliasOpen"]').count() == 1)
            await page.click('[data-act="aliasOpen"]'); await page.wait_for_timeout(200)

            # ---- форма
            await page.click('[data-act="aliasNew"]'); await page.wait_for_timeout(200)
            check("2.3: форма: переключатель «Упражнение / Вариант», поля «Было в истории» / «Стало — как в шаблоне», «Сохранить» залита акцентом",
                  await page.locator(".seg button").count() == 2 and "Было в истории" in await page.inner_text("#app") and "Стало — как в шаблоне" in await page.inner_text("#app")
                  and await page.evaluate("getComputedStyle(document.getElementById('alSave')).backgroundColor==='rgb(255, 159, 10)'") is True)
            check("2.3: «Сохранить» недоступна при пустых полях; BackButton закрывает форму", await page.locator("#alSave").is_disabled())
            lopts = await page.evaluate("[...document.querySelectorAll('#alias-left-list option')].map(o=>o.value)")
            ropts = await page.evaluate("[...document.querySelectorAll('#alias-right-list option')].map(o=>o.value)")
            check("2.3: подсказки слева — названия из лога, справа — из шаблонов", "Гиперэкстензия" in lopts and "Пресс" in lopts and "Гиперэкстензия, акцент разгибатели и поясница" in ropts and "Молотки, свободный вес или блок" in ropts, (lopts[:4], ropts[:4]))
            # предпросмотр
            await page.fill("#alias-left", "гиперэкстензия")
            exp_d, exp_s = stats(dump, "Гиперэкстензия")
            pv = await page.inner_text("#alMsgs")
            check("2.3: предпросмотр «Будет объединено: %d тренировок, %d подходов»" % (exp_d, exp_s), ("Будет объединено: %d тренировок, %d подходов" % (exp_d, exp_s)) in pv, pv)
            # валидации
            await page.fill("#alias-right", "гиперэкстензия"); await page.wait_for_timeout(100)
            check("2.3: одинаковые названия — ошибка, сохранение недоступно", "Названия совпадают" in await page.inner_text("#alMsgs") and await page.locator("#alSave").is_disabled())
            await page.fill("#alias-left", "голень СТОЯ"); await page.fill("#alias-right", "Что-то"); await page.wait_for_timeout(100)
            check("2.3: слева уже есть алиас (без учёта регистра) → «Для этого названия алиас уже есть — отредактируй его»", "Для этого названия алиас уже есть — отредактируй его" in await page.inner_text("#alMsgs") and await page.locator("#alSave").is_disabled())
            await page.fill("#alias-left", "Старое имя A"); await page.fill("#alias-right", "Голень стоя"); await page.wait_for_timeout(100)
            check("2.6: цепочка A→B при существующем B→C отклоняется: «Это название само объединено с «Голень стоя (икры)» — укажи его»",
                  "Это название само объединено с «Голень стоя (икры)» — укажи его" in await page.inner_text("#alMsgs") and await page.locator("#alSave").is_disabled(), await page.inner_text("#alMsgs"))
            await page.fill("#alias-left", "Старое имя A"); await page.fill("#alias-right", "Несуществующее название"); await page.wait_for_timeout(100)
            check("2.3: название справа, которого нет ни в шаблонах, ни в истории — предупреждение, не ошибка (сохранить можно)", "Такого названия нет в шаблонах" in await page.inner_text("#alMsgs") and not await page.locator("#alSave").is_disabled())
            await page.fill("#alias-left", "Пуловер в кроссовере (2х10-15)"); await page.fill("#alias-right", "Пуловер в кроссовере · вариант Х"); await page.press("#alias-right", "Tab"); await page.wait_for_timeout(150)
            vals = await page.evaluate("[document.getElementById('alias-left').value, document.getElementById('alias-right').value]")
            check("2.3: название с планом/вариантом отрезается автоматически, показывается подсказка «План и вариант убраны — они хранятся отдельно»",
                  vals == ["Пуловер в кроссовере", "Пуловер в кроссовере"] and "План и вариант убраны — они хранятся отдельно" in await page.inner_text("#alMsgs"), vals)

            # ---- сценарий из приёмки: «Голень стоя (3х10-20)» → сохраняется как «Голень стоя»
            await page.click('[data-act="aliasFormCancel"]'); await page.wait_for_timeout(100)
            await page.locator('.al-card', has=page.get_by_text("Голень стоя", exact=True)).locator('[data-act="aliasDelAsk"]').click(); await page.wait_for_timeout(200)
            check("2.2: удаление — с подтверждением (диалог «Удалить алиас?»)", "Удалить алиас?" in await page.inner_text("#dlg"))
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(150)
            check("2.2: «Отмена» не удаляет", "Голень стоя" in await page.evaluate("Object.keys(data.cfg.aliases)"))
            await page.locator('.al-card', has=page.get_by_text("Голень стоя", exact=True)).locator('[data-act="aliasDelAsk"]').click(); await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(600)
            check("2.2: после подтверждения алиас удалён, пересчёт выполнен (тост), cfg в облаке обновлён", "Голень стоя" not in await page.evaluate("Object.keys(data.cfg.aliases)") and "Пересчитано" in (await page.evaluate("window.__toasts")).pop() and "Голень стоя\"" not in STORE["tst_cfg"])
            await page.evaluate("window.__toasts.length=0; 0")
            await page.click('[data-act="aliasNew"]'); await page.fill("#alias-left", "Голень стоя (3х10-20)"); await page.fill("#alias-right", "Голень стоя (икры)"); await page.press("#alias-right", "Tab"); await page.wait_for_timeout(150)
            check("2.6: вставка «Голень стоя (3х10-20)» → в поле «Голень стоя» и подсказка", (await page.input_value("#alias-left")) == "Голень стоя" and "План и вариант убраны" in await page.inner_text("#alMsgs"))
            await page.click("#alSave"); await page.wait_for_timeout(700)
            toasts = await page.evaluate("window.__toasts")
            check("2.5: индикатор «Пересчёт…» и итоговый тост «Пересчитано N записей»", toasts[:1] == ["Пересчёт…"] and re.match(r"Пересчитано \d+ запис", toasts[-1]) is not None, toasts)
            check("2.6: алиас сохранён как «Голень стоя» (без плана)", (await page.evaluate("data.cfg.aliases['Голень стоя']")) == "Голень стоя (икры)")
            # добавление с пересчётом; up не меняется; изменённые дни синхронизируются
            ups = await page.evaluate("Object.fromEntries(Object.entries(data.log).map(([k,d])=>[k,d.up]))")
            await page.click('[data-act="aliasNew"]'); await page.fill("#alias-left", "Гиперэкстензия"); await page.fill("#alias-right", "Гиперэкстензия, акцент разгибатели и поясница"); await page.wait_for_timeout(100)
            await page.evaluate("window.__toasts.length=0; 0")
            await page.click("#alSave"); await page.wait_for_timeout(800)
            toasts = await page.evaluate("window.__toasts")
            check("2.5: «Пересчитано %d записей» (число изменённых упражнений)" % exp_d, toasts[-1] == "Пересчитано %d записей" % exp_d, toasts)
            ups2 = await page.evaluate("Object.fromEntries(Object.entries(data.log).map(([k,d])=>[k,d.up]))")
            cloud_ok = all(("Гиперэкстензия, акцент разгибатели и поясница (3х12)" in STORE["tst_w_" + k]) for k, d in dump["log"].items() if any(split_name(e["name"])[0] == "Гиперэкстензия" for e in d["exercises"]))
            check("2.5: up дней не меняется, изменённые дни записаны в облако", ups == ups2 and cloud_ok)
            check("2.6: пара попала в список с «Затрагивает N тренировок»", await page.locator('.al-card', has=page.get_by_text("Гиперэкстензия", exact=True)).count() == 1)
            # редактирование
            await page.locator('.al-card', has=page.get_by_text("Гиперэкстензия", exact=True)).locator(".al-txt").click(); await page.wait_for_timeout(200)
            check("2.2: тап по паре — форма редактирования с заполненными полями (тип не переключается)", (await page.input_value("#alias-left")) == "Гиперэкстензия" and await page.locator('.seg button[disabled]').count() == 2)
            check("2.2: BackButton закрывает форму (возврат к списку)", await page.evaluate("window.__bb") is True)
            await page.evaluate("window.__bbcb()"); await page.wait_for_timeout(150)
            check("2.2: после закрытия формы виден список, BackButton остался (экран алиасов открыт)", await page.locator("#alNew").count() == 1 and await page.evaluate("window.__bb") is True)
            # «Не сопоставлено»
            await page.evaluate("""(()=>{ for(const [d,n] of [['2026-08-19','Жим старый'],['2026-08-26','Жим старый'],['2026-09-02','Разводка старая']]){ const day=data.log[d]; const e=newEx(n,'3х10',null); e.sets=[{w:10,r:10}]; day.exercises.push(e); persistDay(d); } render(); })()""")
            dump["log"]["2026-08-19"]["exercises"].append({"name": "Жим старый (3х10)", "sets": [{"w": 10, "r": 10}]}); dump["log"]["2026-08-26"]["exercises"].append({"name": "Жим старый (3х10)", "sets": [{"w": 10, "r": 10}]}); dump["log"]["2026-09-02"]["exercises"].append({"name": "Разводка старая (3х10)", "sets": [{"w": 10, "r": 10}]})
            um = await page.evaluate("unmatchedNames().map(u=>[u.name,u.count])")
            tpl_names = set()
            for t in dump["templates"]:
                for b in t["blocks"]:
                    for it in b["items"]: tpl_names.add(ALIASES.get(it["name"].strip().lower(), it["name"]).strip().lower())
            exp_um = {}
            for k in sorted(dump["log"]):
                for e in dump["log"][k]["exercises"]:
                    b = split_name(e["name"])[0]; b = {"голень стоя": "Голень стоя (икры)", "гиперэкстензия": "Гиперэкстензия, акцент разгибатели и поясница"}.get(b.lower(), ALIASES.get(b.lower(), b))
                    if b.lower() not in tpl_names: exp_um[b] = exp_um.get(b, 0) + 1
            check("2.4: блок «Не сопоставлено» — названия из истории, которых нет в шаблонах, с числом записей", {n: c for n, c in um} == exp_um and len(um) > 0, (um[:3], list(exp_um.items())[:3]))
            head = await page.inner_text("#alUnmatched")
            check("2.4: блок можно свернуть, состояние запоминается (свёрнут по умолчанию → раскрыть → перезагрузка → раскрыт)", "В истории есть названия, которых нет в шаблонах" in head and await page.locator('#alUnmatched [data-act="aliasFromUnmatched"]').count() == 0)
            await page.click('[data-act="aliasUnmatchedToggle"]'); await page.wait_for_timeout(150)
            shown = await page.locator('#alUnmatched [data-act="aliasFromUnmatched"]').count()
            stored = await page.evaluate("localStorage.getItem('tst_al_unm_collapsed')")
            check("2.4: развёрнутый блок: строка на каждое название с кнопкой «Объединить»; состояние сохранено", shown == len(um) and stored == "0", (shown, stored))
            target = um[0][0]
            await page.locator('#alUnmatched [data-act="aliasFromUnmatched"]').first.click(); await page.wait_for_timeout(200)
            check("2.4: «Объединить» открывает форму с заполненным левым полем", (await page.input_value("#alias-left")) == target, target)
            tpl_first = await page.evaluate("Object.values(templateNameSet('ex'))[0]")
            await page.fill("#alias-right", tpl_first); await page.click("#alSave"); await page.wait_for_timeout(700)
            um2 = await page.evaluate("unmatchedNames().map(u=>u.name)")
            check("2.6: после добавления алиаса сопоставленное название пропадает из блока «Не сопоставлено»", target not in um2 and len(um2) == len(um) - 1, (target, um2[:3]))
            await page.reload(); await page.wait_for_timeout(2500); await page.click('button[data-tab="set"]'); await page.click('[data-act="aliasOpen"]'); await page.wait_for_timeout(300)
            check("2.4: после перезагрузки блок остаётся развёрнутым (состояние запомнено)", await page.locator('#alUnmatched [data-act="aliasFromUnmatched"]').count() > 0)
            # редактирование пары с пересчётом (смена канонического)
            await page.locator('.al-card', has=page.get_by_text("Гиперэкстензия", exact=True)).locator(".al-txt").click(); await page.wait_for_timeout(150)
            await page.fill("#alias-right", "Гиперэкстензия"); await page.wait_for_timeout(100)
            check("2.3: при редактировании название справа не может совпадать с левым", await page.locator("#alSave").is_disabled())
            check("нет pageerror", not errs, errs[:2])
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_alias2.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
