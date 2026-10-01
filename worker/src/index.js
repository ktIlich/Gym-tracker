// Gym Tracker — отправка резервных копий в чат бота.
// Токен бота хранится в секрете BOT_TOKEN и не попадает в клиент; личность пользователя проверяется по подписи initData.
// Один эндпоинт: POST /. Зависимостей нет (Web Crypto, fetch, FormData).

const ALLOWED_ORIGIN = "https://ktilich.github.io";   // покрывает и v2, и test
const MAX_BYTES = 5 * 1024 * 1024;                     // размер файла после декодирования
const MAX_BODY_CHARS = 8 * 1024 * 1024;                // потолок тела запроса до разбора JSON (base64 5 МБ ≈ 6,7 МБ)
const MAX_AGE_SEC = 3600;                              // срок годности initData
const FORMATS = {
  json: { mime: "application/json", ext: "json" },
  xlsx: { mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ext: "xlsx" },
  csv:  { mime: "text/csv", ext: "csv" },
};

class HttpError extends Error {
  constructor(status, error, description) { super(description || error); this.status = status; this.error = error; this.description = description; }
}

const CORS = {
  "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
  "Vary": "Origin",
};

function json(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" } });
}

const enc = new TextEncoder();

async function hmac(keyBytes, dataBytes) {
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, dataBytes));
}

function toHex(bytes) {
  let s = "";
  for (const b of bytes) s += b.toString(16).padStart(2, "0");
  return s;
}

// сравнение за постоянное время (XOR-накопление)
function timingSafeEqual(a, b) {
  const x = enc.encode(String(a)), y = enc.encode(String(b));
  let diff = x.length ^ y.length;
  const n = Math.max(x.length, y.length);
  for (let i = 0; i < n; i++) diff |= (x[i] || 0) ^ (y[i] || 0);
  return diff === 0;
}

// Проверка подписи initData (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).
// Возвращает распарсенный user или бросает HttpError(403).
export async function verifyInitData(initData, botToken, nowSec = Math.floor(Date.now() / 1000)) {
  const params = new URLSearchParams(initData);
  const hash = params.get("hash");
  if (!hash) throw new HttpError(403, "bad_signature", "initData без hash");
  params.delete("hash");
  const pairs = [];
  for (const [k, v] of params.entries()) pairs.push([k, v]);
  pairs.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  const dataCheckString = pairs.map(([k, v]) => k + "=" + v).join("\n");
  const secret = await hmac(enc.encode("WebAppData"), enc.encode(botToken));
  const calc = toHex(await hmac(secret, enc.encode(dataCheckString)));
  if (!timingSafeEqual(calc, hash.toLowerCase())) throw new HttpError(403, "bad_signature", "Подпись initData не совпала");
  const authDate = parseInt(params.get("auth_date"), 10);
  if (!Number.isFinite(authDate)) throw new HttpError(403, "bad_signature", "В initData нет auth_date");
  if (nowSec - authDate > MAX_AGE_SEC) throw new HttpError(403, "expired", "initData устарел, откройте приложение заново");
  let user;
  try { user = JSON.parse(params.get("user") || ""); } catch { user = null; }
  if (!user || !Number.isSafeInteger(user.id)) throw new HttpError(403, "bad_signature", "В initData нет user.id");
  return user;
}

function decodeContent(content, encoding) {
  if (typeof content !== "string") throw new HttpError(400, "bad_request", "content должен быть строкой");
  if (encoding === "text") {
    const bytes = enc.encode(content);
    if (bytes.length > MAX_BYTES) throw new HttpError(413, "too_large", "Файл больше 5 МБ");
    return bytes;
  }
  // base64: оцениваем размер до декодирования
  const clean = content.replace(/\s+/g, "");
  if (Math.floor(clean.length * 3 / 4) > MAX_BYTES + 3) throw new HttpError(413, "too_large", "Файл больше 5 МБ");
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(clean) || clean.length % 4 === 1) throw new HttpError(400, "bad_request", "content не является корректным base64");
  let bin;
  try { bin = atob(clean); } catch { throw new HttpError(400, "bad_request", "content не является корректным base64"); }
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  if (bytes.length > MAX_BYTES) throw new HttpError(413, "too_large", "Файл больше 5 МБ");
  return bytes;
}

// имя файла: без путей и управляющих символов, с расширением формата
function safeFilename(name, format) {
  const ext = FORMATS[format].ext;
  let base = typeof name === "string" ? name.replace(/[\\/\u0000-\u001f]/g, "").trim() : "";
  base = base.slice(0, 100);
  if (!base) base = "gym-tracker-" + new Date().toISOString().slice(0, 10);
  if (!base.toLowerCase().endsWith("." + ext)) base = base.replace(/\.[A-Za-z0-9]{1,5}$/, "") + "." + ext;
  return base;
}

async function handle(request, env) {
  if (!env || !env.BOT_TOKEN) throw new HttpError(500, "server_misconfigured", "BOT_TOKEN не задан");
  const url = new URL(request.url);
  if (url.pathname !== "/") throw new HttpError(404, "not_found", "Не найдено");
  if (request.method !== "POST") throw new HttpError(405, "method_not_allowed", "Только POST");

  const declared = parseInt(request.headers.get("Content-Length") || "0", 10);
  if (declared > MAX_BODY_CHARS) throw new HttpError(413, "too_large", "Тело запроса слишком большое");
  const raw = await request.text();
  if (raw.length > MAX_BODY_CHARS) throw new HttpError(413, "too_large", "Тело запроса слишком большое");

  let body;
  try { body = JSON.parse(raw); } catch { throw new HttpError(400, "bad_request", "Тело запроса — не JSON"); }
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new HttpError(400, "bad_request", "Тело запроса — не объект");
  const { initData, env: appEnv, format, filename, content, encoding } = body;
  if (typeof initData !== "string" || !initData) throw new HttpError(400, "bad_request", "Нет initData");
  if (appEnv !== "test" && appEnv !== "prod") throw new HttpError(400, "bad_request", "env: test или prod");
  if (typeof format !== "string" || !Object.prototype.hasOwnProperty.call(FORMATS, format)) throw new HttpError(400, "bad_request", "format: json, xlsx или csv");
  if (encoding !== "text" && encoding !== "base64") throw new HttpError(400, "bad_request", "encoding: text или base64");

  const user = await verifyInitData(initData, env.BOT_TOKEN);   // 403
  const bytes = decodeContent(content, encoding);               // 400 / 413
  if (!bytes.length) throw new HttpError(400, "bad_request", "Пустой файл");

  const fmt = FORMATS[format];
  // необязательная подпись `note` (например «Копия перед обновлением до v2.13.0»): одна строка, до 120 символов; чат берётся только из initData
  const note = typeof body.note === "string" ? body.note.replace(/[\r\n]+/g, " ").trim().slice(0, 120) : "";
  const caption = (note || "Резервная копия Gym Tracker") + " · " + new Date().toISOString().slice(0, 10) + (appEnv === "test" ? " · TEST" : "");
  const form = new FormData();
  form.append("chat_id", String(user.id));   // только из проверенного initData, никогда из тела
  form.append("caption", caption);
  form.append("document", new Blob([bytes], { type: fmt.mime }), safeFilename(filename, format));

  let tgRes, tg;
  try {
    tgRes = await fetch("https://api.telegram.org/bot" + env.BOT_TOKEN + "/sendDocument", { method: "POST", body: form });
    tg = await tgRes.json();
  } catch (e) {
    throw new HttpError(502, "telegram_error", "Не удалось связаться с Telegram");
  }
  if (!tgRes.ok || !tg || !tg.ok) throw new HttpError(502, "telegram_error", (tg && tg.description) || "Telegram вернул ошибку");
  return json(200, { ok: true });
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    try {
      return await handle(request, env);
    } catch (e) {
      if (e instanceof HttpError) return json(e.status, { ok: false, error: e.error, description: e.description });
      return json(500, { ok: false, error: "internal_error", description: "Внутренняя ошибка" });
    }
  },
};
