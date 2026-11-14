# БЕЗТЕЛ

Сайт для изучения башкирского языка и Telegram-бот рядом с ним.

Сайт: регистрация, хаб, словарь, уроки, чат, дейлики, состязания, школы и рейтинг.
Бот: напоминания, профиль и рейтинг. Учёба остаётся на сайте.

Нужны Python 3.11+ и PostgreSQL 16. Словарь уже лежит в `data/phrasebooks.jsonl` и загружается в базу при первом запуске сайта.

## 1. Настройки

В корне один файл `.env`. Его нет в git.

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Откройте `.env` и заполните:

| Переменная | Зачем |
| --- | --- |
| `BOT_TOKEN` | токен от [@BotFather](https://t.me/BotFather). Без него бот не стартует. Сайт работает и без бота. |
| `BOT_USERNAME` | имя бота без `@` |
| `llm_api_key` | ключ [Groq](https://console.groq.com/). Без него чат с носителем не отвечает. |
| `secret_key` | длинная случайная строка. Ею подписывается вход. |
| `MINI_APP_URL` | адрес сайта. Кнопка «Приложение» в Telegram появляется только если адрес начинается с `https://`. |
| `database_url` | строка подключения к PostgreSQL. Для локальной базы значение из примера уже подходит. |

Остальные поля можно оставить как в примере. Пути `frontend_dir`, `data_dir`, `dataset_file` и `hf_home` задаются от корня проекта, не от диска разработчика.

## 2. База данных

Через Docker, из корня проекта:

```bash
docker compose up -d
```

Поднимется только PostgreSQL: пользователь `bashkar`, пароль `bashkar`, база `bashkar`, порт `5432`.

Без Docker создайте ту же базу сами и поправьте `database_url` в `.env`.

## 3. Сайт

```bash
cd backend
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Linux / macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Откройте [http://127.0.0.1:8000](http://127.0.0.1:8000).

- Документация API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Проверка: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

Первый запуск создаёт таблицы и импортирует словарь. Первый запрос озвучки скачивает модель в папку из `hf_home`, это занимает несколько минут. Регистрация и вход — на самом сайте.

## 4. Бот

Отдельное окружение, потому что боту не нужны модели речи.

```bash
cd bot
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

Linux / macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

В логе будет строка `Бот запущен. Напоминания в 10:00 и 20:00 по Уфе`. Напоминания уходят, только пока этот процесс работает. В боте доступны профиль и рейтинг.

## 5. Весь проект на сервере

На машине с Docker, из корня:

```bash
cp .env.example .env
# впишите BOT_TOKEN, llm_api_key, secret_key и публичный MINI_APP_URL

docker compose --profile app up -d --build
```

Поднимутся база, сайт на порту `8000` и бот. Внутри сети контейнеров база доступна как `db`, отдельно менять `database_url` не нужно.

Первая сборка долгая: в образ сайта ставится PyTorch для озвучки и распознавания. Модели кэшируются в томе `hf-cache`.

Остановить:

```bash
docker compose --profile app down
```

Данные базы останутся в томе `pgdata`. Чтобы удалить и их: `docker compose --profile app down -v`.

## Как устроено

```
bashkar/
├── .env.example          # образец настроек
├── docker-compose.yml    # база, а с профилем app ещё сайт и бот
├── Dockerfile            # образ сайта
├── data/phrasebooks.jsonl
├── frontend/             # страницы сайта
├── backend/              # FastAPI
└── bot/                  # Telegram-бот
```

Сайт и бот читают только корневой `.env`.
