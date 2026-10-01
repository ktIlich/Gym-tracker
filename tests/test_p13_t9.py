"""Фаза 13, задача 9: работа в браузере (вне Telegram): строка-предупреждение, скачивание копии, автокопия-диалог."""
import asyncio, json, os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, WRITES, check, RESULTS, REPO, BASE
from test_task7 import seed, open_tg
from test_task4 import new_page, ensure_xlsx_lib
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
WARN = "Открыто в браузере: данные хранятся только здесь и не синхронизируются с Telegram"

def iso_ago(days): return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - days * 86400))

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8")); dump["cfg"]["onboardingSeen"] = 1
    ensure_xlsx_lib()
    src = open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read()
    srv = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py"), "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            check("9.2: IN_TG = !!Telegram.WebApp.initData; canSendBackup и canDownload используют его", "const IN_TG = !!(window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData);" in src and "function canDownload(){ return !IN_TG; }" in src)

            # ---------- браузер (без Telegram)
            d = json.loads(json.dumps(dump)); d["cfg"]["lastBackup"] = iso_ago(1); d["cfg"]["backupReminderDays"] = 14
            page, errs = await new_page(browser, d, mock=False, snooze=False)
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            check("9.2: в браузере IN_TG = false", await page.evaluate("IN_TG") is False)
            w = await page.evaluate("(()=>{ const e=document.getElementById('brWarn'); if(!e) return null; const r=e.getBoundingClientRect(), h=document.querySelector('header').getBoundingClientRect(); return {txt:e.querySelector('.br-txt').firstChild.textContent.trim(), link:(e.querySelector('.br-link')||{}).href||'', linkTxt:(e.querySelector('.br-link')||{}).textContent||'', target:(e.querySelector('.br-link')||{}).target||'',  below:r.top>=h.bottom-0.5, x:!!e.querySelector('.br-x'), xH:e.querySelector('.br-x')?e.querySelector('.br-x').getBoundingClientRect().height:0, w:r.width, vw:innerWidth}; })()")
            check("9.2: под шапкой постоянная строка-предупреждение: «%s»" % WARN, w and w["txt"] == WARN and w["link"] == "https://t.me/gymtracker_ktilcih_bot" and w["linkTxt"] == "Открыть бота в Telegram" and w["target"] == "_blank" and w["below"] and w["x"] and w["xH"] >= 43.5 and w["w"] <= w["vw"], w)
            for tab in ("cal", "tpl", "prg", "set", "day"):
                await page.click('button[data-tab="%s"]' % tab); await page.wait_for_timeout(120)
                assert await page.locator("#brWarn").count() == 1, tab
            check("9.2: строка видна на всех вкладках", True)
            await page.click('#brWarn [data-act="brWarnToggle"]'); await page.wait_for_timeout(200)
            c = await page.evaluate("(()=>{ const e=document.getElementById('brWarn'); return {cls:e.className, hasTxt:!!e.querySelector('.br-txt'), svg:!!e.querySelector('svg.icon'), h:e.getBoundingClientRect().height, ls:localStorage.getItem('tst_br_warn')}; })()")
            check("9.2: строка сворачивается до значка ⓘ (44×44), состояние сохраняется в localStorage", c["cls"] == "br-info" and not c["hasTxt"] and c["svg"] and c["h"] >= 43.5 and c["ls"] == "0", c)
            await page.reload(); await page.wait_for_timeout(2500)
            check("9.2: после перезагрузки остаётся свёрнутой", await page.evaluate("document.getElementById('brWarn').className") == "br-info")
            await page.click('#brWarn'); await page.wait_for_timeout(200)
            check("9.2: тап по значку разворачивает строку обратно", await page.evaluate("document.getElementById('brWarn').className") == "br-warn" and await page.evaluate("localStorage.getItem('tst_br_warn')") == "1")

            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            bl = await page.evaluate("(()=>{ const a=document.getElementById('botLink'); return a&&{href:a.href, target:a.target, rel:a.rel, txt:a.textContent.trim(), h:a.getBoundingClientRect().height, tag:a.tagName}; })()")
            check("ссылка на бота: в «Настройках → Помощь» строка «Бот в Telegram · @gymtracker_ktilcih_bot» — ссылка https://t.me/gymtracker_ktilcih_bot (новая вкладка, noopener), высота ≥ 44", bl and bl["tag"] == "A" and bl["href"] == "https://t.me/gymtracker_ktilcih_bot" and bl["target"] == "_blank" and "noopener" in bl["rel"] and bl["txt"].startswith("Бот в Telegram") and bl["h"] >= 43.5, bl)
            # резервная копия: скачивание трёх форматов
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(200)
            sec = await page.evaluate("({send:[...document.querySelectorAll('[data-act=sendBackup]')].length, dl:['backupDownload','export','exportCsv'].map(a=>document.querySelectorAll('[data-act='+a+']').length), txt:document.querySelector('[data-tour=set-backup]').textContent})")
            check("9.2: в браузере вместо «Отправить в чат» — «Скачать» JSON / Excel / CSV", sec["send"] == 0 and sec["dl"] == [1, 1, 1] and "Отправить в чат" not in sec["txt"] and "Скачать файл" in sec["txt"], sec)
            got = {}
            for act, ext in [("backupDownload", "json"), ("export", "xlsx"), ("exportCsv", "csv")]:
                try:
                    async with page.expect_download(timeout=8000) as dl:
                        await page.click('[data-act="%s"]' % act)
                    f = await dl.value; got[ext] = f.suggested_filename
                except Exception as e:
                    got[ext] = "ERR " + str(e)[:60]
            check("9.2: «Скачать» отдаёт три формата файлом: JSON, Excel, CSV", all(got.get(x, "").endswith("." + x) for x in ("json", "xlsx", "csv")), got)
            # JSON обновляет lastBackup
            lb = await page.evaluate("Date.now()-new Date(data.cfg.lastBackup).getTime()<20000")
            check("9.2: скачивание JSON обновляет lastBackup", lb)
            check("9.2: восстановление и импорт доступны как в Telegram (кнопки «Восстановить из копии», импорт Excel/CSV)", await page.locator('[data-act="import"]').count() == 1 and await page.locator('[data-act="backupRestoreOpen"], [data-act="backupParse"], [data-tour=set-backup] .wide-btn').count() >= 3)

            # клонирование скрыто
            await page.evaluate("ui.testScreen=true; render(); 0"); await page.wait_for_timeout(200)
            cl = await page.evaluate("({clone:document.querySelectorAll('[data-act=cloneProd]').length, diag:document.querySelectorAll('[data-act=diagOpen]').length})")
            check("9.2: клонирование в браузере доступно (читает localStorage основной версии — см. test_prod_prep)", cl["clone"] == 1, cl)
            check("нет pageerror (браузер)", not errs, errs[:2])
            await page.context.close()

            # ---------- автокопия в браузере: просрочена → диалог
            d2 = json.loads(json.dumps(dump)); d2["cfg"]["lastBackup"] = iso_ago(30); d2["cfg"]["backupReminderDays"] = 14; d2["cfg"]["autoBackup"] = True
            page, errs = await new_page(browser, d2, mock=False, snooze=False)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2800)
            dlg = await page.evaluate("(()=>{ const d=document.getElementById('dlg'); return d?{title:d.querySelector('.dlg-title').textContent, text:d.querySelector('.dlg-text').textContent, btns:[...d.querySelectorAll('[data-dlg]')].map(b=>b.textContent)}:null; })()")
            check("9.2: автокопия в браузере при просрочке — диалог «Пора сделать копию» с кнопками «Скачать JSON» и «Позже» (без фоновой отправки)", dlg and dlg["title"] == "Пора сделать копию" and dlg["btns"] == ["Скачать JSON", "Позже"] and "30 дней назад" in dlg["text"], dlg)
            async with page.expect_download(timeout=8000) as dl:
                await page.click('#dlg [data-dlg="0"]')
            f = await dl.value; await page.wait_for_timeout(300)
            lb = await page.evaluate("Date.now()-new Date(data.cfg.lastBackup).getTime()<20000")
            check("9.2: «Скачать JSON» скачивает файл и обновляет lastBackup; диалог закрыт", f.suggested_filename.endswith(".json") and lb and await page.locator("#dlg").count() == 0, f.suggested_filename)
            await page.reload(); await page.wait_for_timeout(2800)
            check("9.2: после скачивания диалог при следующем запуске не появляется", await page.locator("#dlg").count() == 0)
            check("нет pageerror (автокопия)", not errs, errs[:2])
            await page.context.close()

            d3 = json.loads(json.dumps(dump)); d3["cfg"]["lastBackup"] = iso_ago(30); d3["cfg"]["backupReminderDays"] = 14
            page, errs = await new_page(browser, d3, mock=False, snooze=False)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2800)
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(300)
            sn = await page.evaluate("({left:(data.cfg.backupSnooze-Date.now())/3600000, dlg:!!document.getElementById('dlg')})")
            check("9.2: «Позже» — snooze на 24 часа, lastBackup не меняется", 23.5 < sn["left"] <= 24.01 and not sn["dlg"] and await page.evaluate("Date.now()-new Date(data.cfg.lastBackup).getTime()>20*86400000"), sn)
            await page.reload(); await page.wait_for_timeout(2800)
            check("9.2: в период snooze диалог не показывается", await page.locator("#dlg").count() == 0)
            await page.context.close()

            # ---------- внутри Telegram: поведение прежнее
            seed(dump)
            tgp, errs = await open_tg(browser)
            await tgp.set_viewport_size({"width": 390, "height": 844})
            await tgp.goto(BASE + "/test/index.html"); await tgp.wait_for_timeout(2500)
            check("9.2: в Telegram (initData есть) IN_TG = true, строки-предупреждения нет", await tgp.evaluate("IN_TG") is True and await tgp.locator("#brWarn").count() == 0)
            await tgp.click('button[data-tab="set"]'); await tgp.wait_for_timeout(200)
            dls = await tgp.evaluate("['backupDownload','export','exportCsv'].map(a=>document.querySelectorAll('[data-act='+a+']').length)")
            check("9.2: в Telegram кнопок «Скачать» по-прежнему нет", dls == [0, 0, 0], dls)
            await tgp.evaluate("ui.testScreen=true; render(); 0"); await tgp.wait_for_timeout(200)
            check("9.2: в Telegram клонирование из основной версии на месте", await tgp.locator('[data-act="cloneProd"]').count() == 1)
            check("нет pageerror (Telegram)", not errs, errs[:2])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
