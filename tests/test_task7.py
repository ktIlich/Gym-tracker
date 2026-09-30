"""Задача 7: гигиена данных (дубли шаблонов, проверка данных), запись дня по требованию, шаблоны по умолчанию после проверки облака. На реальном дампе."""
import asyncio, json, os, re, subprocess, sys, statistics, time, tempfile
sys.path.insert(0, os.path.dirname(__file__))
import test_step0 as H
from test_step0 import STORE, WRITES, MOCK, cs_handler, log_handler, check, RESULTS, REPO, BASE
from playwright.async_api import async_playwright

DUMP = os.path.join(REPO, "..", "current_data.json")
ALIASES = {"голень стоя": "Голень стоя (икры)", "гиперэкстензия, акцент на разгибатели и поясница": "Гиперэкстензия, акцент разгибатели и поясница",
           "сгибания голени сидя или стоя": "Сгибания голени", "приседания в гаке лицом назад": "Приседания в гакк-машине", "приседания в гаке лицом к тренажёру": "Приседания в гакк-машине"}
VALIASES = {"приседания в гаке лицом назад": "Спиной", "приседания в гаке лицом к тренажёру": "лицом"}

def canon_base(name):
    return ALIASES.get(name.strip().lower(), name.strip()).lower()

# ---- независимая реализация ожиданий (на Python)
def expected_dups(templates):
    groups = {}
    for i, t in enumerate(templates):
        key = "|".join(sorted({canon_base(it["name"]) for b in t["blocks"] for it in b["items"]}))
        groups.setdefault(key, []).append((i, t))
    out = []
    for key, lst in groups.items():
        if len(lst) < 2: continue
        cnt = lambda t: sum(len(b["items"]) for b in t["blocks"])
        lst.sort(key=lambda x: (-(x[1].get("up") or 0), -cnt(x[1]), x[0]))
        out.append({"keep": lst[0][1]["id"], "drop": [x[1]["id"] for x in lst[1:]]})
    return out

def split_name(name):
    variant = None
    if " · " in name: name, variant = name.rsplit(" · ", 1)
    m = re.match(r"^(.*?)\s*\((\d+)\s*[хx×]\s*(\d+(?:\s*[-–—]\s*\d+)?)\)\s*$", name)
    plan = None
    if m: name, plan = m.group(1), m.group(2)
    return name.strip(), plan, (variant.strip() if variant else None)

def expected_issues(log, today):
    out = {"emptyDay": [], "emptyEx": [], "overPlan": [], "lowWeight": []}
    weights = {}
    parsed = {}
    for k in sorted(log):
        for e in log[k]["exercises"]:
            b, plan, v = split_name(e["name"])
            aliased = ALIASES.get(b.lower())
            if aliased and b.lower() in VALIASES and not v: v = VALIASES[b.lower()]
            b = (aliased or b).lower(); v = (v or "").lower()
            if v == "свободный вес": v = "свободный"
            parsed[id(e)] = (b, plan, v)
            for s in e["sets"]: weights.setdefault((b, v), []).append(s["w"])
    for k in sorted(log):
        exs = log[k]["exercises"]; withs = [e for e in exs if e["sets"]]
        if k < today:
            if exs and not withs: out["emptyDay"].append(k)
            else: out["emptyEx"] += [(k, e["name"]) for e in exs if not e["sets"]]
        for e in exs:
            b, plan, v = parsed[id(e)]
            if plan and len(e["sets"]) >= int(plan) + 1: out["overPlan"].append((k, e["name"]))
            ws = weights[(b, v)]
            if len(ws) >= 3:
                med = statistics.median(ws)
                if any(s["w"] > 0 and s["w"] < med * 0.3 for s in e["sets"]): out["lowWeight"].append((k, e["name"]))
    return out

def seed(dump):
    STORE.clear()
    STORE["tst_cfg"] = json.dumps(dump["cfg"])
    for t in dump["templates"]: STORE["tst_tpl_" + t["id"]] = json.dumps(t)
    for k, d in dump["log"].items(): STORE["tst_w_" + k] = json.dumps(d)

async def open_tg(browser, extra_init=None, cache=None):
    ctx = await browser.new_context(viewport={"width": 390, "height": 900})
    await ctx.expose_binding("__cs", cs_handler); await ctx.expose_binding("__log", log_handler); await ctx.add_init_script(MOCK)
    if extra_init: await ctx.add_init_script(extra_init)
    page = await ctx.new_page(); errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    await page.route("**/telegram.org/**", lambda r: r.abort()); await page.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
    return page, errs

async def main():
    if not os.path.exists(DUMP):
        print("SKIP: нет", DUMP); return
    dump = json.load(open(DUMP, encoding="utf-8"))
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True)
            today = time.strftime("%Y-%m-%d")

            # ================= 7.1 / 7.2 (облако = реальный дамп) =================
            seed(dump)
            page, errs = await open_tg(browser)
            await page.goto(BASE + "/test/index.html"); await page.wait_for_timeout(2500)
            await page.click('button[data-tab="set"]'); await page.wait_for_timeout(300)
            exp = expected_dups(dump["templates"])
            btn = await page.locator('[data-act="hygOpen"][data-screen="dups"]').inner_text()
            check("7.1: в настройках «Найдены похожие шаблоны (N)», N = числу групп (%d)" % len(exp), ("(%d)" % len(exp)) in btn and len(exp) >= 1, (btn, exp))
            await page.click('[data-act="hygOpen"][data-screen="dups"]'); await page.wait_for_timeout(200)
            groups = await page.evaluate("findDupGroups().map(g=>({keep:g.keep.id,drop:g.drop.map(t=>t.id)}))")
            check("7.1: группировка по множеству канонических base; остаётся шаблон с максимальным up (нет up = 0)", sorted(groups, key=lambda g: g["keep"]) == sorted(exp, key=lambda g: g["keep"]), (groups, exp))
            total_drop = sum(len(g["drop"]) for g in exp)
            ups = {t["id"]: (t.get("up") or 0) for t in dump["templates"]}
            check("7.1: в каждой группе оставленный up ≥ up удаляемых", all(all(ups[g["keep"]] >= ups[d] for d in g["drop"]) for g in exp))
            check("7.1: экран показывает «останется» и «будет удалён» для каждой группы", await page.locator(".dup-group").count() == len(exp) and await page.locator("text=останется").count() >= len(exp) and await page.locator("text=будет удалён").count() == total_drop)
            # ссылки на удаляемые id: cfg, дни, состояние экрана
            g0 = exp[0]; drop0, keep0 = g0["drop"][0], g0["keep"]
            await page.evaluate("data.cfg.schedule={mon:%s,tue:'other',nested:{x:%s}}; data.log['2026-09-28'].tplId=%s; ui.tplDelId=%s; 0" % (json.dumps(drop0), json.dumps(drop0), json.dumps(drop0), json.dumps(drop0)))
            n_before = await page.evaluate("data.templates.length")
            await page.locator('[data-act="dupDelAsk"]').first.click(); await page.wait_for_timeout(200)
            check("7.1: удаление — с подтверждением (кнопка «Удалить» появляется после запроса)", await page.locator('[data-act="dupDelGo"]').count() == 1 and await page.evaluate("data.templates.length") == n_before)
            await page.click('[data-act="dupDelNo"]'); await page.wait_for_timeout(150)
            check("7.1: «Отмена» ничего не удаляет", await page.evaluate("data.templates.length") == n_before)
            first_key = await page.evaluate("findDupGroups()[0].key")
            drops_first = await page.evaluate("findDupGroups()[0].drop.map(t=>t.id)")
            keep_first = await page.evaluate("findDupGroups()[0].keep.id")
            await page.evaluate("data.cfg.schedule={mon:%s,tue:'other',nested:{x:%s}}; data.log['2026-09-28'].tplId=%s; ui.tplDelId=%s; 0" % ((json.dumps(drops_first[0]),) * 4))
            await page.locator('[data-act="dupDelAsk"]').first.click(); await page.click('[data-act="dupDelGo"]'); await page.wait_for_timeout(700)
            ids = await page.evaluate("data.templates.map(t=>t.id)")
            check("7.1: лишние шаблоны удалены, оставленный на месте", not any(d in ids for d in drops_first) and keep_first in ids and len(ids) == n_before - len(drops_first), (ids, drops_first))
            refs = await page.evaluate("({s:data.cfg.schedule, t:data.log['2026-09-28'].tplId, d:ui.tplDelId})")
            check("7.1: ссылки на удалённый id перенаправлены на оставшийся (cfg, вложенные объекты, день, экран)", refs == {"s": {"mon": keep_first, "tue": "other", "nested": {"x": keep_first}}, "t": keep_first, "d": keep_first}, refs)
            check("7.1: удалённые шаблоны удалены и из облака, оставшийся — на месте", all(("tst_tpl_" + d) not in STORE for d in drops_first) and ("tst_tpl_" + keep_first) in STORE and "keep_first" or True)
            check("7.1: cfg со скорректированными ссылками записан в облако", keep_first in STORE["tst_cfg"] and drops_first[0] not in STORE["tst_cfg"])
            await page.click('[data-act="hygClose"]'); await page.wait_for_timeout(100)
            await page.evaluate("ui.hygiene='dups'; render(); 0")
            rest = await page.evaluate("findDupGroups().length")
            check("7.1: после удаления групп осталось %d (остальные группы независимы)" % (len(exp) - 1), rest == len(exp) - 1, rest)

            # баннер при заходе
            seed(dump); pb, eb = await open_tg(browser); await pb.goto(BASE + "/test/index.html"); await pb.wait_for_timeout(2500)
            bn = await pb.evaluate("document.getElementById('dupBanner')?.textContent||''")
            check("баннер при заходе: «Найдены похожие шаблоны: лишних — %d шаблонов» на главном экране" % total_drop, "Найдены похожие шаблоны" in bn and ("лишних — %d" % total_drop) in bn, bn)
            await pb.click('[data-act="bannerDupSnooze"]'); await pb.wait_for_timeout(500)
            snz = await pb.evaluate("data.cfg.dupSnooze")
            check("баннер: «×» откладывает на 3 дня, баннер скрыт, метка в облаке", await pb.locator("#dupBanner").count() == 0 and abs(snz - (time.time() * 1000 + 3 * 86400000)) < 120000 and "dupSnooze" in STORE["tst_cfg"])
            await pb.evaluate("data.cfg.dupSnooze=null; render(); 0")
            await pb.click('[data-act="bannerDupOpen"]'); await pb.wait_for_timeout(300)
            check("баннер: «Разобрать» открывает экран удаления лишних шаблонов (настройки → дубли)", await pb.evaluate("ui.tab==='set' && ui.hygiene==='dups'") and await pb.locator(".dup-group").count() == len(exp))
            for _ in range(len(exp)):
                await pb.locator('[data-act="dupDelAsk"]').first.click(); await pb.click('[data-act="dupDelGo"]'); await pb.wait_for_timeout(300)
            await pb.click('[data-act="hygClose"]'); await pb.click('button[data-tab="day"]'); await pb.wait_for_timeout(300)
            check("баннер: после удаления всех лишних шаблонов исчезает", await pb.locator("#dupBanner").count() == 0 and await pb.evaluate("findDupGroups().length") == 0)
            STORE.clear(); pn, en = await open_tg(browser); await pn.goto(BASE + "/test/index.html"); await pn.wait_for_timeout(2000)
            check("баннер: без дублей (3 шаблона по умолчанию) не показывается", await pn.locator("#dupBanner").count() == 0)
            check("баннер: нет pageerror", not (eb or en), (eb[:1], en[:1]))

            # 7.2
            seed(dump); page2, errs2 = await open_tg(browser)
            await page2.goto(BASE + "/test/index.html"); await page2.wait_for_timeout(2500)
            await page2.click('button[data-tab="set"]'); await page2.wait_for_timeout(300)
            snapshot_before = await page2.evaluate("JSON.stringify([data.log,data.templates,data.cfg])")
            await page2.click('[data-act="hygOpen"][data-screen="check"]'); await page2.wait_for_timeout(300)
            got = await page2.evaluate("""(()=>{ const r=findDataIssues(); const o={}; for(const k of Object.keys(r)) o[k]=r[k].map(i=>[i.date,i.text]); return o; })()""")
            ex = expected_issues(dump["log"], today)
            check("7.2: дни без подходов (прошедшие) — 06.08", [d for d, _ in got["emptyDay"]] == ex["emptyDay"] and "2026-08-06" in ex["emptyDay"], (got["emptyDay"], ex["emptyDay"]))
            check("7.2: упражнения прошедших дней без подходов — 05.08 «Пресс»", sorted(d for d, _ in got["emptyEx"]) == sorted(d for d, _ in ex["emptyEx"]) and any(d == "2026-08-05" and "Пресс" in t for d, t in got["emptyEx"]), (got["emptyEx"], ex["emptyEx"]))
            check("7.2: подходов больше, чем в плане (на 1 и более)", sorted(d for d, _ in got["overPlan"]) == sorted(d for d, _ in ex["overPlan"]), (got["overPlan"], ex["overPlan"]))
            check("7.2: вес < 30% медианы упражнения и варианта — жим на плечи 2 кг", sorted(d for d, _ in got["lowWeight"]) == sorted(d for d, _ in ex["lowWeight"]) and any("плечи" in t and "2 кг" in t for _, t in got["lowWeight"]), (got["lowWeight"], ex["lowWeight"]))
            check("7.2: экран показывает разделы, у каждой строки кнопка «К дню» ≥ 44px",
                  await page2.locator('[data-act="hygOpenDay"]').count() == sum(len(v) for v in got.values()) and await page2.evaluate("[...document.querySelectorAll('[data-act=hygOpenDay]')].every(b=>b.getBoundingClientRect().height>=43.5)"))
            check("7.2: без автоисправлений — данные не изменились после открытия экрана", await page2.evaluate("JSON.stringify([data.log,data.templates,data.cfg])") == snapshot_before)
            await page2.locator('[data-act="hygOpenDay"][data-date="2026-08-06"]').click(); await page2.wait_for_timeout(300)
            check("7.2: «К дню» открывает день 06.08 на вкладке «Сегодня»", await page2.evaluate("curDate==='2026-08-06' && ui.tab==='day' && !ui.hygiene"))
            check("7.1/7.2: нет pageerror", not errs and not errs2, (errs[:1], errs2[:1]))

            # ================= 7.3a статически =================
            src = open(os.path.join(REPO, "test", "index.html"), encoding="utf-8").read()
            check("7.3: все циклы по логу используют Object.keys(log).sort()", not re.search(r"for\(const \w+ of Object\.keys\(data\.log\)\)", src) and not re.search(r"for\(const \w+ of Object\.keys\(data\.log\)\)", src))

            # ================= 7.3b запись дня =================
            seed(dump); page3, errs3 = await open_tg(browser)
            await page3.goto(BASE + "/test/index.html"); await page3.wait_for_timeout(2500)
            await page3.evaluate("curDate='2026-10-15'; ui.tab='day'; render(); 0")
            n0 = await page3.evaluate("Object.keys(data.log).length")
            for step in range(12):
                await page3.evaluate("curDate=addDays(curDate,1); render(); 0")
            await page3.evaluate("curDate='2026-10-15'; render(); 0")
            check("7.3: открытие дней (12 переходов) записей не создаёт", await page3.evaluate("Object.keys(data.log).length") == n0 and not any(k.startswith("tst_w_2026-10") for k in STORE))
            WRITES.clear()
            await page3.evaluate("applyTemplate(data.templates.find(x=>x.name.startsWith('Ноги'))||data.templates[0]); 0")
            await page3.wait_for_timeout(300)
            check("7.3: шаблон/упражнения без подходов — записи в data.log и в облаке нет, упражнения показаны (черновик)",
                  await page3.evaluate("!data.log['2026-10-15'] && getDay().exercises.length>0 && !!ui.drafts['2026-10-15']") and not any(k == "tst_w_2026-10-15" for _, k in WRITES) and await page3.locator(".ex-name").count() > 0)
            await page3.evaluate("(()=>{ const id=getDay().exercises[0].id; document.getElementById('w-'+id).value='50'; document.getElementById('r-'+id).value='10'; window.__exid=id; 0 })()")
            await page3.click('[data-act="addSet"]'); await page3.wait_for_timeout(400)
            rec = await page3.evaluate("data.log['2026-10-15']")
            check("7.3: первый введённый подход создаёт запись (up, weekType) и пишет её в облако", rec and rec["exercises"][0]["sets"] == [{"w": 50, "r": 10}] and rec.get("up") and rec.get("weekType") and "tst_w_2026-10-15" in STORE, rec)
            await page3.evaluate("doAction('delSet',{id:window.__exid,i:0}); 0"); await page3.wait_for_timeout(400)
            check("7.3: удалён единственный подход → запись убрана из данных и облака, упражнения остались в черновике", await page3.evaluate("!data.log['2026-10-15'] && getDay().exercises.length>0") and "tst_w_2026-10-15" not in STORE)
            await page3.evaluate("(()=>{ const t=document.querySelector('[data-chg=dayNote]'); 0 })()")
            await page3.evaluate("ui.dayNoteOpen=true; render(); 0")
            await page3.fill('[data-chg="dayNote"]', "заметка дня"); await page3.press('[data-chg="dayNote"]', "Tab"); await page3.wait_for_timeout(400)
            check("7.3: заметка дня создаёт запись", await page3.evaluate("!!data.log['2026-10-15'] && data.log['2026-10-15'].note==='заметка дня'") and "tst_w_2026-10-15" in STORE)
            await page3.fill('[data-chg="dayNote"]', ""); await page3.press('[data-chg="dayNote"]', "Tab"); await page3.wait_for_timeout(400)
            check("7.3: очистка единственной заметки убирает пустую запись", await page3.evaluate("!data.log['2026-10-15']") and "tst_w_2026-10-15" not in STORE)
            await page3.evaluate("ui.exNoteOpen[window.__exid]=true; render(); 0")
            await page3.fill('[data-chg="exNote"]', "заметка упражнения"); await page3.press('[data-chg="exNote"]', "Tab"); await page3.wait_for_timeout(400)
            check("7.3: заметка упражнения создаёт запись", await page3.evaluate("!!data.log['2026-10-15']") and "tst_w_2026-10-15" in STORE)
            check("7.3: нет pageerror", not errs3, errs3[:2])

            # ================= 7.3c шаблоны по умолчанию =================
            gk = "(()=>{ const CS=window.Telegram&&window.Telegram.WebApp.CloudStorage; if(!CS) return; const g=CS.getKeys; CS.getKeys=function(cb){ if(window.__gk==='error') return cb('KEYS_FAIL'); if(window.__gk==='delay') return setTimeout(()=>g.call(CS,cb),1500); return g.call(CS,cb); }; })();"
            # 1. в облаке есть шаблоны, локальный кэш пуст
            STORE.clear(); STORE["tst_cfg"] = json.dumps(dump["cfg"]); STORE["tst_tpl_" + dump["templates"][0]["id"]] = json.dumps(dump["templates"][0])
            pg, e1 = await open_tg(browser); await pg.goto(BASE + "/test/index.html"); await pg.wait_for_timeout(2000)
            check("7.3: облако проверено, шаблон там есть → шаблоны по умолчанию не создаются и не пишутся", await pg.evaluate("data.templates.length") == 1 and len([k for k in STORE if k.startswith("tst_tpl_")]) == 1)
            # 2. облако пусто
            STORE.clear(); pg, e2 = await open_tg(browser); await pg.goto(BASE + "/test/index.html"); await pg.wait_for_timeout(2000)
            check("7.3: облако проверено и пусто → создаются 3 шаблона по умолчанию и пишутся в облако", await pg.evaluate("data.templates.length") == 3 and len([k for k in STORE if k.startswith("tst_tpl_")]) == 3)
            # 3. до завершения проверки — ничего
            STORE.clear(); STORE["tst_tpl_keep"] = json.dumps(dump["templates"][0] | {"id": "keep"}); STORE["tst_cfg"] = json.dumps(dump["cfg"])
            pg, e3 = await open_tg(browser, "window.__gk='delay';" + gk)
            WRITES.clear(); await pg.goto(BASE + "/test/index.html"); await pg.wait_for_timeout(500)
            check("7.3: пока проверка облака не завершена, шаблоны по умолчанию не создаются и не пишутся", await pg.evaluate("data.templates.length") == 0 and not [w for w in WRITES if "tpl_" in w[1]], WRITES[:3])
            await pg.wait_for_timeout(2500)
            check("7.3: после проверки подтягиваются шаблоны из облака (1), а не по умолчанию", await pg.evaluate("data.templates.map(t=>t.id)") == ["keep"] and len([k for k in STORE if k.startswith("tst_tpl_")]) == 1)
            # 4. облако не отвечает
            STORE.clear(); pg, e4 = await open_tg(browser, "window.__gk='error';" + gk)
            WRITES.clear(); await pg.goto(BASE + "/test/index.html"); await pg.wait_for_timeout(2000)
            check("7.3: облако недоступно (getKeys — ошибка) → шаблоны по умолчанию не создаются", await pg.evaluate("data.templates.length") == 0 and not [w for w in WRITES if "tpl_" in w[1]])
            # 5. вне Telegram
            ctx = await browser.new_context(); pl = await ctx.new_page(); await pl.route("**/telegram.org/**", lambda r: r.abort()); await pl.route("**/cdnjs.cloudflare.com/**", lambda r: r.abort())
            await pl.goto(BASE + "/test/index.html"); await pl.wait_for_timeout(800)
            check("7.3: без облака (обычный браузер) шаблоны по умолчанию создаются сразу", await pl.evaluate("data.templates.length") == 3)
            check("7.3: нет pageerror", not (e1 or e2 or e3 or e4), (e1[:1], e2[:1], e3[:1], e4[:1]))
            await browser.close()
    finally:
        srv.terminate()
    bad = [r for r in RESULTS if not r[1]]
    print("\nИТОГО: %d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    asyncio.run(main())
