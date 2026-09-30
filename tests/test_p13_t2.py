"""Фаза 13, задача 2: числа в степперах и строках подходов отцентрированы по вертикали."""
import asyncio, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")


def measure(scope):
    return """(()=>{
  const ctr=(el)=>{ const r=document.createRange(); r.selectNodeContents(el); const b=r.getBoundingClientRect(); return (b.top+b.bottom)/2; };
  const mid=(el)=>{ const b=el.getBoundingClientRect(); return (b.top+b.bottom)/2; };
  const out={val:[], cell:[], row:[], ai:[], disp:[]};
  const scope=document.querySelector('%s');
  scope.querySelectorAll('.stepper .val').forEach(v=>{ out.val.push(Math.abs(ctr(v.querySelector('.vw')||v)-mid(v))); out.disp.push(getComputedStyle(v).display+'/'+getComputedStyle(v).alignItems+'/'+getComputedStyle(v).justifyContent+'/'+getComputedStyle(v).lineHeight); });
  scope.querySelectorAll('.set-row .cell').forEach(v=>{ out.cell.push(Math.abs(ctr(v.querySelector('.vw')||v)-mid(v))); });
  scope.querySelectorAll('.set-row, .set-next').forEach(row=>{ const rm=mid(row); const idx=row.querySelector('.idx'), c=row.querySelector('.cell,.val'), x=row.querySelector('.del-set svg,.check svg');
     out.row.push(Math.max(Math.abs(ctr(idx)-rm), x?Math.abs(mid(x)-rm):0, c?Math.abs(ctr(c.querySelector('.vw')||c)-rm):0)); });
  scope.querySelectorAll('.vw').forEach(w=>{ if(w.querySelector('.u')) out.ai.push(getComputedStyle(w).alignItems); });
  return out; })()""" % scope

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            seed(dump)
            page, errs = await open_tg(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            check("версия 2.13.0", await page.evaluate("APP_VERSION") == "2.13.0")
            await page.evaluate("""(()=>{ const k=toKey(new Date()); const ex=newEx('Жим лёжа','3х8-12',null); ex.sets=[{w:70,r:8},{w:72.5,r:10}]; const ex2=newEx('Сведения','2х10-15',null);
                commitDay(k,{title:'Тест',exercises:[ex,ex2]}); curDate=k; ui.tab='day'; render(); })()"""); await page.wait_for_timeout(300)
            css = open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read()
            check("2: у степпера и ячейки: display:flex; align-items:center; justify-content:center; line-height:1 (CSS)",
                  ".stepper .val{display:flex; align-items:center; justify-content:center; line-height:1;" in css and ".set-row .cell{display:flex; align-items:center; justify-content:center; line-height:1;" in css)
            check("2: «кг» выровнена по базовой линии числа (внутренняя обёртка .vw, align-items:baseline)", ".vw{display:flex; align-items:baseline;" in css)
            for (w, fs) in [(390, 0.9), (390, 1), (390, 1.15), (390, 1.3), (320, 1), (320, 1.3)]:
                await page.set_viewport_size({"width": w, "height": 844})
                await page.evaluate("data.cfg.fontScale=%s; applyFontScale(); render(); 0" % fs); await page.wait_for_timeout(200)
                m = await page.evaluate(measure("#app"))
                worst = max(m["val"] + m["cell"] + m["row"])
                check("2: карточка упражнения %dpx/%d%%: число в степпере, ячейки, номер и значки строки — по центру по вертикали (макс. отклонение %.2fpx)" % (w, fs * 100, worst), m["val"] and m["cell"] and worst <= 1.5, m)
                check("2: %dpx/%d%%: .val — flex, по центру, line-height 1; «кг» по базовой линии" % (w, fs * 100), all(d.startswith("flex/center/center/") for d in m["disp"]) and set(m["ai"]) == {"baseline"}, (m["disp"][:1], m["ai"][:1]))
            await page.set_viewport_size({"width": 390, "height": 844}); await page.evaluate("data.cfg.fontScale=1; applyFontScale(); ui.tab='set'; ui.themeScreen=true; render(); 0"); await page.wait_for_timeout(200)
            for fs in (0.9, 1, 1.3):
                await page.evaluate("data.cfg.fontScale=%s; applyFontScale(); 0" % fs); await page.wait_for_timeout(150)
                m = await page.evaluate(measure("#themePreview"))
                worst = max(m["val"] + m["cell"] + m["row"])
                check("2: превью темы %d%%: число в степпере по центру (откл. %.2fpx)" % (fs * 100, worst), m["val"] and worst <= 1.5, m)
            check("нет pageerror", not errs, errs[:2])
            await page.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_p13_t2.png"))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
