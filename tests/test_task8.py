"""Задача 8: parseSetsStr, вёрстка/safe-area Telegram, иконки, новый ввод подхода (сетка, степперы). На реальном дампе."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, check, RESULTS, REPO, BASE
from test_task7 import open_tg, seed
from test_task4 import new_page
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8"))
    src = open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)

            # ================= 8.1 parseSetsStr =================
            page, errs = await new_page(browser, dump, xlsx=False)
            ps = lambda s: page.evaluate("parseSetsStr(%s)" % json.dumps(s))
            r = await ps("37,5х8, 40х8"); check("8.1: «37,5х8, 40х8» → [{37.5×8},{40×8}]", r == {"sets": [{"w": 37.5, "r": 8}, {"w": 40, "r": 8}], "valid": True}, r)
            r = await ps("40х10,40х10"); check("8.1: «40х10,40х10» → два подхода по 40", r["sets"] == [{"w": 40, "r": 10}] * 2 and r["valid"], r)
            r = await ps("45 х 12"); check("8.1: «45 х 12» → {45×12}", r["sets"] == [{"w": 45, "r": 12}], r)
            r = await ps("40x10 50*8; 60×6"); check("8.1: латинская x, «*», «×», пробелы и «;» как разделители", [(s["w"], s["r"]) for s in r["sets"]] == [(40, 10), (50, 8), (60, 6)] and r["valid"], r)
            r = await ps("40х10, мусор"); check("8.1: нераспознанный остаток → valid=false", r["valid"] is False, r)
            r = await ps(""); check("8.1: пустая строка → пусто, valid", r == {"sets": [], "valid": True})
            check("8.1: в коде нет split(\",\") для подходов (глобальный regex)", "PAIR_RE=/(\\d+(?:[.,]\\d+)?)\\s*[хx×*]\\s*(\\d+)/gi" in src)

            # ================= 8.3 иконки =================
            emoji = re.findall(r"[\U0001F300-\U0001FAFF☀-➿⬀-⯿⧉▾⛓]", src)
            check("8.3: в коде нет эмодзи и символов-иконок (⧉ ▾ ⛓ и т. п.)", not emoji, emoji[:5])
            check("8.3: константы ICON_COPY/CHEVRON/LINK/CHECK/MINUS/PLUS определены через svgIcon (currentColor)",
                  all(re.search(r"const %s=svgIcon\(" % n, src) for n in ("ICON_COPY", "ICON_CHEVRON", "ICON_LINK", "ICON_CHECK", "ICON_MINUS", "ICON_PLUS", "ICON_TRASH")) and 'stroke="currentColor"' in src)
            check("8.4: кнопка «копировать подход» удалена", "repSet" not in src and "ICON_COPY+'" not in src.split("function exCardHtml")[1][:6000])

            # ================= 8.2 safe-area / viewport =================
            check("8.2: нет 100vh и env(safe-area-inset-*) вне определений переменных",
                  len(re.findall(r"env\(safe-area-inset", src)) == 4 and len(re.findall(r"100vh", src)) == 2, (len(re.findall(r"env\(safe-area-inset", src)), len(re.findall(r"100vh", src))))
            INSETS = """(()=>{ const W=window.Telegram.WebApp; window.__order=[]; window.__ev={};
                W.safeAreaInset={top:47,bottom:34,left:0,right:0}; W.contentSafeAreaInset={top:56,bottom:0,left:0,right:0}; W.viewportStableHeight=700;
                W.onEvent=(ev,cb)=>{ (window.__ev[ev]=window.__ev[ev]||[]).push(cb); };
                const r=W.ready, e=W.expand; W.ready=()=>{ window.__order.push('ready'); r&&r(); }; W.expand=()=>{ window.__order.push('expand'); e&&e(); };
                const mo=new MutationObserver(ms=>{ for(const m of ms){ if(m.target.id==='app'&&window.__order.indexOf('render')<0) window.__order.push('render'); } });
                mo.observe(document,{childList:true,subtree:true}); })();"""
            seed(dump)
            tp, te = await open_tg(browser, INSETS)
            await tp.goto(BASE + "/test/index.html"); await tp.wait_for_timeout(2500)
            check("8.2: порядок старта ready() → expand() → первый рендер", (await tp.evaluate("window.__order.slice(0,3)")) == ["ready", "expand", "render"], await tp.evaluate("window.__order"))
            cs = await tp.evaluate("""(()=>{ const r=document.documentElement, g=(v)=>getComputedStyle(r).getPropertyValue(v).trim(), b=getComputedStyle(document.body), t=getComputedStyle(document.getElementById('tabbar')), h=getComputedStyle(document.querySelector('header'));
                return {sat:g('--sa-top'),csat:g('--csa-top'),sab:g('--sa-bottom'),sh:g('--stable-h'),pt:b.paddingTop,minh:b.minHeight,tb:t.paddingBottom,ht:h.top}; })()""")
            check("8.2: значения Telegram попали в переменные (top 47+56, bottom 34, stable 700)", cs["sat"] == "47px" and cs["csat"] == "56px" and cs["sab"] == "34px" and cs["sh"] == "700px", cs)
            check("8.2: контент не заходит под шапку Telegram (padding-top = safe + content safe), шапка липнет ниже неё", cs["pt"] == "103px" and cs["ht"] == "103px", cs)
            check("8.2: нижняя навигация: padding-bottom = нижний safe-area inset (+4px), высота из stable-height", cs["tb"] == "38px" and cs["minh"] == "700px", cs)
            await tp.evaluate("window.__renders=0; const R=window.render; window.render=function(){ window.__renders++; return R.apply(this,arguments); }; 0")
            await tp.evaluate("""(()=>{ const W=window.Telegram.WebApp; W.safeAreaInset={top:20,bottom:10,left:5,right:5}; W.contentSafeAreaInset={top:0,bottom:12,left:0,right:0}; W.viewportStableHeight=500;
                for(const ev of ['viewportChanged','safeAreaChanged','contentSafeAreaChanged']) for(const cb of window.__ev[ev]||[]) cb(); 0 })()""")
            cs2 = await tp.evaluate("""(()=>{ const r=document.documentElement, g=(v)=>getComputedStyle(r).getPropertyValue(v).trim(), b=getComputedStyle(document.body);
                return {sat:g('--sa-top'),csat:g('--csa-top'),sab:g('--sa-bottom'),csab:g('--csa-bottom'),sh:g('--stable-h'),pt:b.paddingTop,minh:b.minHeight,renders:window.__renders}; })()""")
            check("8.2: подписка на viewportChanged / safeAreaChanged / contentSafeAreaChanged обновляет переменные без render()",
                  (await tp.evaluate("['viewportChanged','safeAreaChanged','contentSafeAreaChanged'].map(e=>(window.__ev[e]||[]).length)")) == [1, 1, 1] and cs2["sat"] == "20px" and cs2["csab"] == "12px" and cs2["sh"] == "500px" and cs2["pt"] == "20px" and cs2["minh"] == "500px" and cs2["renders"] == 0, cs2)
            plain = await browser.new_context(); pp = await plain.new_page(); await pp.route("**/telegram.org/**", lambda r: r.abort()); await pp.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
            await pp.goto(BASE + "/test/index.html"); await pp.wait_for_timeout(700)
            fb = await pp.evaluate("(()=>{ const b=getComputedStyle(document.body); return {pt:b.paddingTop, pb:b.paddingBottom, sat:getComputedStyle(document.documentElement).getPropertyValue('--sa-top').trim()}; })()")
            check("8.2: без Telegram — fallback на env()/100vh (нули, padding-bottom 64px)", fb["pt"] == "0px" and fb["pb"] == "64px", fb)

            # ================= 8.4 новый ввод подхода =================
            seed(dump)
            hp = "window.__hap=[]; Telegram.WebApp.HapticFeedback.impactOccurred=k=>window.__hap.push(k); 0"
            dp, de = await open_tg(browser)
            await dp.goto(BASE + "/test/index.html"); await dp.wait_for_timeout(2500)
            await dp.evaluate("curDate='2026-09-30'; ui.tab='day'; data.cfg.autoTimer=true; delete data.log[curDate]; delete ui.drafts[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); 0")
            await dp.evaluate(hp)
            card = lambda name: dp.locator(".card").filter(has=dp.locator('.ex-name', has_text=name))
            c = card("Сгибания с гантелями")
            cols = await c.locator(".set-next").evaluate("e=>{ const s=getComputedStyle(e); return {cols:s.gridTemplateColumns.split(' '), gap:s.columnGap, bs:getComputedStyle(e,'::before').borderTopStyle, bc:getComputedStyle(e,'::before').borderTopColor}; }")
            check("8.4: сетка № | вес | повторы | действие: 20px, 2 гибкие колонки, 44px, gap 6px", len(cols["cols"]) == 4 and cols["cols"][0] == "20px" and cols["cols"][3] == "44px" and cols["cols"][1] == cols["cols"][2] and cols["gap"] == "6px", cols)
            check("8.4: строка следующего подхода — пунктирная рамка акцентного цвета", cols["bs"] == "dashed" and cols["bc"] == "rgb(255, 159, 10)", cols)
            lab = await c.locator(".set-labels").inner_text()
            check("8.4: над сеткой подписи «кг» и «повт.»", "кг" in lab and "повт." in lab)
            nx = await c.locator(".set-next").inner_text()
            check("8.4: предзаполнение первого подхода рекомендацией (неделя отдыха: 45×12 → разгрузка 40 кг × 8)", "40" in nx and "8" in nx, nx)
            geo = await c.locator(".set-next").evaluate("e=>({st:[...e.querySelectorAll('.stepper')].map(s=>s.getBoundingClientRect().height), step:[...e.querySelectorAll('.step')].map(s=>[s.getBoundingClientRect().width,s.getBoundingClientRect().height]), chk:[e.querySelector('.check').getBoundingClientRect().width,e.querySelector('.check').getBoundingClientRect().height]})")
            check("8.4: степперы и галочка — 44px высотой, кнопки −/+ по 32px шириной", geo["st"] == [44, 44] and all(w == 32 and h == 44 for w, h in geo["step"]) and geo["chk"] == [44, 44], geo)
            filled = await c.evaluate("""c=>{ const a=getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(); const rgb='rgb(255, 159, 10)';
                return [...c.querySelectorAll('button')].filter(b=>getComputedStyle(b).backgroundColor===rgb).map(b=>b.className); }""")
            check("8.4: галочка — единственная залитая кнопка карточки, цвет иконки контрастный", filled == ["check"] and await c.locator(".check svg").count() == 1, filled)
            # степперы и округление
            await c.locator('[data-act="stepW"][data-dir="1"]').click()
            w1 = await c.evaluate("e=>e.querySelector('.set-next [data-kind=nw]').textContent.trim()")
            await c.locator('[data-act="stepW"][data-dir="-1"]').click(); await c.locator('[data-act="stepW"][data-dir="-1"]').click()
            w2 = await c.evaluate("e=>e.querySelector('.set-next [data-kind=nw]').textContent.trim()")
            check("8.4: ± по весу — шаг по авто-правилу (40 → 45 → 40 → 35)", w1.startswith("45") and w2.startswith("35"), (w1, w2))
            await c.locator('[data-act="stepR"][data-dir="-1"]').click(count=20) if False else None
            for _ in range(20): await c.locator('[data-act="stepR"][data-dir="-1"]').click()
            r_min = await c.evaluate("e=>e.querySelector('.set-next [data-kind=nr]').textContent.trim()")
            await dp.evaluate("ui.nextSet[getDay().exercises.find(e=>e.base.startsWith('Сгибания с гант')).id].w=0.1+0.2; updateNextDom(getDay().exercises.find(e=>e.base.startsWith('Сгибания с гант')).id); 0")
            await c.locator('[data-act="stepW"][data-dir="1"]').click()
            w_f = await c.evaluate("e=>e.querySelector('.set-next [data-kind=nw]').textContent.trim()")
            check("8.4: минимум повторов 1; вес без артефактов float (0.1+0.2 + шаг → «1.3 кг»)", r_min == "1" and w_f.startswith("1.3") and "0000" not in w_f, (r_min, w_f))
            for _ in range(60): await c.locator('[data-act="stepW"][data-dir="-1"]').click()
            w_min = await c.evaluate("e=>e.querySelector('.set-next [data-kind=nw]').textContent.trim()")
            check("8.4: минимум веса 0", w_min.startswith("0 "), w_min)
            # тап по числу → input
            await c.locator('.set-next [data-kind="nw"]').click()
            inp = c.locator(".set-next input.num-edit")
            check("8.4: тап по весу → input с inputmode=decimal", await inp.count() == 1 and await inp.get_attribute("inputmode") == "decimal")
            await inp.fill("42,5"); await inp.press("Enter")
            check("8.4: Enter применяет значение, запятая — десятичный разделитель (42.5 кг)", (await c.evaluate("e=>e.querySelector('.set-next [data-kind=nw]').textContent.trim()")).startswith("42.5") and await c.locator(".set-next input.num-edit").count() == 0)
            await c.locator('.set-next [data-kind="nr"]').click()
            check("8.4: тап по повторам → input с inputmode=numeric", await c.locator(".set-next input.num-edit").get_attribute("inputmode") == "numeric")
            await c.locator(".set-next input.num-edit").fill("11"); await dp.click("body", position={"x": 5, "y": 300})   # blur
            check("8.4: blur применяет значение (11)", (await c.evaluate("e=>e.querySelector('.set-next [data-kind=nr]').textContent.trim()")) == "11")
            await c.locator('.set-next [data-kind="nw"]').click(); await c.locator(".set-next input.num-edit").fill("abc"); await c.locator(".set-next input.num-edit").press("Enter")
            check("8.4: некорректный ввод не меняет значение (42.5)", (await c.evaluate("e=>e.querySelector('.set-next [data-kind=nw]').textContent.trim()")).startswith("42.5"))
            # галочка
            await dp.evaluate("window.__renders=0; const R=window.render; window.render=function(){ window.__renders++; return R.apply(this,arguments); }; window.__hap.length=0; 0")
            n_w0 = await dp.evaluate("Object.keys(data.log).length")
            await c.locator(".check").click(); await dp.wait_for_timeout(300)
            ex = await dp.evaluate("getDay().exercises.find(e=>e.base.startsWith('Сгибания с гант'))")
            check("8.4: галочка записывает подход (42.5×11) и создаёт запись дня в хранилище", ex["sets"] == [{"w": 42.5, "r": 11}] and await dp.evaluate("!!data.log['2026-09-30']") and "tst_w_2026-09-30" in STORE, ex["sets"])
            check("8.4: без полного render(), haptic light, строка подхода добавлена, номер следующего = 2", await dp.evaluate("window.__renders") == 0 and (await dp.evaluate("window.__hap")) == ["light"] and await c.locator(".set-row").count() == 1 and (await c.locator(".set-next .idx").inner_text()) == "2", (await dp.evaluate("[window.__renders, window.__hap]")))
            check("8.4: следующий подход предзаполнен значениями только что записанного (42.5 / 11)", (await c.evaluate("e=>e.querySelector('.set-next').textContent")).count("42.5") == 1 and "11" in await c.locator(".set-next").inner_text())
            check("8.4: autoTimer запускает таймер отдыха", await dp.evaluate("timerEnd>Date.now()"))
            rowtxt = await c.locator(".set-row").first.inner_text()
            check("8.4: запись в строке: номер | «42.5 кг» | «11» | крестик", "1" in rowtxt and "42.5" in rowtxt and "кг" in rowtxt and "11" in rowtxt and await c.locator(".set-row .del-set").count() == 1)
            muted0 = await c.locator(".set-next .idx").evaluate("e=>e.classList.contains('muted')")
            await c.locator(".check").click(); await dp.wait_for_timeout(200)
            muted1 = await c.locator(".set-next .idx").evaluate("e=>e.classList.contains('muted')")
            check("8.4: план 2х8-15: после 1-го подхода номер акцентный, при достижении плана (2) — приглушённый; строка остаётся", not muted0 and muted1 and await c.locator(".set-next").count() == 1)
            await c.locator(".check").click(); await dp.wait_for_timeout(200)
            check("8.4: сверх плана можно писать дальше (3 подхода)", await dp.evaluate("getDay().exercises.find(e=>e.base.startsWith('Сгибания с гант')).sets.length") == 3 and await dp.evaluate("window.__renders") == 0)
            # правка записанного подхода
            await c.locator('.set-row [data-kind="w"]').first.click(); await c.locator(".set-row input.num-edit").fill("50"); await c.locator(".set-row input.num-edit").press("Enter"); await dp.wait_for_timeout(300)
            chk = await dp.evaluate("getDay().exercises.find(e=>e.base.startsWith('Сгибания с гант')).sets[0]")
            check("8.4: тап по значению записанного подхода — правка (50), сохранение без render()", chk["w"] == 50 and await dp.evaluate("window.__renders") == 0 and '"w":50' in STORE["tst_w_2026-09-30"], chk)
            # удаление
            await c.locator('.set-row [data-act="delSet"]').last.click(); await dp.wait_for_timeout(300)
            check("8.4: крестик удаляет подход", await dp.evaluate("getDay().exercises.find(e=>e.base.startsWith('Сгибания с гант')).sets.length") == 2 and await c.locator(".set-row").count() == 2)
            # пустое упражнение: «—» и валидация
            c2 = card("Вертикальная тяга широким")
            # у упражнения без истории значения пусты
            await dp.evaluate("(()=>{ const e=newEx('Новое упражнение без истории','3х8-12',null); const d=getDay(); d.exercises.push(e); setDay(d); window.__newId=e.id; 0 })()")
            c3 = card("Новое упражнение")
            check("8.4: нет рекомендации и прошлой тренировки → поля пусты («—»)", (await c3.locator(".set-next").inner_text()).count("—") == 2)
            await c3.locator(".check").click(); await dp.wait_for_timeout(200)
            check("8.4: галочка с пустыми значениями ничего не записывает (тост)", "Задайте" in await dp.inner_text("#toastMsg") and await dp.evaluate("getDay().exercises.find(e=>e.id===window.__newId).sets.length") == 0)
            # бейдж рекомендации
            await dp.evaluate("curDate='2026-10-07'; delete data.log[curDate]; delete ui.drafts[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); 0")   # рабочая неделя: кнопка «Реком.»
            rb = card("Молотки").locator(".rec-btn")
            await card("Молотки").locator('[data-act="stepW"][data-dir="1"]').click()
            await dp.evaluate("window.__renders=0; 0")
            await rb.click()
            tx = await card("Молотки").locator(".set-next").inner_text()
            check("8.4: бейдж рекомендации по тапу подставляет значения в строку следующего подхода", "Реком" in await rb.inner_text() and await dp.evaluate("window.__renders") == 0 and ("15" in tx and "14" in tx), tx)
            check("8.4: старые поля ввода кг/повт. и «+» удалены", await dp.locator('input[id^="w-"], input[id^="r-"], .addset').count() == 0)
            check("нет pageerror (8.4)", not de and not te, (de[:1], te[:1]))
            await dp.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_sets.png"))

            # ================= 8.2 ширины и горизонтальная прокрутка =================
            seed(dump)
            wp, we = await open_tg(browser)
            await wp.goto(BASE + "/test/index.html"); await wp.wait_for_timeout(2500)
            await wp.evaluate("curDate='2026-09-30'; data.cfg.autoTimer=false; delete data.log[curDate]; delete ui.drafts[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); const d=getDay(); d.exercises[0].sets.push({w:137.5,r:12},{w:70,r:8}); commitDay(curDate,d); 0")
            views = {"день": "ui.tab='day'; ui.histEx=null; ui.hygiene=null; ui.aliasScreen=false; render()", "прогресс": "ui.tab='prg'; ui.progMode='ex'; progEx='Молотки, свободный вес или блок'; render()",
                     "сводка": "ui.tab='prg'; ui.progMode='summary'; render()", "календарь": "ui.tab='cal'; render()", "шаблоны": "ui.tab='tpl'; ui.editTpl=null; render()",
                     "редактор шаблона": "ui.tab='tpl'; ui.editTpl=JSON.parse(JSON.stringify(data.templates.find(x=>x.id==='fb6c7mc'))); render()",
                     "настройки": "ui.tab='set'; ui.editTpl=null; ui.aliasScreen=false; ui.hygiene=null; render()", "алиасы": "ui.tab='set'; ui.aliasScreen=true; render()",
                     "дубли": "ui.tab='set'; ui.aliasScreen=false; ui.hygiene='dups'; render()", "проверка": "ui.tab='set'; ui.hygiene='check'; render()"}
            bad = {}
            for width in (320, 360, 390, 412, 768, 1280):
                await wp.set_viewport_size({"width": width, "height": 900})
                for name, js in views.items():
                    await wp.evaluate(js + "; 0"); await wp.wait_for_timeout(60)
                    off = await wp.evaluate("""(()=>{ const W=innerWidth, de=document.documentElement; const out=[];
                        if(de.scrollWidth>W||document.body.scrollWidth>W) out.push('scroll:'+de.scrollWidth+'>'+W);
                        for(const e of document.querySelectorAll('#app *')){ if(e.closest('svg')&&e.tagName!=='svg') continue; const r=e.getBoundingClientRect(); if(r.width&&r.right>W+1&&getComputedStyle(e).position!=='fixed') out.push(e.tagName+'.'+e.className+':'+Math.round(r.right)); }
                        return out.slice(0,4); })()""")
                    if off: bad["%s@%d" % (name, width)] = off
            check("8.2: ширины 320/360/390/412/768/1280 × 10 экранов — нет горизонтальной прокрутки и выступающих элементов", not bad, dict(list(bad.items())[:6]))
            await wp.set_viewport_size({"width": 1280, "height": 900}); await wp.evaluate(views["день"] + "; 0"); await wp.wait_for_timeout(100)
            check("8.4: на ширине ≥ 600px строка не растягивается (≤ 480px)", await wp.evaluate("Math.max(...[...document.querySelectorAll('.sets-wrap')].map(e=>e.getBoundingClientRect().width))") <= 480)
            await wp.set_viewport_size({"width": 320, "height": 900}); await wp.wait_for_timeout(100)
            await wp.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_sets320.png"))
            check("нет pageerror (8.2)", not we, we[:2])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
