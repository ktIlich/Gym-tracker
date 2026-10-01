"""Фаза 13, задача 4: свой пикер цвета (нижний лист): круг, яркость, HEX, недавние, отмена/готово."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")

def rgbhex(s):
    m = re.match(r"rgb\((\d+), (\d+), (\d+)", s); return "#%02x%02x%02x" % tuple(map(int, m.groups()))

async def open_pick(page, tok):
    await page.click('[data-act="colorOpen"][data-tok="%s"]' % tok); await page.wait_for_timeout(200)

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    src = open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read()
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            check("4: системный <input type=\"color\"> не используется, внешних библиотек нет", 'type="color"' not in src )
            seed(dump)
            page, errs = await open_tg(browser)
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.click('button[data-tab="set"]'); await page.click('[data-act="themeOpen"]'); await page.wait_for_timeout(250)
            await open_pick(page, "accent")
            scroll0 = await page.evaluate("scrollY")
            lay = await page.evaluate("""(()=>{ const sh=document.querySelector('.cp-sheet'); const q=(s)=>document.querySelector(s).getBoundingClientRect(); const s=sh.getBoundingClientRect();
                const order=['.cp-title','#cpWheel','#cpSlider','#cpHex','#cpRecent','#cpWarn','.cp-btns'].map(x=>q(x).top);
                const fs=parseFloat(getComputedStyle(document.documentElement).fontSize); const w=q('#cpWheel'), m=q('#cpMarker'), th=q('#cpThumb'), sl=q('#cpSlider');
                return {title:document.querySelector('.cp-title').textContent, x:!!document.querySelector('.cp-x svg'), order, wheelW:w.width, wheelRem:w.width/fs, centered:Math.abs((w.left+w.right)/2-innerWidth/2)<2, marker:m.width/fs, markerBorder:getComputedStyle(document.getElementById('cpMarker')).borderTopWidth+' '+getComputedStyle(document.getElementById('cpMarker')).borderTopColor,
                    thumb:th.width/fs, sliderW:sl.width, hexFont:getComputedStyle(document.getElementById('cpHex')).fontFamily, ta:[getComputedStyle(document.querySelector('.cp-wheelbox')).touchAction, getComputedStyle(document.getElementById('cpSlider')).touchAction],
                    btns:[...document.querySelectorAll('.cp-btns button')].map(b=>b.textContent), btnRow:new Set([...document.querySelectorAll('.cp-btns button')].map(b=>Math.round(b.getBoundingClientRect().top))).size,
                    sheetTop:s.top, sheetBottom:s.bottom, vh:innerHeight, fits:sh.scrollHeight<=sh.clientHeight+1, pair:[!!document.getElementById('cpWas'),!!document.getElementById('cpNow')], hexVal:document.getElementById('cpHex').value, back:currentBackAction()!==null}; })()""")
            check("4.1: лист: заголовок «Акцент» и крестик; сверху вниз: круг, слайдер, образцы+HEX, недавние, предупреждение, кнопки", lay["title"] == "Акцент" and lay["x"] and lay["order"] == sorted(lay["order"]), lay["order"])
            check("4.1: круг ≈ 16rem по центру; маркер 1.5rem с белой обводкой; бегунок слайдера 1.75rem; кнопки «Отмена»/«Готово» в одном ряду", abs(lay["wheelRem"] - 16) < 0.3 and lay["centered"] and abs(lay["marker"] - 1.5) < 0.05 and lay["markerBorder"].startswith("2px rgb(255, 255, 255)") and abs(lay["thumb"] - 1.75) < 0.05 and lay["btns"] == ["Отмена", "Готово"] and lay["btnRow"] == 1, lay)
            check("4.1: образцы «было → стало», HEX моноширинный; touch-action:none на круге и слайдере", lay["pair"] == [True, True] and "mono" in lay["hexFont"].lower() and lay["ta"] == ["none", "none"], lay["hexFont"])
            check("4.2: лист целиком на экране iPhone 13 (390×844), прокрутка внутри не нужна; открыт с цветом токена (#FF9F0A)", lay["sheetTop"] >= 0 and lay["sheetBottom"] <= lay["vh"] + 0.5 and lay["fits"] and lay["hexVal"] == "#FF9F0A", (lay["sheetTop"], lay["sheetBottom"], lay["fits"], lay["hexVal"]))
            px = await page.evaluate("""(()=>{ const c=document.getElementById('cpWheel'); const x=c.getContext('2d'); const W=c.width; const at=(fx,fy)=>Array.from(x.getImageData(Math.round(fx*W),Math.round(fy*W),1,1).data); return {center:at(.5,.5), right:at(.97,.5), bottom:at(.5,.97), corner:at(.02,.02), w:W}; })()""")
            check("4.1: круг нарисован в canvas: центр белый, справа красный (тон 0°), снизу — тон 90° (зелёно-жёлтый), за кругом прозрачно", px["center"][0] > 240 and px["center"][1] > 240 and px["center"][2] > 240 and px["right"][0] > 240 and px["right"][1] < 60 and px["bottom"][1] > 200 and px["bottom"][2] < 120 and px["corner"][3] == 0, px)
            # маркер по текущему цвету: #ff9f0a → тон ≈ 37°, насыщ. ≈ 0.96
            mk = await page.evaluate("(()=>{ const w=document.getElementById('cpWheel').getBoundingClientRect(), m=document.getElementById('cpMarker').getBoundingClientRect(); const R=w.width/2, dx=(m.left+m.right)/2-(w.left+R), dy=(m.top+m.bottom)/2-(w.top+R); return {h:(Math.atan2(dy,dx)*180/Math.PI+360)%360, s:Math.hypot(dx,dy)/R, thumb:(document.getElementById('cpThumb').getBoundingClientRect().left+14-document.getElementById('cpSlider').getBoundingClientRect().left)/document.getElementById('cpSlider').getBoundingClientRect().width}; })()")
            check("4.2: маркер и бегунок выставлены по текущему цвету (тон ≈ 37°, насыщенность ≈ 0.96, яркость 100%)", abs(mk["h"] - 37.4) < 2 and abs(mk["s"] - 0.96) < 0.03 and mk["thumb"] > 0.97, mk)
            # перетаскивание по кругу
            w = await page.evaluate("(()=>{ const r=document.getElementById('cpWheel').getBoundingClientRect(); return [r.left,r.top,r.width]; })()")
            cx, cy, R = w[0] + w[2] / 2, w[1] + w[2] / 2, w[2] / 2
            acc0 = await page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()")
            await page.mouse.move(cx + R * 0.5, cy); await page.mouse.down(); await page.mouse.move(cx, cy + R * 0.8, steps=6); await page.wait_for_timeout(120)
            mid = await page.evaluate("({hex:document.getElementById('cpHex').value, accent:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(), scroll:scrollY, down:true})")
            await page.mouse.up(); await page.wait_for_timeout(100)
            check("4.2: перетаскивание по кругу меняет H и S, HEX обновляется, акцент в превью меняется сразу (:root), страница не прокручивается", mid["hex"].lower() == mid["accent"].lower() and mid["accent"] != acc0 and mid["scroll"] == scroll0, (mid, acc0))
            dragged_hex = mid["hex"]
            # слайдер яркости
            sl = await page.evaluate("(()=>{ const r=document.getElementById('cpSlider').getBoundingClientRect(); return [r.left,r.top+r.height/2,r.width]; })()")
            await page.mouse.move(sl[0] + sl[2] * 0.9, sl[1]); await page.mouse.down(); await page.mouse.move(sl[0] + sl[2] * 0.4, sl[1], steps=5); await page.mouse.up(); await page.wait_for_timeout(120)
            v = await page.evaluate("({hex:document.getElementById('cpHex').value, accent:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(), dim:document.getElementById('cpDim').style.opacity, bg:document.getElementById('cpSlider').style.background})")
            check("4.2: слайдер яркости затемняет цвет (HEX темнее), градиент слайдера — от чёрного к цвету при полной яркости", v["hex"] != dragged_hex and v["hex"].lower() == v["accent"].lower() and abs(float(v["dim"]) - 0.6) < 0.06 and "linear-gradient" in v["bg"], v)
            # HEX → маркер
            await page.fill("#cpHex", "#3A7BD5"); await page.wait_for_timeout(150)
            hx = await page.evaluate("(()=>{ const w=document.getElementById('cpWheel').getBoundingClientRect(), m=document.getElementById('cpMarker').getBoundingClientRect(); const R=w.width/2, dx=(m.left+m.right)/2-(w.left+R), dy=(m.top+m.bottom)/2-(w.top+R); return {h:(Math.atan2(dy,dx)*180/Math.PI+360)%360, s:Math.hypot(dx,dy)/R, accent:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(), bad:document.getElementById('cpHex').classList.contains('bad')}; })()")
            check("4.2: ввод HEX двигает маркер (#3A7BD5: тон ≈ 213°), акцент в превью тот же, рамка не красная", abs(hx["h"] - 213.2) < 2 and abs(hx["s"] - 0.75) < 0.03 and hx["accent"] == "#3a7bd5" and not hx["bad"], hx)
            await page.fill("#cpHex", "#12zz"); await page.wait_for_timeout(100)
            bad = await page.evaluate("({bad:document.getElementById('cpHex').classList.contains('bad'), border:getComputedStyle(document.getElementById('cpHex')).borderTopColor, acc:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()})")
            check("4.1: невалидный HEX — красная обводка, цвет темы не меняется", bad["bad"] and bad["border"] == "rgb(248, 113, 113)" and bad["acc"] == "#3a7bd5", bad)
            await page.fill("#cpHex", "3a7bd5"); await page.wait_for_timeout(100)
            check("4.1: HEX принимается и без «#»", not await page.evaluate("document.getElementById('cpHex').classList.contains('bad')"))
            # отмена
            await page.click('#cpick .cp-btns [data-cp="cancel"]'); await page.wait_for_timeout(200)
            c = await page.evaluate("({open:!!document.getElementById('cpick'), acc:data.cfg.theme.accent, css:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(), recent:data.cfg.recentColors, back:currentBackAction()})")
            check("4.2: «Отмена» возвращает прежнее значение (#ff9f0a) и закрывает лист; в облако ничего не записано, недавние пусты", not c["open"] and c["acc"] == "#ff9f0a" and c["css"] == "#ff9f0a" and c["recent"] == [] and '"accent":"#3a7bd5"' not in STORE["tst_cfg"] and c["back"] is None, c)
            # готово
            await open_pick(page, "accent"); await page.fill("#cpHex", "#3A7BD5"); await page.click('#cpick [data-cp="done"]'); await page.wait_for_timeout(300)
            d = await page.evaluate("({acc:data.cfg.theme.accent, recent:data.cfg.recentColors, css:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(), set:document.querySelector('.swatch.custom[data-custom=accent]').classList.contains('set'), cap:document.querySelectorAll('.sw-picked')[1].textContent})")
            check("4.2: «Готово» сохраняет: cfg.theme.accent, облако, «недавние», образец «Свой» залит и подписан «свой #3A7BD5»", d["acc"] == "#3a7bd5" and d["recent"] == ["#3a7bd5"] and '"accent":"#3a7bd5"' in STORE["tst_cfg"] and '"recentColors":["#3a7bd5"]' in STORE["tst_cfg"] and d["set"] and d["cap"] == "Выбрано: свой #3A7BD5", d)
            # заголовки по токену
            titles = {}
            for tok in ["accent2", "rest", "bg", "surface", "text"]:
                await open_pick(page, tok); titles[tok] = await page.inner_text(".cp-title"); await page.click('#cpick .cp-btns [data-cp="cancel"]'); await page.wait_for_timeout(100)
            check("4.1: заголовок по токену: Дополнительный цвет / Неделя отдыха / Фон / Карточки / Текст", titles == {"accent2": "Дополнительный цвет", "rest": "Неделя отдыха", "bg": "Фон", "surface": "Карточки", "text": "Текст"}, titles)
            # фон: живое применение к превью и странице
            await open_pick(page, "bg"); await page.fill("#cpHex", "#202020"); await page.wait_for_timeout(150)
            live = await page.evaluate("({body:getComputedStyle(document.body).backgroundColor, prev:getComputedStyle(document.getElementById('themePreview')).backgroundColor, base:data.cfg.theme.base})")
            check("4.2: выбор фона применяется к странице сразу (base → свои цвета), до нажатия «Готово»", live["body"] == "rgb(32, 32, 32)" and live["base"] == "custom", live)
            await page.click('#cpick .cp-btns [data-cp="cancel"]'); await page.wait_for_timeout(150)
            check("4.2: «Отмена» возвращает и основу: base снова «Как в Telegram»", await page.evaluate("data.cfg.theme.base") == "tg" and await page.evaluate("data.cfg.theme.custom") == {})
            # предупреждение о контрасте
            await open_pick(page, "bg"); await page.fill("#cpHex", "#202020"); await page.click('#cpick [data-cp="done"]'); await page.wait_for_timeout(150)
            await open_pick(page, "text"); await page.fill("#cpHex", "#383838"); await page.wait_for_timeout(200)
            warn = await page.inner_text("#cpWarn")
            check("4.1: слабый контраст — в листе «Текст может плохо читаться»", warn == "Текст может плохо читаться", warn)
            await page.fill("#cpHex", "#f0f0f0"); await page.wait_for_timeout(200)
            check("4.1: контраст хороший — предупреждение исчезает", await page.inner_text("#cpWarn") == "")
            await page.click('#cpick .cp-btns [data-cp="cancel"]'); await page.wait_for_timeout(100)
            await page.evaluate("data.cfg.theme={base:'tg',accent:'#ff9f0a',accent2:null,rest:'#30d158',custom:{}}; data.cfg.accent='#ff9f0a'; applyTheme(); themeMarks(); 0")
            # недавние: до 8
            for i in range(10):
                await open_pick(page, "accent"); await page.fill("#cpHex", "#%02x%02x%02x" % (20 + i * 20, 90, 200 - i * 10)); await page.click('#cpick [data-cp="done"]'); await page.wait_for_timeout(80)
            rec = await page.evaluate("data.cfg.recentColors")
            check("4.1: «Недавние»: не больше 8, новые впереди, без повторов (cfg.recentColors)", len(rec) == 8 and rec[0] == "#%02x%02x%02x" % (20 + 9 * 20, 90, 200 - 90) and len(set(rec)) == 8, rec)
            await open_pick(page, "accent")
            rc = await page.evaluate("({n:document.querySelectorAll('.cp-rc').length, size:document.querySelector('.cp-rc').getBoundingClientRect().width})")
            await page.click('.cp-rc:nth-child(3)'); await page.wait_for_timeout(120)
            picked = await page.evaluate("document.getElementById('cpHex').value.toLowerCase()")
            check("4.1: в листе 8 кружков недавних (≥ 44px); тап по ним выбирает цвет", rc["n"] == 8 and rc["size"] >= 43.5 and picked == rec[2], (rc, picked, rec[2]))
            # закрытие: BackButton, фон, свайп
            check("4.2: BackButton закрывает лист как «Отмена»", await page.evaluate("currentBackAction()!==null"))
            await page.evaluate("currentBackAction()(); 0"); await page.wait_for_timeout(150)
            check("4.2: после BackButton лист закрыт, цвет прежний", not await page.evaluate("!!document.getElementById('cpick')") and await page.evaluate("data.cfg.theme.accent") == rec[0])
            await open_pick(page, "accent")
            sh = await page.evaluate("(()=>{ const r=document.querySelector('.cp-head').getBoundingClientRect(); return [r.left+40, r.top+20]; })()")
            await page.mouse.move(sh[0], sh[1]); await page.mouse.down(); await page.mouse.move(sh[0], sh[1] + 140, steps=6); await page.mouse.up(); await page.wait_for_timeout(300)
            check("4.2: свайп вниз по шапке закрывает лист", not await page.evaluate("!!document.getElementById('cpick')"))
            await open_pick(page, "accent")
            await page.mouse.move(sh[0], sh[1]); await page.mouse.down(); await page.mouse.move(sh[0], sh[1] + 30, steps=3); await page.mouse.up(); await page.wait_for_timeout(300)
            check("4.2: короткий свайп лист не закрывает (возвращается на место)", await page.evaluate("!!document.getElementById('cpick')") and await page.evaluate("document.querySelector('.cp-sheet').style.transform") == "")
            await page.mouse.click(200, 30); await page.wait_for_timeout(200)
            check("4.2: тап по затемнению закрывает лист (как «Отмена»)", not await page.evaluate("!!document.getElementById('cpick')"))
            # 320px и 130%
            for w_, fs in [(320, 1), (320, 1.3), (390, 1.3)]:
                await page.set_viewport_size({"width": w_, "height": 640 if w_ == 320 else 844})
                await page.evaluate("data.cfg.fontScale=%s; applyFontScale(); render(); 0" % fs); await page.wait_for_timeout(200)
                await open_pick(page, "accent")
                g = await page.evaluate("""(()=>{ const sh=document.querySelector('.cp-sheet'), s=sh.getBoundingClientRect(); const W=innerWidth; const bad=[...sh.querySelectorAll('*')].filter(e=>{const r=e.getBoundingClientRect(); return r.width&&(r.right>W+1||r.left<-1);}).length;
                    const wh=document.getElementById('cpWheel').getBoundingClientRect(); return {inView:s.top>=0&&s.bottom<=innerHeight+0.5, bad, scrollX:document.documentElement.scrollWidth<=W, wheel:wh.width, round:Math.abs(wh.width-wh.height)<1, btns:[...document.querySelectorAll('.cp-btns button')].map(b=>Math.round(b.getBoundingClientRect().height))}; })()""")
                check("4: %dpx, шрифт %d%%: лист в пределах экрана, ничего не вылезает по ширине, круг круглый (%dpx), кнопки ≥ 44px" % (w_, fs * 100, g["wheel"]), g["inView"] and g["bad"] == 0 and g["scrollX"] and g["round"] and min(g["btns"]) >= 43, g)
                # перетаскивание всё равно попадает по маркеру
                wr = await page.evaluate("(()=>{ const r=document.getElementById('cpWheel').getBoundingClientRect(); return [r.left,r.top,r.width]; })()")
                await page.mouse.click(wr[0] + wr[2] * 0.8, wr[1] + wr[2] * 0.5); await page.wait_for_timeout(100)
                check("4: %dpx/%d%%: касание круга выбирает цвет (HEX изменился)" % (w_, fs * 100), await page.evaluate("document.getElementById('cpHex').value.toLowerCase()") != "#" + "ff9f0a")
                await page.click('#cpick .cp-btns [data-cp="cancel"]'); await page.wait_for_timeout(100)
            check("нет pageerror", not errs, errs[:2])
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_p13_t4.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
