"""Задача 5: Cloudflare Worker (логика гоняется в браузере: Web Crypto/fetch/FormData те же, что в workerd) и клиент отправки в чат."""
import asyncio, base64, hashlib, hmac, io, json, os, subprocess, sys, tempfile, time, urllib.parse
sys.path.insert(0, os.path.dirname(__file__))
from test_step0 import STORE, MOCK, cs_handler, log_handler, check, RESULTS, REPO, BASE
from test_task4 import ensure_xlsx_lib, XLSX_JS, HEADER
from playwright.async_api import async_playwright

TOKEN = "123456:TEST-TOKEN"
DUMP = os.path.join(REPO, "..", "current_data.json")

def make_init_data(token=TOKEN, user_id=4242, age=10, extra=None, tamper=None, drop_hash=False):
    auth = int(time.time()) - age
    fields = {"query_id": "AAH-test", "user": json.dumps({"id": user_id, "first_name": "Тест", "username": "t"}, ensure_ascii=False, separators=(",", ":")),
              "auth_date": str(auth), "signature": "sig-value"}
    if extra: fields.update(extra)
    dcs = "\n".join("%s=%s" % (k, fields[k]) for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    if drop_hash: del fields["hash"]
    if tamper: fields = tamper(fields)
    return urllib.parse.urlencode(fields)

WORKER_JS = r"""
window.__calls = [];
window.__tg = { mode: 'ok' };
window.__realFetch = window.fetch;
window.fetch = async (url, init) => {
  if (String(url).startsWith('https://api.telegram.org/')) {
    const fd = init.body, entries = {};
    for (const [k, v] of fd.entries()) entries[k] = v instanceof Blob ? { name: v.name, type: v.type, size: v.size, b64: null, blob: v } : v;
    const doc = entries.document; let bytes = null;
    if (doc) { bytes = Array.from(new Uint8Array(await doc.blob.arrayBuffer())); }
    window.__calls.push({ url: String(url), chat_id: entries.chat_id, caption: entries.caption, doc: doc ? { name: doc.name, type: doc.type, size: doc.size, bytes: bytes.slice(0, 64) } : null, docBytes: bytes ? bytes.length : 0, docHead: bytes ? bytes.slice(0,3) : null });
    if (window.__tg.mode === 'throw') throw new Error('network down');
    if (window.__tg.mode === 'fail') return new Response(JSON.stringify({ ok: false, error_code: 400, description: 'Bad Request: chat not found' }), { status: 400 });
    if (window.__tg.mode === 'html') return new Response('<html>oops</html>', { status: 502 });
    return new Response(JSON.stringify({ ok: true, result: {} }), { status: 200 });
  }
  return window.__realFetch(url, init);
};
window.call = async (method, path, body, env, headers) => {
  const req = new Request('https://gym-tracker-backup.example.workers.dev' + path, { method, body: typeof body === 'string' || body == null ? body : JSON.stringify(body), headers: headers || { 'Content-Type': 'application/json' } });
  const res = await window.W.default.fetch(req, env == null ? { BOT_TOKEN: '%s' } : env);
  const text = await res.text(); let j = null; try { j = JSON.parse(text); } catch (e) {}
  return { status: res.status, json: j, text, cors: res.headers.get('Access-Control-Allow-Origin'), methods: res.headers.get('Access-Control-Allow-Methods'), allowH: res.headers.get('Access-Control-Allow-Headers'), ctype: res.headers.get('Content-Type') };
};
""" % TOKEN

async def worker_tests(browser):
    page = await browser.new_page()
    errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
    await page.goto(BASE + "/worker/README.md")
    await page.evaluate("import('/worker/src/index.js').then(m => { window.W = m; })")
    await page.wait_for_function("!!window.W")
    await page.evaluate(WORKER_JS)
    # env=None в evaluate → undefined → токен по умолчанию; для «нет токена» передаём {}
    body = lambda **kw: dict({"initData": make_init_data(), "env": "test", "format": "json", "filename": "gym-tracker-2026-09-30.json", "content": '{"app":"gym-tracker"}', "encoding": "text"}, **kw)
    async def post(b, env=None): return await page.evaluate("([b,e]) => window.call('POST','/',b,e)", [b, env])
    reset = lambda: page.evaluate("window.__calls.length=0; window.__tg.mode='ok'; 0")

    # ---- CORS / маршруты
    r = await page.evaluate("window.call('OPTIONS','/',null)")
    check("worker: OPTIONS → 204, CORS: https://ktilich.github.io, POST/OPTIONS, Content-Type", r["status"] == 204 and r["cors"] == "https://ktilich.github.io" and r["methods"] == "POST, OPTIONS" and r["allowH"] == "Content-Type", r)
    r = await page.evaluate("window.call('GET','/',null)"); check("worker: GET → 405 (с CORS)", r["status"] == 405 and r["json"]["ok"] is False and r["cors"] == "https://ktilich.github.io", r)
    r = await page.evaluate("window.call('POST','/other','{}')"); check("worker: другой путь → 404", r["status"] == 404, r)
    r = await page.evaluate("window.call('POST','/','{}',{})"); check("worker: нет BOT_TOKEN → 500 server_misconfigured", r["status"] == 500 and r["json"]["error"] == "server_misconfigured", r)

    # ---- успех
    await reset()
    r = await post(body())
    calls = await page.evaluate("window.__calls")
    check("worker: успех → 200 {ok:true}, CORS и JSON в ответе", r["status"] == 200 and r["json"] == {"ok": True} and r["cors"] == "https://ktilich.github.io" and "application/json" in r["ctype"], r)
    c = calls[0]
    today = time.strftime("%Y-%m-%d", time.gmtime())
    check("worker: sendDocument на api.telegram.org/bot<TOKEN>", c["url"] == "https://api.telegram.org/bot%s/sendDocument" % TOKEN, c["url"])
    check("worker: chat_id = user.id из проверенного initData", c["chat_id"] == "4242", c)
    check("worker: caption «Резервная копия Gym Tracker · <дата> · TEST» для env=test", c["caption"] == "Резервная копия Gym Tracker · %s · TEST" % today, c["caption"])
    check("worker: документ — имя файла, MIME application/json, содержимое", c["doc"]["name"] == "gym-tracker-2026-09-30.json" and c["doc"]["type"] == "application/json" and bytes(c["doc"]["bytes"]).decode() == '{"app":"gym-tracker"}', c["doc"])
    await reset(); r = await post(body(env="prod")); c = (await page.evaluate("window.__calls"))[0]
    check("worker: для env=prod подпись без « · TEST»", c["caption"] == "Резервная копия Gym Tracker · %s" % today, c["caption"])
    await reset(); r = await post(body(chat_id=999, user_id=1, initData=make_init_data(user_id=4242))); c = (await page.evaluate("window.__calls"))[0]
    check("worker: chat_id из тела запроса игнорируется", c["chat_id"] == "4242", c)
    raw_xlsx = bytes(range(256)) * 4
    await reset(); r = await post(body(format="xlsx", filename="gym-tracker-2026-09-30.xlsx", content=base64.b64encode(raw_xlsx).decode(), encoding="base64")); c = (await page.evaluate("window.__calls"))[0]
    check("worker: xlsx (base64) → MIME openxml, байты совпали", r["status"] == 200 and c["doc"]["type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" and c["docBytes"] == 1024 and c["doc"]["bytes"] == list(raw_xlsx[:64]), c["doc"])
    await reset(); r = await post(body(format="csv", filename="x.csv", content="﻿Дата;Вес\r\n", encoding="text")); c = (await page.evaluate("window.__calls"))[0]
    check("worker: csv (text, BOM сохранён) → text/csv", c["doc"]["type"] == "text/csv" and c["docHead"] == [0xEF, 0xBB, 0xBF], c)
    await reset(); await post(body(filename="../../etc/passwd")); c = (await page.evaluate("window.__calls"))[0]
    check("worker: имя файла очищено от путей, расширение по формату", "/" not in c["doc"]["name"] and "\\" not in c["doc"]["name"] and c["doc"]["name"].endswith(".json"), c["doc"]["name"])
    await reset(); await post(body(filename="report.xlsx")); c = (await page.evaluate("window.__calls"))[0]
    check("worker: расширение приводится к формату (report.xlsx + json → report.json)", c["doc"]["name"] == "report.json", c["doc"]["name"])

    # ---- 403
    await reset()
    r = await post(body(initData=make_init_data(tamper=lambda f: dict(f, user=json.dumps({"id": 1}))))); check("worker: изменённые данные (подмена user) → 403 bad_signature", r["status"] == 403 and r["json"]["error"] == "bad_signature", r)
    r = await post(body(initData=make_init_data(drop_hash=True))); check("worker: нет hash → 403", r["status"] == 403 and r["json"]["error"] == "bad_signature", r)
    r = await post(body(initData=make_init_data(token="999:OTHER"))); check("worker: подпись чужим токеном → 403", r["status"] == 403, r)
    r = await post(body(initData=make_init_data(age=3700))); check("worker: auth_date старше 3600 с → 403 expired", r["status"] == 403 and r["json"]["error"] == "expired", r)
    r = await post(body(initData=make_init_data(age=3590))); check("worker: auth_date 3590 с назад ещё принимается", r["status"] == 200, r)
    r = await post(body(initData=make_init_data(extra={"start_param": "a b&c=d"}))); check("worker: значения с пробелами/спецсимволами подписываются корректно (декодирование URLSearchParams)", r["status"] == 200, r)
    await reset(); await post(body(initData=make_init_data(age=3700))); check("worker: при 403 запросов к Telegram нет", len(await page.evaluate("window.__calls")) == 0)

    # ---- 400
    bad = {
        "не JSON": "{oops", "массив": "[1,2]", "нет initData": body(initData=""), "env вне списка": body(env="dev"), "format не из белого списка": body(format="exe"),
        "format __proto__": body(format="__proto__"), "encoding вне списка": body(encoding="hex"), "content не строка": body(content=123),
        "битый base64": body(encoding="base64", content="@@@@"), "пустой файл": body(content=""),
    }
    for name, b in bad.items():
        r = await post(b); check("worker: 400 — " + name, r["status"] == 400 and r["json"]["ok"] is False and r["json"]["error"] == "bad_request", r)
    # ---- 413
    five = 5 * 1024 * 1024
    r = await post(body(content="a" * (five + 1))); check("worker: text > 5 МБ → 413", r["status"] == 413 and r["json"]["error"] == "too_large", r["status"])
    r = await post(body(format="xlsx", encoding="base64", content=base64.b64encode(b"\x01" * (five + 1)).decode())); check("worker: base64 > 5 МБ (после декодирования) → 413", r["status"] == 413, r["status"])
    await reset(); r = await post(body(content="a" * five)); check("worker: ровно 5 МБ проходит", r["status"] == 200 and (await page.evaluate("window.__calls[0].docBytes")) == five, r["status"])
    # ---- 502
    await reset(); await page.evaluate("window.__tg.mode='fail'"); r = await post(body())
    check("worker: ошибка Telegram → 502 с description", r["status"] == 502 and r["json"]["error"] == "telegram_error" and "chat not found" in r["json"]["description"], r)
    await page.evaluate("window.__tg.mode='throw'"); r = await post(body()); check("worker: сеть до Telegram недоступна → 502", r["status"] == 502, r)
    await page.evaluate("window.__tg.mode='html'"); r = await post(body()); check("worker: не-JSON ответ Telegram → 502", r["status"] == 502, r)
    check("worker: токен бота не попадает ни в один ответ", TOKEN not in r["text"])
    check("worker: нет pageerror", not errs, errs[:2])
    await page.close()

async def client_tests(browser, dump):
    have_xlsx = ensure_xlsx_lib()
    cache = json.dumps(json.dumps({"cfg": dump["cfg"], "templates": dump["templates"], "log": dump["log"]}))
    async def make(endpoint, tg=True, delay=0.0, mode="ok"):
        ctx = await browser.new_context(viewport={"width": 390, "height": 900})
        if tg:
            await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
        await ctx.add_init_script("if(!localStorage.getItem('tst_gt2:cache'))localStorage.setItem('tst_gt2:cache',%s);" % cache)
        page = await ctx.new_page(); state = {"reqs": [], "mode": mode}
        await page.route("**/telegram.org/**", lambda r: r.abort())
        if have_xlsx: await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.fulfill(path=XLSX_JS, content_type="application/javascript"))
        async def index(route):
            resp = await route.fetch(); txt = await resp.text()
            if endpoint: txt = txt.replace('const BACKUP_ENDPOINT="";', 'const BACKUP_ENDPOINT="%s";' % endpoint)
            await route.fulfill(response=resp, body=txt)
        await page.route("**/test/index.html", index)
        async def worker(route):
            req = route.request
            cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Allow-Methods": "POST, OPTIONS"}
            if req.method == "OPTIONS": return await route.fulfill(status=204, headers=cors)
            state["reqs"].append(json.loads(req.post_data)); await asyncio.sleep(delay)
            if state["mode"] == "abort": return await route.abort()
            if state["mode"] == "expired": return await route.fulfill(status=403, headers=cors, content_type="application/json", body=json.dumps({"ok": False, "error": "expired", "description": "initData устарел"}))
            if state["mode"] == "tgfail": return await route.fulfill(status=502, headers=cors, content_type="application/json", body=json.dumps({"ok": False, "error": "telegram_error", "description": "Bad Request: chat not found"}))
            await route.fulfill(status=200, headers=cors, content_type="application/json", body=json.dumps({"ok": True}))
        await page.route("https://worker.test/**", worker)
        await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(1500)
        await page.click('button[data-tab="set"]'); await page.wait_for_timeout(300)
        return page, state
    send_sel = '[data-act="sendBackup"]'

    page, st = await make("")
    check("клиент: BACKUP_ENDPOINT пуст → кнопки отправки скрыты, приложение работает", await page.locator(send_sel).count() == 0 and await page.evaluate("BACKUP_ENDPOINT===''") and await page.locator('[data-act="backupCopy"]').count() == 1)
    page, st = await make("https://worker.test/", tg=False)
    check("клиент: вне Telegram (нет initData) кнопки отправки скрыты", await page.locator(send_sel).count() == 0)

    page, st = await make("https://worker.test/", delay=0.8)
    check("клиент: endpoint задан, есть initData → три кнопки «JSON / Excel / CSV»", await page.locator(send_sel).count() == 3 and "Отправить в чат" in await page.inner_text("#app"))
    await page.evaluate("data.cfg.lastBackup=null; 0")
    click = asyncio.ensure_future(page.click('[data-act="sendBackup"][data-format="json"]'))
    await asyncio.sleep(0.35)
    txt = await page.evaluate("[...document.querySelectorAll('[data-act=sendBackup]')].map(b=>({t:b.textContent.trim(),d:b.disabled}))")
    check("клиент: во время запроса кнопка в состоянии загрузки («Отправка…»), остальные заблокированы", txt[0]["t"] == "Отправка…" and all(x["d"] for x in txt), txt)
    await click; await page.wait_for_timeout(1200)
    req = st["reqs"][0]
    check("клиент: запрос — initData, env, format, filename, encoding", req["initData"].startswith("user=") and req["env"] == "test" and req["format"] == "json" and req["encoding"] == "text" and req["filename"].startswith("gym-tracker-") and req["filename"].endswith(".json"), {k: (v if k != "content" else "...") for k, v in req.items()})
    j = json.loads(req["content"])
    check("клиент: JSON — полный дамп (app gym-tracker, 35 дней)", j["app"] == "gym-tracker" and len(j["log"]) == 35)
    check("клиент: тост «Отправлено в чат», lastBackup обновлён только после ok (JSON)", "Отправлено в чат" in await page.inner_text("#toastMsg") and await page.evaluate("!!data.cfg.lastBackup"))
    check("клиент: после ответа кнопки снова активны", await page.evaluate("[...document.querySelectorAll('[data-act=sendBackup]')].every(b=>!b.disabled)"))

    await page.evaluate("data.cfg.lastBackup=null; 0")
    await page.click('[data-act="sendBackup"][data-format="csv"]'); await page.wait_for_timeout(1500)
    req = st["reqs"][-1]
    rows = req["content"].split("\r\n")
    check("клиент: CSV — text, с BOM, заголовок ТЗ", req["format"] == "csv" and req["encoding"] == "text" and req["content"].startswith("﻿") and rows[0].lstrip("﻿") == ";".join(HEADER), rows[0])
    check("клиент: отправка CSV не обновляет lastBackup (не полная копия)", await page.evaluate("data.cfg.lastBackup===null") and "Отправлено в чат" in await page.inner_text("#toastMsg"))
    if have_xlsx:
        import openpyxl
        await page.click('[data-act="sendBackup"][data-format="xlsx"]'); await page.wait_for_timeout(2000)
        req = st["reqs"][-1]
        wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(req["content"]))); ws = wb.worksheets[0]
        check("клиент: Excel — base64, файл открывается, заголовок ТЗ, lastBackup не тронут", req["encoding"] == "base64" and req["filename"].endswith(".xlsx") and list(next(ws.iter_rows(values_only=True))) == HEADER and await page.evaluate("data.cfg.lastBackup===null"))

    # ошибки
    page, st = await make("https://worker.test/", mode="tgfail"); await page.evaluate("data.cfg.lastBackup=null; 0")
    await page.click('[data-act="sendBackup"][data-format="json"]'); await page.wait_for_timeout(800)
    check("клиент: ошибка сервера — текст ошибки в тосте, lastBackup не обновлён", "chat not found" in await page.inner_text("#toastMsg") and await page.evaluate("data.cfg.lastBackup===null"))
    st["mode"] = "expired"; await page.click('[data-act="sendBackup"][data-format="json"]'); await page.wait_for_timeout(800)
    check("клиент: 403 expired — «Сессия устарела»", "устарела" in await page.inner_text("#toastMsg"))
    st["mode"] = "abort"; await page.click('[data-act="sendBackup"][data-format="json"]'); await page.wait_for_timeout(800)
    check("клиент: сеть недоступна — сообщение, кнопки снова активны", "Не удалось отправить" in await page.inner_text("#toastMsg") and await page.evaluate("[...document.querySelectorAll('[data-act=sendBackup]')].every(b=>!b.disabled)"))

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8"))
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            await worker_tests(browser)
            await client_tests(browser, dump)
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
