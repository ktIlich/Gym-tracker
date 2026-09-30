import re
import os
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
import asyncio, json, subprocess, sys, time, copy
from playwright.async_api import async_playwright

BASE = "http://localhost:8765"
RESULTS = []
def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond), extra))
    print(("PASS " if cond else "FAIL ") + name + (("  -> " + str(extra)) if (extra and not cond) else ""))

# ---- «облако Telegram» на стороне Python: общее для всех страниц, с журналом записей ----
STORE = {}
WRITES = []   # (op, key)

def seed_prod():
    STORE.clear()
    STORE["cfg"] = json.dumps({"cycle": {"workWeeks": 2, "restWeeks": 1, "anchorDate": "2026-07-13"}, "up": 1000, "accent": "#ff9f0a"})
    for i in range(3):
        STORE["tpl_t%d" % i] = json.dumps({"id": "t%d" % i, "name": "Шаблон %d" % i, "title": "T%d" % i, "up": 1,
                                             "blocks": [{"type": "single", "items": [{"name": "Жим", "plan": "3х8-12"}]}]})
    for d in ["2026-09-21", "2026-09-23", "2026-09-28"]:
        STORE["w_" + d] = json.dumps({"title": "T0", "up": 5, "weekType": "work",
                                       "exercises": [{"id": "e" + d, "name": "Жим (3х8-12)", "base": "Жим", "plan": "3х8-12", "variant": None, "sets": [{"w": 50, "r": 10}]}]})

MOCK = """
(() => {
  const call = (op, a) => window.__cs(op, JSON.stringify(a)).then(r => JSON.parse(r));
  const cs = {
    getKeys: cb => call('getKeys', []).then(v => cb(null, v)),
    getItems: (keys, cb) => call('getItems', [keys]).then(v => cb(null, v)),
    setItem: (k, v, cb) => call('setItem', [k, v]).then(v => cb(null, v)),
    removeItem: (k, cb) => call('removeItem', [k]).then(v => cb(null, v)),
    removeItems: (keys, cb) => call('removeItems', [keys]).then(v => cb(null, v)),
  };
  window.__toasts = [];
  window.Telegram = { WebApp: { ready(){}, expand(){}, isVersionAtLeast: () => true, disableVerticalSwipes(){},
    platform: 'ios', version: '8.0', initData: 'user=%7B%22id%22%3A4242%7D', initDataUnsafe: { user: { id: 4242 } },
    colorScheme: 'dark', CloudStorage: cs, showConfirm(msg, cb){ window.__log('confirm', msg); cb(true); },
    showAlert(msg, cb){ window.__log('alert_cache', localStorage.getItem('tst_gt2:cache') || ''); window.__log('alert', msg); if (cb) cb(); },
    enableClosingConfirmation(){ window.__log('closing', 'on'); }, disableClosingConfirmation(){ window.__log('closing', 'off'); },
    HapticFeedback: { impactOccurred(){}, notificationOccurred(){} } } };
})();
"""

LOG = []   # (kind, msg): showAlert / showConfirm
async def log_handler(source, kind, msg):
    LOG.append((kind, msg))
def logs_of(kind): return [m for k, m in LOG if k == kind]

INFLIGHT = {"cur": 0, "max": 0}
DELAY = {"set": 0.0}
GET_SIZES = []
REMOVE_MANY = []   # списки ключей каждого вызова removeItems

async def cs_handler(source, op, args_json):
    a = json.loads(args_json)
    if op == "getKeys":
        return json.dumps(list(STORE.keys()))
    if op == "getItems":
        GET_SIZES.append(len(a[0]))
        return json.dumps({k: STORE.get(k, "") for k in a[0]})
    if op == "setItem":
        INFLIGHT["cur"] += 1; INFLIGHT["max"] = max(INFLIGHT["max"], INFLIGHT["cur"])
        try:
            if DELAY["set"]: await asyncio.sleep(DELAY["set"])
            WRITES.append(("set", a[0])); STORE[a[0]] = a[1]
        finally:
            INFLIGHT["cur"] -= 1
        return "true"
    if op == "removeItem":
        WRITES.append(("del", a[0])); STORE.pop(a[0], None); return "true"
    if op == "removeItems":
        REMOVE_MANY.append(list(a[0]))
        for k in a[0]:
            WRITES.append(("del", k)); STORE.pop(k, None)
        return "true"

async def open_page(ctx, path, mock=True):
    page = await ctx.new_page()
    logs = []
    page.on("pageerror", lambda e: logs.append("pageerror: %s" % e))
    page.on("console", lambda m: logs.append("console.%s: %s" % (m.type, m.text)) if m.type == "error" else None)
    await page.route("**/telegram.org/**", lambda r: r.abort())
    await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
    await page.goto(BASE + path)
    await page.wait_for_timeout(1200)
    return page, logs

async def main():
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            ctx = await browser.new_context(viewport={"width": 390, "height": 800})
            await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler)
            await ctx.add_init_script(MOCK)

            seed_prod()
            PROD0 = copy.deepcopy(STORE)

            # ---------- v2: боевая версия, ничего не должно измениться ----------
            cache = {"cfg": json.loads(STORE["cfg"]), "templates": [json.loads(v) for k, v in STORE.items() if k.startswith("tpl_")],
                     "log": {k[2:]: json.loads(v) for k, v in STORE.items() if k.startswith("w_")}}
            await ctx.add_init_script("if(location.pathname.includes('/v2/')&&!localStorage.getItem('gt2:cache'))localStorage.setItem('gt2:cache',%s);" % json.dumps(json.dumps(cache)))
            v2, v2logs = await open_page(ctx, "/v2/index.html")
            check("v2: файл не изменён (нет ENV/KP)", await v2.evaluate("typeof ENV==='undefined'") and subprocess.run(["git","diff","--quiet","--","v2"],cwd=REPO).returncode==0)
            check("v2: нет бейджа TEST", await v2.evaluate("!document.querySelector('.env-badge')"))
            check("v2: прод-данные не изменились после открытия", STORE == PROD0, WRITES)
            LS_NONTST = "JSON.stringify(Object.fromEntries(Object.entries(localStorage).filter(([k])=>!k.startsWith('tst_'))))"
            v2_ls_before = await v2.evaluate(LS_NONTST)

            # ---------- test ----------
            WRITES.clear()
            t, tlogs = await open_page(ctx, "/test/index.html")
            check("test: ENV=test, KP=tst_", await t.evaluate("ENV==='test' && KP==='tst_' && K('w_2026-09-28')==='tst_w_2026-09-28'"))
            check("test: бейдж TEST на экране первичной настройки", await t.evaluate("document.getElementById('envBadge')?.textContent==='TEST'"))
            b = await t.evaluate("""(()=>{ const e=document.getElementById('envBadge'), cs=getComputedStyle(e), r=e.getBoundingClientRect();
                const a=document.querySelector('.setup').getBoundingClientRect().top; e.style.display='none'; const a2=document.querySelector('.setup').getBoundingClientRect().top; e.style.display='';
                return {pos:cs.position, top:r.top, right:innerWidth-r.right, shift:a-a2, pe:cs.pointerEvents}; })()""")
            check("бейдж TEST: position:fixed в углу, не сдвигает контент", b["pos"] == "fixed" and 0 <= b["top"] <= 20 and 0 < b["right"] <= 20 and b["shift"] == 0 and b["pe"] == "none", b)
            check("бейдж TEST: top учитывает safe-area (CSS-переменные Telegram)", "--tg-safe-area-inset-top" in open(REPO+"/test/index.html", encoding="utf-8").read())
            check("test: на первом экране (setup) есть кнопка клонирования", await t.locator('[data-act="cloneProd"]').count() == 1)
            check("test: title содержит TEST", "TEST" in await t.title())
            check("test: csKeys не видит прод-ключей", await t.evaluate("csKeys().then(k=>!k.includes('w_2026-09-28') && k.every(x=>!x.startsWith('tst_')))"))
            check("test: при первом старте все записи с префиксом tst_", all(k.startswith("tst_") for _, k in WRITES) and len(WRITES) > 0, WRITES[:5])
            prod_now = {k: v for k, v in STORE.items() if not k.startswith("tst_")}
            check("test: прод-ключи не изменены при первом старте", prod_now == PROD0)
            ls = await t.evaluate("Object.keys(localStorage)")
            check("test: свои ключи localStorage с префиксом tst_", "tst_gt2:cache" in ls, ls)
            check("localStorage: не-tst ключи (v2) не изменились после старта test", await t.evaluate(LS_NONTST) == v2_ls_before)

            # ---------- защита ----------
            WRITES.clear(); snap = copy.deepcopy(STORE)
            r = await t.evaluate("""(async()=>{ const out=[];
                try{ await rawSet('cfg','HACK'); out.push('set-noerr'); }catch(e){ out.push('set:'+e.message); }
                try{ await rawDel('w_2026-09-28'); out.push('del-noerr'); }catch(e){ out.push('del:'+e.message); }
                try{ lsSet.call(null,'x','y'); out.push('ls-ok'); }catch(e){ out.push('ls:'+e.message); }
                try{ guardKey('gt2:cache'); out.push('guard-noerr'); }catch(e){ out.push('guard:'+e.message); }
                out.push(document.getElementById('toastMsg').textContent);
                return out; })()""")
            check("защита: rawSet прод-ключа бросает", r[0].startswith("set:Blocked"), r)
            check("защита: rawDel прод-ключа бросает", r[1].startswith("del:Blocked"), r)
            check("защита: тост о блокировке", "Попытка записи в боевые данные заблокирована" in r[-1], r)
            check("защита: прод-ключ не изменился, запросов к облаку не было", STORE == snap and not WRITES, WRITES)
            await t.evaluate("lsDel('x')")

            # ---------- клонирование ----------
            check("v2: кнопки клонирования нет", await v2.evaluate("!document.querySelector('[data-act=cloneProd]') && typeof cloneFromProd==='undefined'"))
            WRITES.clear()
            LOG.clear(); await t.evaluate("window.__marker=1; 0")
            await t.click('[data-act="cloneProd"]')   # с экрана первичной настройки
            await t.wait_for_timeout(2500)
            check("клон #1 (тестовых данных ещё нет): подтверждение не спрашивается", not logs_of("confirm"), LOG)
            check("клон #1: showAlert с итогом «Скопировано: 3 тренировок, 3 шаблонов, 7 ключей»", logs_of("alert") == ["Скопировано: 3 тренировок, 3 шаблонов, 7 ключей"], LOG)
            check("клон #1: после showAlert выполнена перезагрузка страницы", await t.evaluate("window.__marker===undefined"))
            check("после клона и перезагрузки: мастера нет, бейдж TEST есть", await t.locator('[data-act="setupNext"]').count() == 0 and await t.evaluate("!!document.getElementById('envBadge')"))
            await t.click('button[data-tab="set"]'); await t.wait_for_timeout(300); await t.click('[data-act="testOpen"]'); await t.wait_for_timeout(200)
            check("test: кнопка клонирования в настройках", await t.locator('[data-act="cloneProd"]').count() == 1)
            WRITES.clear(); LOG.clear()
            await t.click('[data-act="cloneProd"]'); await t.wait_for_timeout(2500)
            check("клон #2 (тестовые данные есть): запрошено подтверждение", any("Перезаписать" in m for m in logs_of("confirm")), LOG)
            check("клон: все записи/удаления — только tst_", all(k.startswith("tst_") for _, k in WRITES) and len(WRITES) > 0, [w for w in WRITES if not w[1].startswith("tst_")])
            check("клон: прод-ключи не тронуты", {k: v for k, v in STORE.items() if not k.startswith("tst_")} == PROD0)
            copied = {k[4:]: v for k, v in STORE.items() if k.startswith("tst_") and k != "tst_clone_state"}
            check("клон: tst_* == копия прода (ключи и значения)", copied == PROD0, (set(copied) ^ set(PROD0)))
            check("клон #2: итог в showAlert", logs_of("alert") == ["Скопировано: 3 тренировок, 3 шаблонов, 7 ключей"], LOG)
            check("клон: данные в приложении", await t.evaluate("Object.keys(data.log).length===3 && data.templates.length===3"))
            check("клон: cfg.schema — информационная метка (=2)", await t.evaluate("data.cfg.schema===2"))
            check("клон: тест сохранил preclone в localStorage с префиксом", "tst_preclone" in await t.evaluate("Object.keys(localStorage)"))
            await t.screenshot(path=os.path.join(os.environ.get("TEMP","."),"gt_shot.png"))

            # правка в test не видна в v2
            await t.evaluate("data.log['2026-09-28'].exercises[0].sets.push({w:99,r:9}); data.log['2026-09-28'].up=Date.now(); persistDay('2026-09-28')")
            await t.wait_for_timeout(300)
            check("правка в test: прод-ключ w_2026-09-28 не изменился", STORE["w_2026-09-28"] == PROD0["w_2026-09-28"])
            check("правка в test: tst_w_2026-09-28 изменился", "99" in STORE["tst_w_2026-09-28"])
            v2b, _ = await open_page(ctx, "/v2/index.html")
            check("v2 (новая страница): подходов в 28.09 всё ещё 1", await v2b.evaluate("data.log['2026-09-28'].exercises[0].sets.length===1"))
            check("после работы в test прод-ключи побайтно равны исходным", {k: v for k, v in STORE.items() if not k.startswith("tst_")} == PROD0)
            check("localStorage: не-tst ключи не изменились за весь прогон", await t.evaluate(LS_NONTST) == v2_ls_before)

            # wipe в test не трогает прод
            WRITES.clear()
            await t.evaluate("(async()=>{ const keys=await csKeys(); for(const k of keys) await csDel(k); })()")
            await t.wait_for_timeout(500)
            check("удаление в test (по списку csKeys) не задевает прод", {k: v for k, v in STORE.items() if not k.startswith("tst_")} == PROD0 and not any(k.startswith("tst_") for k in STORE))

            # ---------- миграции (по записям) ----------
            MIG = """window.__mig={id:'log-fields',
                needs(r,kind){ return kind==='day' && (r.exercises||[]).some(e=>!e.base); },
                run(r){ r.exercises.forEach(e=>{ if(!e.base) e.base=String(e.name).replace(/ \\(.*$/,''); }); r.up=(r.up||0)+12345; return r; }};
                MIGRATIONS.push(window.__mig); 0"""
            await t.evaluate(MIG)
            OLD_DAY = {"title": "T0", "up": 777, "weekType": "work", "exercises": [{"id": "old1", "name": "Жим (3х8-12)", "sets": [{"w": 40, "r": 8}]}]}
            # приёмка: старый день в облаке при cfg.schema=2 и новом cfg.up -> после слияния мигрирован и дописан в облако
            cfgc = json.loads(STORE.get("tst_cfg", "{}") or "{}") if "tst_cfg" in STORE else {}
            cfgc.setdefault("cycle", {"workWeeks": 2, "restWeeks": 1, "anchorDate": "2026-07-13"})
            cfgc["schema"] = 2; cfgc["up"] = 9999999999999
            STORE["tst_cfg"] = json.dumps(cfgc)
            STORE["tst_w_2026-08-01"] = json.dumps(OLD_DAY)
            await t.evaluate("cloudLoad()"); await t.wait_for_timeout(1500)
            check("миграции: cfg.schema=2 не мешает — день из облака мигрирован в памяти", await t.evaluate("data.cfg.schema>=2 && data.log['2026-08-01'].exercises[0].base==='Жим'"))
            cloud_day = json.loads(STORE["tst_w_2026-08-01"])
            check("миграции: мигрированный день дописан в облако (base есть)", cloud_day["exercises"][0].get("base") == "Жим", cloud_day)
            check("миграции: up дня не изменился (777)", cloud_day["up"] == 777 and await t.evaluate("data.log['2026-08-01'].up===777"), cloud_day.get("up"))
            check("миграции: снапшот premig_<дата-время> сохранён в localStorage с префиксом", any(k.startswith("tst_premig_2") for k in await t.evaluate("Object.keys(localStorage)")))
            check("миграции: грязный список очищен после записи в облако", await t.evaluate("getDirty().days.length===0"))
            # идемпотентность
            r = await t.evaluate("""(()=>{ const a=JSON.stringify(data); const r1=migrateAll(data); const b=JSON.stringify(data); const r2=migrateAll(data);
                return {same:a===b&&b===JSON.stringify(data), n1:r1.days.length+r1.tpls.length, n2:r2.days.length, snap:r2.snapshot}; })()""")
            check("миграции: повторный migrateAll ничего не меняет (JSON равен), снапшот не создаётся", r["same"] and r["n1"] == 0 and r["snap"] is None, r)
            # решение не зависит от schema
            r = await t.evaluate("""(()=>{ const d={cfg:{schema:99,up:1},templates:[],log:{'2026-01-01':{up:5,exercises:[{name:'A (3х5)'}]}}};
                const res=migrateAll(d); return {days:res.days, base:d.log['2026-01-01'].exercises[0].base, up:d.log['2026-01-01'].up}; })()""")
            check("миграции: schema=99 не отключает миграцию, up=5 сохранён", r["days"] == ["2026-01-01"] and r["base"] == "A" and r["up"] == 5, r)
            # день без up
            r = await t.evaluate("""(()=>{ const d={cfg:{},templates:[],log:{'2026-01-02':{exercises:[{name:'B'}]}}}; migrateAll(d); return 'up' in d.log['2026-01-02']; })()""")
            check("миграции: у записи без up он не появляется", r is False, r)
            # хранить три последних снапшота
            await t.evaluate("""(async()=>{ for(let i=0;i<5;i++){ const d={cfg:{},templates:[],log:{['2026-02-0'+(i+1)]:{exercises:[{name:'C'+i}]}}}; migrateAll(d); await new Promise(r=>setTimeout(r,5)); } })()""")
            snaps = await t.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('tst_premig_'))")
            check("миграции: хранятся только 3 последних снапшота", len(snaps) == 3, snaps)
            check("миграции: снапшоты только с префиксом tst_ (нет premig_ без префикса)", not await t.evaluate("Object.keys(localStorage).some(k=>k.startsWith('premig_'))"))
            # сбой одной записи не ломает остальные
            r = await t.evaluate("""(()=>{ MIGRATIONS.push({id:'bad',needs:(r,k)=>k==='day'&&r.boom,run(){ throw new Error('x'); }});
                const d={cfg:{},templates:[],log:{'2026-03-01':{boom:true,exercises:[]},'2026-03-02':{exercises:[{name:'Z'}]}}};
                const res=migrateAll(d); MIGRATIONS.pop();
                return {err:res.errors, okOther:d.log['2026-03-02'].exercises[0].base==='Z', bad:d.log['2026-03-01'].boom===true}; })()""")
            check("миграции: сбой одной записи → она не тронута, остальные мигрированы", r["err"] == 1 and r["okOther"] and r["bad"], r)
            # грязные записи переживают отказ облака
            r = await t.evaluate("""(async()=>{ const orig=window.Telegram.WebApp.CloudStorage.setItem; cs.setItem=(k,v,cb)=>cb(new Error('offline'),false);
                data.log['2026-04-01']={up:3,exercises:[{name:'Q'}]}; applyMigrations(); await new Promise(r=>setTimeout(r,300));
                const dirtyOffline=getDirty().days.slice(); cs.setItem=orig; await flushDirty();
                return {dirtyOffline, dirtyAfter:getDirty().days}; })()""")
            check("миграции: при недоступном облаке запись остаётся «грязной», потом дописывается", r["dirtyOffline"] == ["2026-04-01"] and r["dirtyAfter"] == [], r)
            check("миграции: после повторной отправки запись в облаке мигрирована", json.loads(STORE["tst_w_2026-04-01"])["exercises"][0].get("base") == "Q")
            # другие точки входа: восстановление из JSON
            r = await t.evaluate("""(()=>{ const dump={app:'gym-tracker',cfg:{cycle:{anchorDate:'2026-07-13'}},templates:[],log:{'2026-05-01':{up:8,exercises:[{name:'M (2х8)'}]}}};
                applyBackupDump(dump,'merge'); const a=data.log['2026-05-01'].exercises[0].base;
                applyBackupDump(dump,'replace'); const b=data.log['2026-05-01'].exercises[0].base; return [a,b,data.log['2026-05-01'].up]; })()""")
            check("миграции: восстановление из JSON (merge и replace) мигрирует записи, up сохранён", r == ["M", "M", 8], r)
            await t.evaluate("MIGRATIONS.length=0")
            check("миграции: без миграций migrateAll — no-op и без снапшота", await t.evaluate("(()=>{const r=migrateAll({cfg:{},templates:[],log:{a:{exercises:[{name:'x'}]}}}); return r.snapshot===null&&!r.days.length;})()"))
            check("миграции: cfg.schema отсутствует → 1, APP_SCHEMA=2", await t.evaluate("APP_SCHEMA===2 && normalizeData({cfg:{}}).cfg.schema===1"))

            # ---------- диагностика и видимый результат клонирования ----------
            ctx2 = await browser.new_context(viewport={"width": 390, "height": 800})
            await ctx2.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
            await ctx2.expose_binding("__cs", cs_handler); await ctx2.expose_binding("__log", log_handler)
            await ctx2.add_init_script(MOCK)
            STORE.clear(); STORE.update(copy.deepcopy(PROD0))
            f, flogs = await open_page(ctx2, "/test/index.html")
            geo = await f.evaluate("""(()=>{ const c=document.querySelector('[data-act=cloneProd]').closest('.card').getBoundingClientRect();
                const w=[...document.querySelectorAll('.setup .card')].find(x=>x.querySelector('[data-act=setupNext]')).getBoundingClientRect();
                return {cw:c.width, ctop:c.top, wtop:w.top, ww:w.width, vw:innerWidth}; })()""")
            check("setup: карточка клонирования выше мастера и не уже его (не сосед в ряду)", geo["ctop"] < geo["wtop"] and geo["cw"] >= geo["ww"] and geo["cw"] > 340, geo)
            check("setup: кнопка «Диагностика» доступна из мастера", await f.locator('[data-act="diagOpen"]').count() == 1)
            await f.click('[data-act="diagOpen"]'); await f.wait_for_timeout(600)
            rep_text = await f.evaluate("document.querySelector('.diag-pre').textContent")
            for needle in ["ENV: test", 'KP: "tst_"', "location.href: http://localhost:8765/test/", "platform: ios", "version: 8.0",
                           "isVersionAtLeast('6.9'): true", "initData: есть", "user.id: 4242", "Telegram.WebApp.CloudStorage: есть",
                           "без префикса tst_: 7", "первые 10 ключей:", "последняя ошибка клонирования: нет"]:
                check("диагностика: отчёт содержит «%s»" % needle, needle in rep_text, rep_text)
            await f.click('[data-act="diagCopy"]'); await f.wait_for_timeout(400)
            clip = await f.evaluate("navigator.clipboard.readText()")
            check("диагностика: «Скопировать отчёт» кладёт весь текст в буфер", clip.replace(chr(13)+chr(10), chr(10)) == rep_text and "ENV: test" in clip, repr(clip)+" ||| "+repr(rep_text))
            await f.click('[data-act="diagClose"]'); await f.wait_for_timeout(200)
            check("диагностика: «Назад» возвращает в мастер", await f.locator('[data-act="setupNext"]').count() == 1)
            # ошибка чтения ключей: текст ошибки виден, попадает в диагностику
            await f.evaluate("window.__origGetKeys=Telegram.WebApp.CloudStorage.getKeys; Telegram.WebApp.CloudStorage.getKeys=cb=>cb('BOOM_KEYS'); 0")
            LOG.clear()
            await f.click('[data-act="cloneProd"]'); await f.wait_for_timeout(500)
            msg = await f.evaluate("document.querySelector('.res-err')?.textContent||''")
            check("клон: при ошибке getKeys виден её текст в карточке", "BOOM_KEYS" in msg, msg)
            check("клон: ошибка через showAlert с названием шага", any("Шаг «Чтение списка ключей»" in m and "BOOM_KEYS" in m for m in logs_of("alert")), LOG)
            check("клон: после ошибки перезагрузки нет", await f.evaluate("document.querySelector('.res-err')!==null"))
            await f.click('[data-act="diagOpen"]'); await f.wait_for_timeout(600)
            rep_text = await f.evaluate("document.querySelector('.diag-pre').textContent")
            check("диагностика: getKeys ошибка и последняя ошибка клонирования в отчёте", "getKeys: ОШИБКА — BOOM_KEYS" in rep_text and "BOOM_KEYS" in rep_text.split("последняя ошибка клонирования:")[1], rep_text)
            await f.click('[data-act="diagClose"]'); await f.evaluate("Telegram.WebApp.CloudStorage.getKeys=window.__origGetKeys; 0")
            # нет прод-данных
            saved = {k: v for k, v in STORE.items() if not k.startswith("tst_")}
            for k in list(saved): STORE.pop(k)
            LOG.clear()
            await f.click('[data-act="cloneProd"]'); await f.wait_for_timeout(500)
            msg = await f.evaluate("document.querySelector('.res-err')?.textContent||''")
            check("клон: нет прод-данных → явное сообщение и showAlert с шагом", "основные данные не найдены" in msg and any("Шаг «Проверка основных данных»" in m for m in logs_of("alert")), (msg, LOG))
            STORE.update(saved)
            # успех виден на экране
            LOG.clear(); await f.evaluate("window.__marker=1; 0")
            await f.click('[data-act="cloneProd"]'); await f.wait_for_timeout(2500)
            check("клон: итог в showAlert и перезагрузка", logs_of("alert") == ["Скопировано: 3 тренировок, 3 шаблонов, 7 ключей"] and await f.evaluate("window.__marker===undefined"), LOG)
            # отмена подтверждения тоже сообщает результат
            await f.evaluate("Telegram.WebApp.showConfirm=(m,cb)=>cb(false); 0")
            await f.click('button[data-tab="set"]'); await f.wait_for_timeout(300); await f.click('[data-act="testOpen"]'); await f.wait_for_timeout(200)
            check("настройки: есть «Диагностика»", await f.locator('[data-act="diagOpen"]').count() == 1)
            await f.click('[data-act="cloneProd"]'); await f.wait_for_timeout(800)
            check("клон: отмена → сообщение «Отменено»", await f.evaluate("document.body.innerText.includes('Отменено: тестовые данные не изменены')"))
            check("клон: прод-ключи по-прежнему не тронуты", {k: v for k, v in STORE.items() if not k.startswith("tst_")} == PROD0)
            # сбой записи копии → шаг «Запись копии»
            LOG.clear()
            await f.evaluate("window.__origSet=Telegram.WebApp.CloudStorage.setItem; Telegram.WebApp.CloudStorage.setItem=(k,v,cb)=>cb(null,false); 0")
            await f.evaluate("Telegram.WebApp.showConfirm=(m,cb)=>cb(true); 0")
            await f.click('[data-act="cloneProd"]'); await f.wait_for_timeout(1200)
            check("клон: сбой записи маркера → showAlert «Шаг «Запись маркера «running»»»", any("Шаг «Запись маркера «running»»" in m for m in logs_of("alert")), LOG)
            check("клон: маркер не записан → экрана «не завершено» нет", await f.locator('[data-act="setupNext"], header').count() >= 1 and "Копирование не завершено" not in await f.evaluate("document.body.innerText"))
            # сбой записи данных при записанном маркере → «Копирование не завершено»
            await f.evaluate("""Telegram.WebApp.CloudStorage.setItem=(k,v,cb)=>{ if(k.includes('_w_')||k.includes('tst_w_')) cb(null,false); else window.__origSet.call(Telegram.WebApp.CloudStorage,k,v,cb); }; 0""")
            LOG.clear()
            await f.evaluate("window.__marker=1; 0")
            await f.click('[data-act="cloneProd"]'); await f.wait_for_timeout(1500)
            check("клон: сбой записи данных → showAlert «Шаг «Запись копии»»", any("Шаг «Запись копии»" in m for m in logs_of("alert")), LOG)
            check("клон: closing confirmation включён и выключен после сбоя", logs_of("closing")[:2] == ["on", "off"], LOG)
            check("клон: при сбое экран «Копирование не завершено» и кнопка «Повторить»", "Копирование не завершено" in await f.evaluate("document.body.innerText") and await f.locator('[data-act="cloneProd"]').inner_text() != "")
            check("клон: маркер tst_clone_state = running", STORE.get("tst_clone_state") == "running", STORE.get("tst_clone_state"))
            await f.reload(); await f.wait_for_timeout(1500)
            check("старт с маркером running: экран «Копирование не завершено», в приложение не пускает",
                  "Копирование не завершено" in await f.evaluate("document.body.innerText") and await f.locator('[data-tab]').first.is_hidden())
            LOG.clear(); WRITES.clear(); await f.evaluate("window.__marker=1; 0")
            await f.click('[data-act="cloneProd"]'); await f.wait_for_timeout(3000)   # «Повторить»: без подтверждения перезаписи
            check("«Повторить»: подтверждение перезаписи не спрашивается, итог в showAlert", not logs_of("confirm") and logs_of("alert") == ["Скопировано: 3 тренировок, 3 шаблонов, 7 ключей"], LOG)
            check("«Повторить»: после reload приложение открыто (нет экрана «не завершено»)", await f.evaluate("window.__marker===undefined") and "Копирование не завершено" not in await f.evaluate("document.body.innerText"))
            check("«Повторить»: маркер done;<дата>;7", STORE.get("tst_clone_state", "").startswith("done;") and STORE["tst_clone_state"].endswith(";7"), STORE.get("tst_clone_state"))
            sets = [w[1] for w in WRITES if w[0] == "set"]
            check("клон: порядок — первая запись маркер running, последняя — маркер done", sets[0] == "tst_clone_state" and sets[-1] == "tst_clone_state" and sets.count("tst_clone_state") == 2, sets[:3] + sets[-3:])
            check("клон: closing confirmation on → off при успехе", logs_of("closing")[:2] == ["on", "off"], LOG)
            cache = logs_of("alert_cache")[-1] if logs_of("alert_cache") else ""
            check("клон: к моменту showAlert кэш localStorage заполнен (3 дня, 3 шаблона)", cache and len(json.loads(cache)["log"]) == 3 and len(json.loads(cache)["templates"]) == 3, cache[:80])
            check("клон: время этапов в диагностике", (await f.evaluate("collectDiag().then(()=>diagReportText())")).count("время клонирования: чтение") == 1)
            check("диагностика/клон: нет pageerror", not [l for l in flogs if l.startswith("pageerror")], flogs[:3])
            await f.screenshot(path=os.path.join(os.environ.get("TEMP", "."), "gt_diag.png"))

            # ---------- мастер: текст цикла из cfg, мастер не показывается при наличии tst-данных ----------
            r = await f.evaluate("""(()=>{ const c=data.cfg.cycle, o=[c.workWeeks,c.restWeeks]; const res=[];
                for(const [w,r] of [[2,1],[1,1],[3,1],[5,2],[11,21]]){ c.workWeeks=w; c.restWeeks=r; res.push(cycleText()); }
                c.workWeeks=o[0]; c.restWeeks=o[1]; return res; })()""")
            check("мастер: текст цикла собирается из cfg.cycle (склонения)", r == ["Цикл по умолчанию: 2 рабочие недели, потом 1 неделя отдыха", "Цикл по умолчанию: 1 рабочая неделя, потом 1 неделя отдыха",
                  "Цикл по умолчанию: 3 рабочие недели, потом 1 неделя отдыха", "Цикл по умолчанию: 5 рабочих недель, потом 2 недели отдыха", "Цикл по умолчанию: 11 рабочих недель, потом 21 неделя отдыха"], r)
            check("мастер: «2+1» не зашито в разметке", "Цикл по умолчанию: 2 рабочие" not in open(REPO+"/test/index.html", encoding="utf-8").read())
            ctx3 = await browser.new_context(viewport={"width": 390, "height": 800})
            await ctx3.expose_binding("__cs", cs_handler); await ctx3.expose_binding("__log", log_handler); await ctx3.add_init_script(MOCK)
            g, glogs = await open_page(ctx3, "/test/index.html")
            check("мастер не показывается, если tst_-данные уже есть в облаке (чистый localStorage)", await g.locator('[data-act="setupNext"]').count() == 0 and await g.evaluate("Object.keys(data.log).length===3"))
            await ctx3.close()

            # ---------- очистка тестовых данных ----------
            await f.evaluate("Telegram.WebApp.showConfirm=(m,cb)=>{ window.__log('confirm', m); cb(false); }; 0")
            await f.click('button[data-tab="set"]'); await f.wait_for_timeout(300); await f.click('[data-act="testOpen"]'); await f.wait_for_timeout(200)
            check("настройки: кнопка «Очистить тестовые данные»", await f.locator('[data-act="clearTest"]').count() == 1)
            before = {k: v for k, v in STORE.items()}
            LOG.clear(); await f.click('[data-act="clearTest"]'); await f.wait_for_timeout(500)
            check("очистка: при отказе в подтверждении ничего не удалено", STORE == before and not logs_of("alert") and any("Удалить все тестовые данные" in m for m in logs_of("confirm")), LOG)
            await f.evaluate("Telegram.WebApp.showConfirm=(m,cb)=>{ window.__log('confirm', m); cb(true); }; window.__marker=1; 0")
            n_cloud = len([k for k in STORE if k.startswith("tst_")])
            n_ls = await f.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('tst_')).length")
            await f.evaluate("lsSet('premig_2026-01-01T00-00-00-000Z','{}'); 0"); n_ls += 1
            nontst_ls = await f.evaluate(LS_NONTST)
            WRITES.clear(); LOG.clear()
            await f.click('[data-act="clearTest"]'); await f.wait_for_timeout(600)
            check("очистка: showAlert «Удалено N ключей» (облако + localStorage)", logs_of("alert") == ["Удалено %d ключей" % (n_cloud + n_ls)], (LOG, n_cloud, n_ls))
            check("очистка: все операции только над tst_-ключами, удалены ровно они", all(k.startswith("tst_") for op, k in WRITES) and len([1 for op, k in WRITES if op == "del"]) == n_cloud, WRITES[:5])
            await f.wait_for_timeout(2000)
            check("очистка: выполнена перезагрузка", await f.evaluate("window.__marker===undefined"))
            check("очистка: прод-ключи облака не тронуты", {k: v for k, v in STORE.items() if not k.startswith("tst_")} == PROD0)
            check("очистка: ключи localStorage без tst_ не тронуты", await f.evaluate(LS_NONTST) == nontst_ls)
            check("очистка: снапшоты premig_/preclone удалены", not await f.evaluate("Object.keys(localStorage).some(k=>k.startsWith('tst_premig_')||k==='tst_preclone')"))
            check("очистка: test открылся в пустом состоянии (мастер, нет дней)", await f.locator('[data-act="setupNext"]').count() == 1 and await f.evaluate("Object.keys(data.log).length===0"))
            # ошибка удаления → showAlert с шагом, без reload
            await f.evaluate("Telegram.WebApp.CloudStorage.removeItem=(k,cb)=>cb('DEL_FAIL',false); window.__marker=1; 0")
            LOG.clear(); await f.click('[data-act="clearTest"]'); await f.wait_for_timeout(800)
            check("очистка: сбой удаления → showAlert «Шаг «Удаление ключей облака»», без перезагрузки", any("Шаг «Удаление ключей облака»" in m for m in logs_of("alert")) and await f.evaluate("window.__marker===1"), LOG)

            # ---------- оптимизация: пачки, removeItems только для лишних, пул по 6, прогресс и оверлей ----------
            STORE.clear(); STORE.update(copy.deepcopy(PROD0))
            for i in range(120): STORE["w_2030-01-%03d" % i] = json.dumps({"title": "x", "up": 1, "exercises": []})
            PROD_BIG = {k: v for k, v in STORE.items()}
            STORE["tst_junk_extra"] = "1"; STORE["tst_w_2030-01-000"] = "stale"   # лишний и устаревший (есть в новой копии)
            DELAY["set"] = 0.04
            cons = []
            f.on("console", lambda m: cons.append(m.text))
            LOG.clear()
            await f.evaluate("Telegram.WebApp.showConfirm=(m,cb)=>{ window.__log('confirm', m); cb(true); }; window.__marker=1; 0")
            GET_SIZES.clear(); WRITES.clear(); REMOVE_MANY.clear(); INFLIGHT["max"] = 0
            click = asyncio.ensure_future(f.click('[data-act="cloneProd"]'))
            seen = None
            for _ in range(80):
                await asyncio.sleep(0.05)
                try:
                    seen = await f.evaluate("""(()=>{ const o=document.getElementById('cloneOverlay'); if(!o) return null; const b=document.querySelector('[data-act=cloneProd]');
                        const top=document.elementFromPoint(innerWidth/2, innerHeight/2);
                        return {text:document.getElementById('cloneOverlayText').textContent, btn:b?b.textContent.trim():null, blocks: top===o||o.contains(top)}; })()""")
                except Exception:
                    seen = None
                if seen and re.match(r"Копирование [1-9]\d*/127$", seen["text"]): break
            await click
            check("прогресс: оверлей «Копирование N/127» блокирует интерфейс", bool(seen) and re.match(r"Копирование \d+/127$", seen["text"]) is not None and seen["blocks"], seen)
            check("прогресс: на кнопке «Копирование N/127»", bool(seen) and seen["btn"] is not None and re.match(r"Копирование \d+/127$", seen["btn"]) is not None, seen)
            await f.wait_for_timeout(3500)
            check("чтение: getItems пачками ≤50 ключей (127 ключей → 3 пачки)", GET_SIZES[:3] == [50, 50, 27], GET_SIZES)
            check("удаление: один вызов removeItems, только лишний tst_-ключ; устаревший w_ не удаляется заранее", REMOVE_MANY == [["tst_junk_extra"]], REMOVE_MANY)
            check("удаление: поштучных removeItem во время клонирования нет", not [w for w in WRITES if w[0] == "del" and w[1] != "tst_junk_extra"], WRITES[:3])
            check("запись: параллельно (>1), но не более 6 одновременных запросов", 1 < INFLIGHT["max"] <= 6, INFLIGHT)
            check("запись: tst_* == копия прода после клона (127 ключей)", {k[4:]: v for k, v in STORE.items() if k.startswith("tst_") and k != "tst_clone_state"} == PROD_BIG)
            check("время этапов выведено в console", any(c.startswith("[clone] чтение") and "удаление" in c and "запись" in c for c in cons), cons[-3:])
            rep_text = await f.evaluate("collectDiag().then(()=>diagReportText())")
            check("время этапов выведено на экране диагностики", "время клонирования: чтение" in rep_text and "запись" in rep_text and "tst_clone_state: done;" in rep_text, rep_text[-400:])
            DELAY["set"] = 0.0
            for k in list(STORE):
                if k.startswith("w_2030") or k.startswith("tst_w_2030"): STORE.pop(k)
            STORE.update(copy.deepcopy(PROD0))

            # ---------- статический контроль ----------
            src = open(REPO+"/test/index.html", encoding="utf-8").read()
            check("статика: нет localStorage.clear; removeItems — один вызов, только в rawDelMany с guardKey по каждому ключу", "localStorage.clear" not in src and src.count("cs.removeItems(") == 1 and "keys.forEach(guardKey)" in src)
            raw_ls = [m.start() for m in re.finditer(r"localStorage\.", src)]
            check("статика: прямой localStorage только внутри lsGet/lsSet/lsDel/lsKeys", len(raw_ls) == 5, len(raw_ls))
            check("статика: прямых cs.* нет вне raw-слоя", len(re.findall(r"\bcs\.(setItem|removeItem|getKeys|getItems)", src)) == 5)
            check("статика: APP_VERSION 2.11.0", 'APP_VERSION="2.11.0"' in src)

            # холодный старт в test без Telegram/облака не падает
            plain = await browser.new_context(viewport={"width": 390, "height": 800})
            pg = await plain.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            await pg.route("**/telegram.org/**", lambda r: r.abort()); await pg.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
            await pg.goto(BASE + "/test/index.html"); await pg.wait_for_timeout(800)
            check("test в обычном браузере: без ошибок, бейдж виден", not errs and await pg.evaluate("!!document.querySelector('.env-badge')"), errs)
            await pg.screenshot(path=os.path.join(os.environ.get("TEMP","."),"gt_shot.png"))

            for name, logs in (("v2", v2logs), ("test", tlogs)):
                check("консоль %s: нет pageerror" % name, not [l for l in logs if l.startswith("pageerror")], logs[:3])
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
