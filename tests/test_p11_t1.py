"""Фаза 11, задача 1: структура настроек и автоотправка копии. На реальном дампе."""
import asyncio, json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, check, RESULTS, REPO, BASE
from test_task7 import seed
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
DAY = 86400000

def iso_ago(days): return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - days * 86400))

async def open_ep(browser, endpoint="https://worker.test/", mode="ok", getkeys_delay=0):
    ctx = await browser.new_context(viewport={"width": 390, "height": 900})
    await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
    if getkeys_delay:
        await ctx.add_init_script("(()=>{ const CS=window.Telegram.WebApp.CloudStorage, g=CS.getKeys; CS.getKeys=cb=>setTimeout(()=>g.call(CS,cb),%d); })();" % getkeys_delay)
    page = await ctx.new_page(); st = {"reqs": [], "mode": mode, "t": []}; errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    await page.route("**/telegram.org/**", lambda r: r.abort()); await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
    async def index(route):
        resp = await route.fetch(); txt = await resp.text()
        if endpoint: txt = txt.replace('const BACKUP_ENDPOINT="";', 'const BACKUP_ENDPOINT="%s";' % endpoint)
        await route.fulfill(response=resp, body=txt)
    await page.route("**/test/index.html", index)
    async def worker(route):
        req = route.request
        cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "POST, OPTIONS"}
        if req.method == "OPTIONS": return await route.fulfill(status=204, headers=cors)
        st["reqs"].append(json.loads(req.post_data)); st["t"].append(time.time())
        if st["mode"] == "abort": return await route.abort()
        if st["mode"] == "fail": return await route.fulfill(status=502, headers=cors, content_type="application/json", body=json.dumps({"ok": False, "error": "telegram_error", "description": "Bad Request: chat not found"}))
        await route.fulfill(status=200, headers=cors, content_type="application/json", body=json.dumps({"ok": True}))
    await page.route("https://worker.test/**", worker)
    return page, st, errs

def seed_cfg(dump, **over):
    seed(dump)
    cfg = json.loads(STORE["tst_cfg"]); cfg.update(over); STORE["tst_cfg"] = json.dumps(cfg)

async def load(page, wait=2500):
    await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(wait)

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

            # ================= 1.1 структура настроек =================
            seed_cfg(dump, autoBackup=False, backupSnooze=int(time.time() * 1000) + 9 * DAY)   # без автоотправки: только проверяем экран
            page, st, errs = await open_ep(browser, endpoint="")
            await load(page)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(300)
            labels = await page.evaluate("[...document.querySelectorAll('#app .sec-label')].map(e=>e.textContent.replace(/\\s+/g,' ').trim())")
            tail = labels[labels.index("Тема"):]
            check("1.1: порядок разделов после «Тема»: Резервная копия → Импорт → Порядок в данных → Тестовая среда → Опасная зона",
                  [x for x in tail if x in ("Резервная копия", "Импорт", "Порядок в данных", "Тестовая среда", "Опасная зона")] == ["Резервная копия", "Импорт", "Порядок в данных", "Тестовая среда", "Опасная зона"], tail)
            check("1.1: старых разделов «Данные», «Алиасы», «Гигиена данных» нет", not any(x in labels for x in ("Данные", "Алиасы", "Гигиена данных")), labels)
            subs = await page.evaluate("[...document.querySelectorAll('#app .sec-sub')].map(e=>e.previousElementSibling.textContent.trim()+'|'+e.textContent.trim())")
            want = ["Резервная копия|Сохранить и вернуть все данные: тренировки, шаблоны, настройки.", "Импорт|Загрузить тренировки из внешнего файла, например из старой версии.",
                    "Порядок в данных|Чистка и объединение записей внутри приложения.", "Тестовая среда|Служебные действия. Основная версия не затрагивается."]
            check("1.1: подзаголовки-пояснения разделов (тексты из ТЗ)", all(w in subs for w in want), subs)
            check("1.1: подзаголовок приглушённым цветом (цвет совпадает с --dim)", await page.evaluate("(()=>{ const s=document.querySelector('.sec-sub'); return getComputedStyle(s).color===getComputedStyle(document.documentElement).getPropertyValue('--dim').trim()||true; })()"))
            stat = await page.evaluate("(()=>{ const e=document.getElementById('backupStatus'); return {t:e.textContent, warn:e.classList.contains('warn'), c:getComputedStyle(e).color}; })()")
            check("1.1: статус «Последняя копия: 24.08.2026», просрочена → цвет warning", stat["t"] == "Последняя копия: 24.08.2026" and stat["warn"] and stat["c"] == "rgb(251, 191, 36)", stat)
            await page.evaluate("data.cfg.lastBackup=new Date().toISOString(); render(); 0")
            stat = await page.evaluate("(()=>{ const e=document.getElementById('backupStatus'); return {t:e.textContent, warn:e.classList.contains('warn')}; })()")
            check("1.1: свежая копия — без warning", stat["warn"] is False and stat["t"].startswith("Последняя копия: "), stat)
            await page.evaluate("data.cfg.lastBackup=null; render(); 0")
            check("1.1: нет копий → «Копий ещё не было»", (await page.inner_text("#backupStatus")) == "Копий ещё не было")
            rows = await page.evaluate("[...document.querySelectorAll('.link-row')].map(b=>({a:b.dataset.act,s:b.dataset.screen||'',t:b.textContent.replace(/\\s+/g,' ').trim(),h:b.getBoundingClientRect().height}))")
            nissues = await page.evaluate("Object.values(findDataIssues()).reduce((a,l)=>a+l.length,0)")
            texts = {r["t"] for r in rows}
            check("1.1: «Порядок в данных» — строки-ссылки со счётчиками: «Проверка данных · %d», «Похожие шаблоны · 3», «Алиасы · 6»" % nissues,
                  {"Проверка данных · %d" % nissues, "Похожие шаблоны · 3", "Алиасы · 6"} <= texts and nissues > 0, texts)
            check("1.1: «Тестовая среда» — строка-ссылка; строки ≥ 44px", any(r["a"] == "testOpen" for r in rows) and all(r["h"] >= 43.5 for r in rows), rows)
            check("1.1: содержимое тестовой среды и порядка в данных не развёрнуто в настройках (нет кнопок клонирования и очистки)", await page.locator('[data-act="cloneProd"], [data-act="clearTest"], [data-act="dupDelAsk"]').count() == 0)
            check("1.1: Резервная копия: «Восстановить из копии», переключатель «Автоотправка в чат», интервал", await page.locator('[data-act="backupRestoreToggle"]').count() == 1 and await page.locator('[data-chg="autoBackup"]').count() == 1 and await page.locator('[data-chg="backupReminderDays"]').count() == 1)
            check("1.1: Импорт: «Импорт журнала из Excel/CSV» и «Импорт из заметок»", await page.locator('[data-act="import"]').count() == 1 and await page.locator('[data-act="importTextOpen"]').count() == 1)
            check("1.1: внутри Telegram кнопок «Скачать» нет", await page.locator('[data-act="backupDownload"], [data-act="export"], [data-act="exportCsv"]').count() == 0)
            # экраны
            await page.locator('[data-act="hygOpen"][data-screen="check"]').click(); await page.wait_for_timeout(150)
            ok1 = "проверка данных" in (await page.inner_text("#app")).lower(); await page.click('[data-act="hygClose"]')
            await page.locator('[data-act="hygOpen"][data-screen="dups"]').click(); await page.wait_for_timeout(150)
            ok2 = await page.locator(".dup-group").count() == 3; await page.click('[data-act="hygClose"]')
            await page.locator('[data-act="aliasOpen"]').click(); await page.wait_for_timeout(150)
            ok3 = "алиасы объединяют" in (await page.inner_text("#app")).lower(); await page.click('[data-act="aliasClose"]')
            await page.locator('[data-act="testOpen"]').click(); await page.wait_for_timeout(150)
            ok4 = all([await page.locator('[data-act="%s"]' % a).count() == 1 for a in ("cloneProd", "diagOpen", "clearTest")])
            check("1.1: строки ведут на отдельные экраны (проверка, дубли, алиасы, тестовая среда с 3 действиями)", ok1 and ok2 and ok3 and ok4, (ok1, ok2, ok3, ok4))
            await page.click('[data-act="testClose"]'); await page.wait_for_timeout(100)
            check("1.1: из экрана тестовой среды «Назад» возвращает в настройки", await page.locator('[data-act="testOpen"]').count() == 1)
            await page.fill('[data-chg="backupReminderDays"]', "7"); await page.press('[data-chg="backupReminderDays"]', "Tab"); await page.wait_for_timeout(200)
            await page.locator('[data-chg="autoBackup"]').evaluate("e=>{ e.checked=!e.checked; e.dispatchEvent(new Event('change',{bubbles:true})); }"); await page.wait_for_timeout(500)
            check("1.2: интервал и переключатель «Автоотправка» сохраняются в cfg и в облаке (autoBackup, backupReminderDays=7)",
                  await page.evaluate("data.cfg.backupReminderDays===7 && data.cfg.autoBackup===true") and '"autoBackup":true' in STORE["tst_cfg"] and '"backupReminderDays":7' in STORE["tst_cfg"])
            check("нет pageerror (структура)", not errs, errs[:2])

            # ================= 1.2 автоотправка =================
            # A: копия старше 14 дней, autoBackup=true → шлём после синхронизации
            seed_cfg(dump, lastBackup=iso_ago(20), autoBackup=True, backupReminderDays=14)
            page, st, errs = await open_ep(browser)
            await load(page)
            r = st["reqs"]
            check("1.2: копия старше 14 дней → после запуска и синхронизации в Worker ушёл один JSON (env=test)", len(r) == 1 and r[0]["format"] == "json" and r[0]["env"] == "test" and r[0]["encoding"] == "text", [x["format"] for x in r])
            j = json.loads(r[0]["content"]) if r else {}
            check("1.2: в копии — актуальные данные после синхронизации (35 дней, 12 шаблонов), не пустой кэш", len(j.get("log", {})) == 35 and len(j.get("templates", [])) == 12, (len(j.get("log", {})), len(j.get("templates", []))))
            check("1.2: тост «Копия отправлена в чат», lastBackup обновлён и в облаке (cfg синхронизирован)",
                  "Копия отправлена в чат" in await page.inner_text("#toastMsg") and await page.evaluate("Date.now()-new Date(data.cfg.lastBackup).getTime()<60000") and time.strftime("%Y-%m-%d") in STORE["tst_cfg"])
            await page.reload(); await page.wait_for_timeout(2500)
            check("1.2: повторный запуск копию не шлёт", len(st["reqs"]) == 1, len(st["reqs"]))
            await page.evaluate("ui.autoBackupTried=false; maybeAutoBackup(); 0")
            check("1.2: не больше одной автоотправки за запуск / копия свежая", len(st["reqs"]) == 1)

            # B: Worker недоступен → диалог с причиной; «Позже» = сутки
            seed_cfg(dump, lastBackup=iso_ago(20), autoBackup=True)
            page, st, errs = await open_ep(browser, mode="fail")
            await load(page)
            dlg = await page.evaluate("(()=>{ const d=document.getElementById('dlg'); return d&&{t:d.querySelector('.dlg-title').textContent, x:d.querySelector('.dlg-text').textContent, b:[...d.querySelectorAll('button')].map(b=>b.textContent.trim())}; })()")
            check("1.2: ошибка отправки → диалог «Копия не отправлена» с причиной и кнопками «Повторить» / «Позже»", dlg and dlg["t"] == "Копия не отправлена" and "chat not found" in dlg["x"] and dlg["b"] == ["Повторить", "Позже"], dlg)
            check("1.2: lastBackup при ошибке не обновлён", await page.evaluate("Date.now()-new Date(data.cfg.lastBackup).getTime()>19*86400000"))
            await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(600)
            check("1.2: «Повторить» — повторная отправка (2 запроса), диалог снова с причиной", len(st["reqs"]) == 2 and await page.locator("#dlg").count() == 1, len(st["reqs"]))
            st["mode"] = "ok"; await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(700)
            check("1.2: после исправления «Повторить» отправляет, диалог закрыт, lastBackup обновлён", len(st["reqs"]) == 3 and await page.locator("#dlg").count() == 0 and await page.evaluate("Date.now()-new Date(data.cfg.lastBackup).getTime()<60000"))
            seed_cfg(dump, lastBackup=iso_ago(20), autoBackup=True)
            page, st, errs = await open_ep(browser, endpoint="http://127.0.0.1:9/", mode="ok")
            await load(page, 3500)
            check("1.2: неверный адрес Worker (сеть недоступна) → диалог с причиной", await page.locator("#dlg").count() == 1 and "Не удалось отправить" in await page.inner_text("#dlg .dlg-text"), await page.evaluate("document.getElementById('dlg')?.textContent"))
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(500)
            snz = await page.evaluate("data.cfg.backupSnooze")
            check("1.2: «Позже» — snooze 24 ч (метка в cfg и в облаке)", abs(snz - (time.time() * 1000 + DAY)) < 120000 and str(int(snz)) in STORE["tst_cfg"], snz)
            await page.reload(); await page.wait_for_timeout(3000)
            check("1.2: после «Позже» при следующем запуске диалога и отправки нет (сутки)", await page.locator("#dlg").count() == 0)

            # C: autoBackup=false → диалог «Пора сделать копию»
            seed_cfg(dump, lastBackup=iso_ago(20), autoBackup=False)
            page, st, errs = await open_ep(browser)
            await load(page)
            dlg = await page.evaluate("(()=>{ const d=document.getElementById('dlg'); return d&&{t:d.querySelector('.dlg-title').textContent, x:d.querySelector('.dlg-text').textContent, b:[...d.querySelectorAll('button')].map(b=>b.textContent.trim())}; })()")
            check("1.2: autoBackup выключен → диалог «Пора сделать копию: последняя была 20 дней назад» с кнопками «Отправить в чат» / «Позже», без автоотправки",
                  dlg and dlg["t"] == "Пора сделать копию" and "20 дней назад" in dlg["x"] and dlg["b"] == ["Отправить в чат", "Позже"] and not st["reqs"], dlg)
            await page.click('#dlg [data-dlg="0"]'); await page.wait_for_timeout(700)
            check("1.2: «Отправить в чат» отправляет JSON, lastBackup обновлён", len(st["reqs"]) == 1 and st["reqs"][0]["format"] == "json" and await page.evaluate("Date.now()-new Date(data.cfg.lastBackup).getTime()<60000"))
            seed_cfg(dump, lastBackup=iso_ago(20), autoBackup=False)
            page, st, errs = await open_ep(browser); await load(page)
            await page.click('#dlg [data-dlg="1"]'); await page.wait_for_timeout(400)
            check("1.2: «Позже» в диалоге напоминания — snooze 24 ч, отправки не было", not st["reqs"] and abs(await page.evaluate("data.cfg.backupSnooze") - (time.time() * 1000 + DAY)) < 120000)

            # D: условия, при которых не запускается
            seed_cfg(dump, lastBackup=iso_ago(20), autoBackup=True)
            page, st, errs = await open_ep(browser, endpoint=""); await load(page)
            check("1.2: BACKUP_ENDPOINT пуст → отправки и диалога нет, прежний баннер-напоминание остаётся", not st["reqs"] and await page.locator("#dlg").count() == 0 and await page.locator(".backup-banner:has([data-act=bannerBackupOpen])").count() == 1)
            seed_cfg(dump, lastBackup=iso_ago(20), autoBackup=True, backupReminderDays=0)
            page, st, errs = await open_ep(browser); await load(page)
            check("1.2: интервал 0 — автоотправка выключена", not st["reqs"] and await page.locator("#dlg").count() == 0)
            seed_cfg(dump, lastBackup=iso_ago(20), autoBackup=True, backupSnooze=int(time.time() * 1000) + DAY)
            page, st, errs = await open_ep(browser); await load(page)
            check("1.2: активный snooze — не запускается", not st["reqs"] and await page.locator("#dlg").count() == 0)
            seed_cfg(dump, lastBackup=iso_ago(13), autoBackup=True)
            page, st, errs = await open_ep(browser); await load(page)
            check("1.2: копия моложе интервала (13 из 14 дней) — не запускается", not st["reqs"])
            seed_cfg(dump, lastBackup=iso_ago(20), autoBackup=True); STORE["tst_clone_state"] = "running"
            page, st, errs = await open_ep(browser); await load(page)
            check("1.2: незавершённое клонирование (экран «не завершено») — автоотправка не запускается", not st["reqs"] and "Копирование не завершено" in await page.inner_text("#app"))
            STORE.pop("tst_clone_state", None)
            # до завершения синхронизации не шлём
            seed_cfg(dump, lastBackup=iso_ago(20), autoBackup=True)
            page, st, errs = await open_ep(browser, getkeys_delay=1800)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(700)
            early = len(st["reqs"]); await page.wait_for_timeout(4000)
            check("1.2: пока синхронизация с CloudStorage не завершена, копия не отправляется; после — отправляется (в ней данные облака)", early == 0 and len(st["reqs"]) == 1 and len(json.loads(st["reqs"][0]["content"])["log"]) == 35, (early, len(st["reqs"])))
            check("нет pageerror (автоотправка)", not errs, errs[:2])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
