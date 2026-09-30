"""Фаза 12, задача 3: темы и цвета. На реальном дампе."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")

def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
def contrast(a, b):
    la, lb = lum(a), lum(b); return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
def rgb(h): return "rgb(%d, %d, %d)" % tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

CONTRAST_JS = """(()=>{ const t=resolveColor('--text'), s=resolveColor('--surface'), bg=resolveColor('--bg'), a=resolveColor('--accent'), oa=resolveColor('--on-accent');
    const c=(x,y)=>{ const f=v=>{v/=255; return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)}; const L=z=>.2126*f(z.r)+.7152*f(z.g)+.0722*f(z.b); const p=L(x),q=L(y); return (Math.max(p,q)+.05)/(Math.min(p,q)+.05); };
    return {textSurf:c(t,s), textBg:c(t,bg), onAcc:c(oa,a), scroll:document.documentElement.scrollWidth<=innerWidth}; })()"""

async def pick(page, tok, hexv, done=True):
    """выбрать свой цвет через пикер: открыть лист, ввести HEX, «Готово» (или «Отмена»)"""
    await page.click('[data-act="colorOpen"][data-tok="%s"]' % tok); await page.wait_for_timeout(120)
    await page.fill("#cpHex", hexv); await page.wait_for_timeout(100)
    await page.click('#cpick .cp-btns [data-cp="%s"]' % ("done" if done else "cancel")); await page.wait_for_timeout(120)

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

            # ---- 3.1 токены и отсутствие хардкода
            st = src[src.index("<style>"):src.index("</style>")]
            css_rest = st[st.index("--touch-2:max(52px,3.25rem);"):]
            js = src[src.index("</style>"):]
            js_rest = js[:js.index("THEME-DATA-BEGIN")] + js[js.index("THEME-DATA-END"):]
            pat = r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)"
            check("3.1: в стилях нет цветов вне токенов (поиск «#» и «rgb(» вне :root)", not re.findall(pat, css_rest), re.findall(pat, css_rest)[:5])
            check("3.1: в JS нет цветов вне блока данных темы (THEME-DATA)", not re.findall(pat, js_rest), re.findall(pat, js_rest)[:5])
            check("3.1: старые токены (--card, --mut, --dim, --btn, --link, --red, --green) не используются", not re.findall(r"var\(--(card2?|mut|dim|btn(-text)?|link|red|green)\)", src))

            seed(dump)
            page, errs = await open_tg(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            toks = await page.evaluate("""['--bg','--surface','--surface-2','--text','--text-muted','--accent','--on-accent','--accent-2','--danger'].map(t=>{ const p=document.createElement('span'); p.style.color='var('+t+')'; document.body.appendChild(p); const c=getComputedStyle(p).color; p.remove(); return [t,c]; })""")
            check("3.1: все токены из ТЗ определены и раскрываются в цвет", all(c and c != "rgba(0, 0, 0, 0)" for _, c in toks), toks)
            acc2 = await page.evaluate("[resolveColor('--accent'), resolveColor('--accent-2')]")
            check("3.1: по умолчанию --accent-2 = «Как акцент»", acc2[0] == acc2[1], acc2)
            check("3.1: --on-accent вычисляется автоматически (чёрный/белый по контрасту)", await page.evaluate("[accentBtnText('#ffd60a'),accentBtnText('#3b82f6'),accentBtnText('#000000'),accentBtnText('#ffffff')]") == ["#09090b", "#09090b", "#ffffff", "#09090b"])

            # ---- 3.5 миграция
            mig = await page.evaluate("""[normTheme('tg','#2481cc'),normTheme('dark','#34d399'),normTheme('light',undefined),normTheme({base:'graphite',accent:'#3B82F6',accent2:'#ff453a',custom:{}}),normTheme({base:'мусор',accent:'red'}),normTheme(undefined,undefined)]""")
            check("3.5: миграция cfg.theme-строки и cfg.accent: tg→tg, dark→oled, light→light, акцент сохраняется", mig[0]["base"] == "tg" and mig[0]["accent"] == "#2481cc" and mig[1]["base"] == "oled" and mig[1]["accent"] == "#34d399" and mig[2]["base"] == "light" and mig[2]["accent"] == "#ff9f0a", mig[:3])
            check("3.5: объект темы проходит как есть (нормализуется регистр hex), мусор → tg/оранжевый", mig[3] == {"base": "graphite", "accent": "#3b82f6", "accent2": "#ff453a", "rest": "#30d158", "custom": {}} and mig[4]["base"] == "tg" and mig[4]["accent"] == "#ff9f0a" and mig[5]["base"] == "tg", mig[3:])
            check("3.5: в реальных данных cfg.theme стал объектом, cfg.accent синхронизирован", await page.evaluate("typeof data.cfg.theme==='object' && data.cfg.theme.base==='tg' && data.cfg.accent===data.cfg.theme.accent"))

            # ---- 3.4 экран
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            check("3.4: в настройках строка «Цвета и акцент» ведёт на экран темы", await page.locator('[data-act="themeOpen"]').count() == 1)
            await page.click('[data-act="themeOpen"]'); await page.wait_for_timeout(200)
            cnt = await page.evaluate("({base:document.querySelectorAll('#swBase [data-act=themeBase]').length, baseCustom:document.querySelectorAll('#themeSections .swatch.custom[data-custom=bg],#themeSections .swatch.custom[data-custom=surface],#themeSections .swatch.custom[data-custom=text]').length, acc:document.querySelectorAll('#swAccent [data-act=themeAccent]').length, accCustom:document.querySelectorAll('.swatch.custom[data-custom=accent]').length, a2:document.querySelectorAll('#swAccent2 [data-act=themeAccent2]').length, a2Custom:document.querySelectorAll('.swatch.custom[data-custom=accent2]').length, preview:!!document.getElementById('themePreview')})")
            check("3.2: основа — 6 вариантов + «Свои цвета основы» (фон, карточки, текст); акцент — 12 + «Свой»; дополнительный — 12 + «Свой» (+ строка «Как акцент»)", cnt == {"base": 6, "baseCustom": 3, "acc": 12, "accCustom": 1, "a2": 12, "a2Custom": 1, "preview": True}, cnt)
            names = await page.evaluate("[...document.querySelectorAll('#swBase [data-act=themeBase]')].map(b=>b.title)")
            check("3.2: названия основ как в ТЗ", names == ["Как в Telegram", "Чёрная (OLED)", "Тёмно-серая", "Графит с синевой", "Светлая", "Тёплая светлая"], names)
            check("3.2: в сетке акцентов оранжевый #ff9f0a выбран (обводка), круги ≥ 44px", await page.evaluate("(()=>{ const b=document.querySelector('#swAccent [data-v=\"#ff9f0a\"]'); return b.classList.contains('sel')&&getComputedStyle(b).outlineStyle==='solid'&&b.getBoundingClientRect().width>=44; })()"))
            prev = await page.evaluate("(()=>{ const c=document.getElementById('themePreview'); return {name:!!c.querySelector('.ex-name'), badge:!!c.querySelector('.rec-btn'), steppers:c.querySelectorAll('.stepper').length, check:!!c.querySelector('.check'), variant:!!c.querySelector('.variant-btn')}; })()")
            check("3.4: живое превью: карточка упражнения с заголовком, бейджем, строкой подхода со степперами и галочкой, кнопкой варианта", prev == {"name": True, "badge": True, "steppers": 2, "check": True, "variant": True}, prev)

            # ---- применение без render, хранение
            await page.evaluate("window.__renders=0; const R=window.render; window.render=function(){ window.__renders++; return R.apply(this,arguments); }; 0")
            bgs = await page.evaluate("getComputedStyle(document.getElementById('themePreview')).backgroundColor")
            await page.click('#swBase [data-v="oled"]'); await page.wait_for_timeout(300)
            r = await page.evaluate("({bg:getComputedStyle(document.body).backgroundColor, card:getComputedStyle(document.getElementById('themePreview')).backgroundColor, sel:document.querySelector('#swBase [data-v=oled]').classList.contains('sel'), name:document.getElementById('swBaseName').textContent, renders:window.__renders})")
            check("3.2: «Чёрная (OLED)»: фон #000 и карточки #0d0d0f применяются сразу к превью и странице, отметка и название обновились, render() не вызывался", r["bg"] == "rgb(0, 0, 0)" and r["card"] == rgb("#0d0d0f") and r["sel"] and r["name"] == "Выбрано: Чёрная (OLED)" and r["renders"] == 0 and r["card"] != bgs, r)
            check("3.5: тема сохранена в cfg и в облаке (base oled)", await page.evaluate("data.cfg.theme.base") == "oled" and '"base":"oled"' in STORE["tst_cfg"])
            await page.click('#swAccent [data-v="#ffd60a"]'); await page.wait_for_timeout(200)
            a = await page.evaluate("({acc:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(), chk:getComputedStyle(document.querySelector('#themePreview .check')).backgroundColor, chkc:getComputedStyle(document.querySelector('#themePreview .check')).color})")
            check("3.1: жёлтый акцент → галочка жёлтая, иконка на ней чёрная (контраст считается)", a["acc"] == "#ffd60a" and a["chk"] == rgb("#ffd60a") and a["chkc"] == rgb("#09090b"), a)
            await page.click('#swAccent2 [data-v="#ff453a"]'); await page.wait_for_timeout(200)
            a2 = await page.evaluate("({badge:getComputedStyle(document.querySelector('#themePreview .rec-btn')).color, outline:getComputedStyle(document.querySelector('#themePreview .set-next'),'::before').borderTopColor, acc:getComputedStyle(document.querySelector('#themePreview .check')).backgroundColor})")
            check("3.1: дополнительный цвет (красный) красит бейдж рекомендации и обводку следующего подхода; акцент остаётся жёлтым", a2["badge"] == rgb("#ff453a") and a2["outline"] == rgb("#ff453a") and a2["acc"] == rgb("#ffd60a"), a2)
            await page.click('[data-act="themeAccent2"][data-v=""]'); await page.wait_for_timeout(150)
            check("3.2: «Как акцент» возвращает дополнительный цвет к акценту", await page.evaluate("data.cfg.theme.accent2") is None and await page.evaluate("JSON.stringify(resolveColor('--accent-2'))===JSON.stringify(resolveColor('--accent'))"))

            # ---- 3.3 свои цвета и контраст
            await pick(page, 'accent', '#123abc'); await page.wait_for_timeout(700)
            c = await page.evaluate("({acc:data.cfg.theme.accent, sel:document.querySelector('.swatch.custom[data-custom=accent]').classList.contains('sel'), bg:document.querySelector('.swatch.custom[data-custom=accent]').style.background, cfgAcc:data.cfg.accent, presetSel:document.querySelectorAll('#swAccent [data-act=themeAccent].sel').length})")
            check("3.3: свой акцент #123abc применён, кружок «Свой» показывает выбранный цвет и отмечен, пресеты сняты", c["acc"] == "#123abc" and c["sel"] and "rgb(18, 58, 188)" in c["bg"] and c["presetSel"] == 0 and c["cfgAcc"] == "#123abc", c)
            check("3.3: свой цвет сохранён в облаке (после паузы)", '"accent":"#123abc"' in STORE["tst_cfg"])
            await pick(page, 'bg', '#202020')
            await pick(page, 'surface', '#303030'); await pick(page, 'text', '#383838'); await page.wait_for_timeout(700)
            w = await page.evaluate("({base:data.cfg.theme.base, custom:data.cfg.theme.custom, warn:document.getElementById('themeWarn').textContent, name:document.getElementById('swBaseName').textContent, bg:getComputedStyle(document.body).backgroundColor})")
            check("3.3: свои фон/карточки/текст → base=custom, значения сохранены; контраст текста ниже 4.5:1 → «Текст может плохо читаться» (сохранить можно)", w["base"] == "custom" and w["custom"] == {"from": "oled", "bg": "#202020", "surface": "#303030", "text": "#383838"} and w["warn"] == "Текст может плохо читаться" and w["bg"] == rgb("#202020"), w)
            await pick(page, 'text', '#f0f0f0')
            check("3.3: хороший контраст — предупреждение исчезает", await page.evaluate("document.getElementById('themeWarn').textContent") == "")
            # reset
            await page.click('[data-act="themeResetAsk"]'); await page.wait_for_timeout(150)
            check("3.4: «Сбросить к стандартной» — с подтверждением", "Сбросить тему?" in await page.inner_text("#dlg"))
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(100)
            check("3.4: «Отмена» тему не трогает", await page.evaluate("data.cfg.theme.base") == "custom")
            await page.click('[data-act="themeResetAsk"]'); await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(700)
            rs = await page.evaluate("({t:data.cfg.theme, acc:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(), bgInline:document.documentElement.style.getPropertyValue('--bg')})")
            check("3.4: после подтверждения — «Как в Telegram», акцент #ff9f0a, свои цвета очищены, inline-переопределения фона сняты", rs["t"] == {"base": "tg", "accent": "#ff9f0a", "accent2": None, "rest": "#30d158", "custom": {}} and rs["acc"] == "#ff9f0a" and rs["bgInline"] == "", rs)
            await page.evaluate("document.documentElement.style.setProperty('--tg-theme-bg-color','#123456'); 0")
            check("3.2: «Как в Telegram» берёт фон из themeParams (--tg-theme-bg-color)", await page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(18, 52, 86)")
            await page.evaluate("document.documentElement.style.removeProperty('--tg-theme-bg-color'); 0")

            # ---- приёмка: каждая основа × 3 акцента читаема
            bases = json.loads(await page.evaluate("JSON.stringify(THEME_BASES.filter(b=>b.id!=='tg'))"))
            accents = json.loads(await page.evaluate("JSON.stringify(ACCENT_COLORS)"))
            ok_text = all(contrast(b["text"], b["surface"]) >= 4.5 and contrast(b["text"], b["bg"]) >= 4.5 and contrast(b["muted"], b["surface"]) >= 3 for b in bases)
            ink = await page.evaluate("ACCENT_COLORS.map(c=>accentBtnText(c[1]))")
            ok_acc = all(contrast(c[1], i) >= 4.5 for c, i in zip(accents, ink))
            check("приёмка: во всех 5 готовых основах текст/карточки ≥ 4.5:1, приглушённый ≥ 3:1; на всех 12 акцентах текст кнопки ≥ 4.5:1", ok_text and ok_acc and len(accents) == 12, (ok_text, ok_acc))
            screens = {"день": "ui.tab='day'; ui.themeScreen=false; render()", "календарь": "ui.tab='cal'; render()", "прогресс-сводка": "ui.tab='prg'; ui.progMode='summary'; render()", "прогресс-упражнение": "ui.tab='prg'; ui.progMode='ex'; progEx='Молотки, свободный вес или блок'; render()", "шаблоны": "ui.tab='tpl'; render()", "настройки": "ui.tab='set'; render()", "тема": "ui.tab='set'; ui.themeScreen=true; render()"}
            bad = []
            await page.evaluate("curDate='2026-10-07'; delete data.log[curDate]; delete ui.drafts[curDate]; applyTemplate(data.templates.find(x=>x.id==='fb6c7mc')); 0")
            for b in bases:
                for acc in ("#ff9f0a", "#3b82f6", "#30d158"):
                    await page.evaluate("(a)=>{ data.cfg.theme={base:a[0],accent:a[1],accent2:null,custom:{}}; data.cfg.accent=a[1]; applyTheme(); 0 }", [b["id"], acc])
                    for name, js_ in screens.items():
                        await page.evaluate(js_ + "; 0")
                        r = await page.evaluate(CONTRAST_JS)
                        if r["textSurf"] < 4.5 or r["textBg"] < 4.5 or r["onAcc"] < 4.5 or not r["scroll"]: bad.append((b["id"], acc, name, r))
            check("приёмка: основа × 3 акцента × 7 экранов — текст, кнопки на акценте читаемы, без горизонтальной прокрутки", not bad, bad[:2])
            check("нет pageerror", not errs, errs[:2])
            await page.evaluate("data.cfg.theme={base:'warm',accent:'#8b5cf6',accent2:'#ff453a',custom:{}}; applyTheme(); ui.tab='day'; render(); 0")
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_theme_warm.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
