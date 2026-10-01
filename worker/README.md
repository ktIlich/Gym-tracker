# gym-tracker-backup — Cloudflare Worker

Отправляет резервную копию (JSON / Excel / CSV) в чат пользователя с ботом. Токен бота хранится в секретах Worker и не попадает в клиент, а личность пользователя проверяется по подписи `initData` Telegram Mini App.

## Деплой

```
npm i -g wrangler
cd worker
wrangler login
wrangler secret put BOT_TOKEN
wrangler deploy
```

После деплоя скопируйте адрес Worker (`https://gym-tracker-backup.<аккаунт>.workers.dev/`) в константу `BACKUP_ENDPOINT` в `test/index.html` (и позже в `v2/index.html`). Пока константа пустая, кнопки «Отправить в чат» в приложении скрыты.

## API

`POST /` с `Content-Type: application/json`:

```json
{ "initData": "<Telegram.WebApp.initData>", "env": "test|prod", "format": "json|xlsx|csv",
  "filename": "gym-tracker-2026-09-30.xlsx", "content": "<текст или base64>", "encoding": "text|base64", "note": "необязательная подпись" }
```

Ответ — JSON `{ ok, error?, description? }`:

| Код | Когда |
|---|---|
| 200 | файл отправлен |
| 400 | некорректное тело запроса |
| 403 | подпись `initData` не совпала (`bad_signature`) или он старше 3600 с (`expired`) |
| 413 | файл больше 5 МБ после декодирования |
| 502 | Telegram вернул ошибку |

`chat_id` берётся только из `user.id` проверенного `initData`. В подписи к файлу для `env: "test"` добавляется ` · TEST`.

CORS: `Access-Control-Allow-Origin: https://ktilich.github.io` (v2 и test), методы `POST, OPTIONS`.

## Локальный запуск

Создайте `worker/.dev.vars` (в git не попадает) со строкой `BOT_TOKEN=...` и выполните `wrangler dev`.
