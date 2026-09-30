"""Фаза 12, задача 4: размер шрифта (rem, масштаб корня). На реальном дампе."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
LONG_VARIANT = "Прямая изогнутая рукоять узкая"
LONG_NAME = "Очень длинное название упражнения для проверки переноса строк в карточке"

OFFENDERS = """(()=>{ const out=[]; for(const e of document.querySelectorAll('#app button, #app select, #app input:not([type=color]):not([type=checkbox]):not([type=radio]), #app .chip')){
    const r=e.getBoundingClientRect(); if(!r.width||!r.height) continue; const cs=getComputedStyle(e); if(cs.visibility==='hidden'||cs.display==='none') continue;
    if(e.classList.contains('note-toggle')||e.classList.contains('today-link')||e.classList.contains('dtitle-btn')||e.classList.contains('hist-back')||e.classList.contains('ex-name')||e.classList.contains('badge')||e.closest('.swatch')) continue;
    if(r.height<43.5) out.push((e.className||e.tagName)+':'+Math.round(r.height)); } return [...new Set(out)].slice(0,8); })()"""

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    src = open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            st = src[src.index("<style>"):src.index("</style>")]
            rest = st[st.index("        }", st.index(":root{")):]
            check("4: все font-size в стилях — в rem (px не осталось)", not re.findall(r"font-size:\s*[\d.]+px", rest), re.findall(r"font-size:\s*[\d.]+px", rest)[:4])
            check("4: отступы и размеры в rem; px остались только у границ/теней/max-width/токенов", not re.findall(r"(?<![\w-])(?:padding|margin|gap|border-radius)[a-z-]*:[^;{}]*\b(?:[3-9]|\d\d+)(?:\.\d+)?px", rest), re.findall(r"(?:padding|margin|gap|border-radius)[a-z-]*:[^;{}]*\b(?:[3-9]|\d\d+)(?:\.\d+)?px", rest)[:4])
            check("4: зона нажатия 44px — токены --touch / --touch-w (max(44px, 2.75rem))", "--touch:max(44px,2.75rem)" in st and "--touch-w:44px" in st)

            seed(dump)
            page, errs = await open_tg(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            check("4: cfg.fontScale по умолчанию 1; корень 16px", await page.evaluate("data.cfg.fontScale")  == 1 and await page.evaluate("getComputedStyle(document.documentElement).fontSize") == "16px")
            check("4: невалидный fontScale нормализуется в 1", await page.evaluate("[normalizeData({cfg:{fontScale:2},templates:[],log:{}}).cfg.fontScale, normalizeData({cfg:{fontScale:'1.15'},templates:[],log:{}}).cfg.fontScale]") == [1, 1.15])
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            seg = await page.evaluate("[...document.querySelectorAll('#fontSeg button')].map(b=>[b.textContent.replace(/\\s+/g,' ').trim(), b.classList.contains('on'), Math.round(b.getBoundingClientRect().height)])")
            check("4: «Размер шрифта»: переключатель Мелкий 90% / Обычный 100% / Крупный 115% / Очень крупный 130%, выбран «Обычный», зоны ≥ 44px",
                  [s[0] for s in seg] == ["Мелкий 90%", "Обычный 100%", "Крупный 115%", "Очень крупный 130%"] and [s[1] for s in seg] == [False, True, False, False] and all(s[2] >= 44 for s in seg), seg)
            check("4: под переключателем образец текста", await page.locator(".font-sample").count() == 1)
            await page.evaluate("window.__renders=0; const R=window.render; window.render=function(){ window.__renders++; return R.apply(this,arguments); }; 0")
            sample0 = await page.evaluate("document.querySelector('.font-sample').getBoundingClientRect().height")
            for v, px in ((0.9, "14.4px"), (1.15, "18.4px"), (1.3, "20.8px"), (1, "16px")):
                await page.click('#fontSeg [data-v="%s"]' % v); await page.wait_for_timeout(150)
                fs = await page.evaluate("getComputedStyle(document.documentElement).fontSize")
                if v == 1.3:
                    big = await page.evaluate("document.querySelector('.font-sample').getBoundingClientRect().height")
                check("4: масштаб %s → fontSize корня %s" % (v, px), fs == px, fs)
            check("4: образец и интерфейс перестраиваются сами (на 130% образец выше), полный render() не вызывался", big > sample0 * 1.15 and await page.evaluate("window.__renders") == 0, (sample0, big))
            check("4: выбор сохраняется в cfg и в облаке", await page.evaluate("data.cfg.fontScale") == 1 and '"fontScale":1' in STORE["tst_cfg"])
            await page.click('#fontSeg [data-v="1.3"]'); await page.wait_for_timeout(700)
            check("4: fontScale 1.3 записан в облако; после перезагрузки применяется сразу", '"fontScale":1.3' in STORE["tst_cfg"])
            await page.reload(); await page.wait_for_timeout(2500)
            check("4: после перезагрузки корень 20.8px", await page.evaluate("getComputedStyle(document.documentElement).fontSize") == "20.8px")
            await page.click('#fontSeg [data-v="1"]') if False else None

            # ---- 130% и 320px
            await page.set_viewport_size({"width": 320, "height": 800})
            await page.evaluate("curDate='2026-10-07'; ui.tab='day'; delete data.log[curDate]; delete ui.drafts[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); const d=getDay(); d.exercises[0].name+=' '; d.exercises[0].base=%s; d.exercises[0].name=composeName(d.exercises[0].base,d.exercises[0].plan,d.exercises[0].variant); const m=d.exercises.find(e=>e.base.startsWith('Молотки')); setExVariant(m,%s); window.__mid=m.id; render(); 0" % (json.dumps(LONG_NAME), json.dumps(LONG_VARIANT)))
            await page.wait_for_timeout(300)
            views = {"день": "ui.tab='day'; render()", "прогресс": "ui.tab='prg'; ui.progMode='ex'; progEx='Молотки, свободный вес или блок'; render()", "сводка": "ui.tab='prg'; ui.progMode='summary'; render()", "календарь": "ui.tab='cal'; render()", "шаблоны": "ui.tab='tpl'; render()",
                     "редактор": "ui.tab='tpl'; ui.editTpl=JSON.parse(JSON.stringify(data.templates.find(x=>x.id==='fb6c7mc'))); render()", "настройки": "ui.tab='set'; ui.editTpl=null; render()", "тема": "ui.tab='set'; ui.themeScreen=true; render()", "алиасы": "ui.tab='set'; ui.themeScreen=false; ui.aliasScreen=true; render()", "справка": "ui.aliasScreen=false; ui.tab='day'; render(); openHelp('day')"}
            bad = {}
            for name, js in views.items():
                await page.evaluate(js + "; 0"); await page.wait_for_timeout(80)
                off = await page.evaluate("""(()=>{ const W=innerWidth, out=[]; if(document.documentElement.scrollWidth>W) out.push('scroll:'+document.documentElement.scrollWidth); const root=document.getElementById('helpOv')||document.getElementById('app');
                    for(const e of root.querySelectorAll('*')){ if(e.closest('svg')&&e.tagName!=='svg') continue; const r=e.getBoundingClientRect(); if(r.width&&r.right>W+1&&getComputedStyle(e).position!=='fixed') out.push(e.tagName+'.'+e.className+':'+Math.round(r.right)); } return out.slice(0,4); })()""")
                if off: bad[name] = off
                await page.evaluate("const o=document.getElementById('helpOv'); if(o){ closeHelp(); } 0")
            check("4 (приёмка): 130% и 320px — нет горизонтальной прокрутки и выступающих элементов на 10 экранах", not bad, bad)
            await page.evaluate("ui.tab='day'; ui.aliasScreen=false; ui.themeScreen=false; render(); 0"); await page.wait_for_timeout(150)
            nxt = await page.evaluate("""(()=>{ const row=document.querySelector('.set-next'); const kids=[...row.children].map(c=>c.getBoundingClientRect()); const rr=row.getBoundingClientRect();
                return {tops:kids.map(k=>Math.round(k.top)), h:Math.round(rr.height), inside:kids.every(k=>k.left>=rr.left-1&&k.right<=rr.right+1), w:Math.round(rr.width), one:Math.max(...kids.map(k=>k.top))-Math.min(...kids.map(k=>k.top))<=rr.height/2}; })()""")
            check("4 (приёмка): на 130%/320px строка следующего подхода (степперы + галочка) в одну строку и внутри контейнера", nxt["one"] and nxt["inside"], nxt)
            vals = await page.evaluate("[...document.querySelectorAll('.set-next .stepper .val')].map(v=>[v.textContent.trim(), v.scrollWidth, v.clientWidth, Math.round(v.parentElement.getBoundingClientRect().width), getComputedStyle(v).fontSize])")
            check("4 (приёмка): значения в степперах видны (единицы скрыты контейнерным запросом, числа не обрезаны)", all(v[1] <= v[2] + 1 and v[0] for v in vals), vals[:4])
            nm = await page.evaluate("(()=>{ const e=document.querySelector('.ex-name'); const r=e.getBoundingClientRect(); const lh=parseFloat(getComputedStyle(e).lineHeight); return {lines:Math.round(r.height/lh), right:r.right, W:innerWidth}; })()")
            check("4 (приёмка): длинное название упражнения переносится на несколько строк и не выходит за экран", nm["lines"] >= 3 and nm["right"] <= nm["W"], nm)
            vb = await page.evaluate("""(id)=>{ const btn=document.querySelector('[data-act=variantToggle][data-id="'+id+'"]'), t=btn.querySelector('.vtxt'); const br=btn.getBoundingClientRect(), tr=t.getBoundingClientRect(), lh=parseFloat(getComputedStyle(t).lineHeight);
                return {inside:tr.left>=br.left-.5&&tr.right<=br.right+.5&&tr.bottom<=br.bottom+.5&&tr.top>=br.top-.5, lines:Math.round(tr.height/lh), h:Math.round(br.height), fs:getComputedStyle(t).fontSize}; }""", await page.evaluate("window.__mid"))
            check("1 (приёмка): вариант из 30 символов на 320px при 130% не вылезает за кнопку, не больше двух строк, высота ряда ≥ 44px", vb["inside"] and vb["lines"] <= 2 and vb["h"] >= 44, vb)
            check("4: минимальная зона нажатия 44px на 130% (кнопки, поля, чипы)", not await page.evaluate(OFFENDERS), await page.evaluate(OFFENDERS))
            # графики
            await page.evaluate("ui.tab='prg'; ui.progMode='ex'; progEx='Молотки, свободный вес или блок'; render(); 0"); await page.wait_for_timeout(150)
            fs130 = await page.evaluate("[...new Set([...document.querySelectorAll('#app svg text')].map(t=>t.getAttribute('font-size')))]")
            check("4: подписи осей графиков масштабируются вместе с интерфейсом (9 × 1.3 = 11.7)", fs130 == ["11.700000000000001"] or fs130 == ["11.7"], fs130)

            # ---- 90%
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.evaluate("data.cfg.fontScale=0.9; applyFontScale(); ui.tab='day'; render(); 0"); await page.wait_for_timeout(200)
            check("4: на 90% корень 14.4px, зоны нажатия не меньше 44px (степпер, галочка, крестики, ряд кнопок)", await page.evaluate("getComputedStyle(document.documentElement).fontSize") == "14.4px" and not await page.evaluate(OFFENDERS), await page.evaluate(OFFENDERS))
            for name, js in (("настройки", "ui.tab='set'; render()"), ("календарь", "ui.tab='cal'; render()"), ("шаблоны", "ui.tab='tpl'; render()")):
                await page.evaluate(js + "; 0"); await page.wait_for_timeout(80)
                o = await page.evaluate(OFFENDERS)
                check("4: 90 процентов: экран «" + name + "» — кнопки и поля не меньше 44px", not o, o)
            await page.evaluate("data.cfg.fontScale=1; applyFontScale(); ui.tab='day'; render(); 0")
            check("нет pageerror", not errs, errs[:2])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
