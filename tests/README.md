# Автотесты test/index.html

Браузерные тесты (Playwright + установленный Microsoft Edge) с моком Telegram WebApp и «облаком» CloudStorage в памяти.

```
python -m pip install playwright openpyxl
python tests/test_step0.py      # фаза 10, задача 0 (изоляция, клонирование, миграции)
python tests/test_task1.py … test_task8.py
python tests/test_p11_t1.py … test_p11_t5.py   # фаза 11
python tests/test_p12_t1.py … test_p12_t6.py   # фаза 12 (t6 — интерактивный тур)
python tests/test_p13_t2.py … test_p13_t9.py   # фаза 13 (t4 — пикер цвета, t9 — режим браузера)
python tests/test_real_data.py  # задачи 1–2 на реальном дампе
python tests/test_final.py      # итоговая проверка: боевые ключи и v2 не меняются
```

Тесты на реальных данных читают `../current_data.json` и `../Тренировки(2).xlsx` (лежат рядом с репозиторием, не в нём) и пропускаются, если файлов нет.
Статический сервер поднимается на порту 8765 самими тестами.
