# Secret Santa Bot

Полнофункциональный Telegram-бот для организации тайного Санты с двумя маршрутами регистрации, автоматическим распределением, админ-панелью и системой напоминаний.

## Особенности

- **Две ветки регистрации:**
  - **Маршрут 1:** полная информация (email, адрес, способ доставки, пожелания)
  - **Маршрут 2:** упрощённая (только email)
- **Защита от дубликатов:** один пользователь — одна активная заявка на маршрут
- **Автоматическое распределение** (розыгрыш) с защитой от самоприсвоения
- **Админ-команды бота:** `/draw_route1`, `/draw_route2`, `/notify_route1`, `/export_route1`, и т.д.
- **FastAPI админ-панель** для просмотра/редактирования всех данных и экспорта CSV
- **Планировщик** (APScheduler): автоматическая аннуляция через 7 дней, переразыгрыш
- **База данных:** SQLAlchemy + Alembic миграции (работает с SQLite и PostgreSQL)

## Установка и запуск

### Локально (без Docker)

1. **Создайте виртуальное окружение:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # на Windows: .venv\Scripts\activate
   ```

2. **Установите зависимости:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Настройте переменные окружения в `.env`:**
   ```
   BOT_TOKEN=ваш_токен_бота_здесь
   DATABASE_URL=sqlite+aiosqlite:///./data.db
   ADMIN_IDS=111111,222222
   REMINDER_HOURS=24
   ```

4. **Примените миграции БД:**
   ```bash
   alembic upgrade head
   ```
   Или пропустите этот шаг — таблицы создадутся автоматически при запуске бота.

5. **Запустите бота:**
   ```bash
   python -m bot.main
   ```

6. **Запустите админ-панель (в отдельном терминале):**
   ```bash
   uvicorn admin_panel.main:app --reload
   ```
   Панель доступна на `http://127.0.0.1:8000/docs`

### С Docker

1. **Соберите и запустите контейнеры:**
   ```bash
   docker-compose up --build
   ```

2. **Админ-панель доступна на:** `http://localhost:8000/docs`

### Развёртывание на сервере (production)

Минимальная схема: Docker + docker-compose + обратный прокси с TLS (например, Caddy).

1. **Подготовка сервера:**
   - Установите Docker и docker-compose (Docker Compose v2 рекомендуется).
   - Настройте DNS: `DOMAIN` (см. `.env.production.example`) должен указывать на IP сервера.

2. **Скопируйте пример env и заполните:**
   ```bash
   cp .env.production.example .env.production
   # отредактируйте .env.production: укажите DOMAIN, BOT_TOKEN, ADMIN_PASSWORD и др.
   ```

3. **Запуск в фоне:**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d --build
   ```

4. **Открытые порты:**
   - Откройте 80 и 443 (HTTP/HTTPS) в брандмауэре, чтобы Caddy мог получить и обновлять TLS-сертификаты.

### Прямой доступ по IP (быстро, без TLS)

- Если хотите доступить админ-панель напрямую по IP, можно открыть порт `8000` и пробросить его хосту.
- В `docker-compose.prod.yml` уже есть `ports: - "8000:8000"` для сервиса `admin`.
- Откройте порт и перезапустите стек:
   ```bash
   sudo ufw allow 8000/tcp
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d --build
   ```
- После этого админ-панель будет доступна по `http://<IP>:8000/admin`.
- ВАЖНО: это соединение без TLS — используйте только в защищённой сети или временно. Для публичного доступа лучше настроить домен и HTTPS через Caddy.

### Использование PostgreSQL

- По умолчанию вы можете использовать SQLite, но для production рекомендуется PostgreSQL.
- В `.env.production` задайте `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` и/или `DATABASE_URL`.
- Если вы не зададите `DATABASE_URL`, контейнеры будут использовать локальный SQLite как fallback.
- Пример `DATABASE_URL` для asyncpg-драйвера:
   `postgresql+asyncpg://<user>:<password>@postgres:5432/<db>`

Docker Compose в `docker-compose.prod.yml` уже содержит сервис `postgres`, поэтому достаточно настроить `.env.production` и запустить `docker compose up`. Ниже — подробная инструкция по настройке и использованию PostgreSQL в Docker.

####  Подробная настройка PostgreSQL в Docker

1) **Переменные окружения** — заполните `.env.production`:
   - `POSTGRES_USER` — имя пользователя (например `secret`)
   - `POSTGRES_PASSWORD` — пароль
   - `POSTGRES_DB` — имя базы данных (например `secret_santa`)
   - (опционально) `DATABASE_URL` — полный URL подключения (например `postgresql+asyncpg://secret:secret@postgres:5432/secret_santa`)

2) **Запуск Postgres через Docker Compose** (отдельно или вместе со всем стеком):
   ```bash
   # Поднять только postgres
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d postgres

   # Поднять весь стек
   docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d --build
   ```

3) **Проверка готовности и запуск миграций**:
   - Postgres имеет `healthcheck`; дождитесь статуса `healthy`:
     ```bash
     docker compose ps
     docker compose logs -f postgres
     ```
   - Запустите alembic вручную, если хотите контролировать порядок или отладить:
     ```bash
     docker compose exec bot alembic upgrade head
     # или
     docker compose exec admin alembic upgrade head
     ```
   Замечание: `alembic upgrade head` уже выполняется в `entrypoint` сервисов `admin` и `bot`, но иногда полезно вызвать вручную после миграции/переноса данных.

4) **Бэкапы/восстановление**:
   - Бэкап (на хост):
     ```bash
     docker compose exec postgres pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} > backup.sql
     ```
   - Восстановление:
     ```bash
     cat backup.sql | docker compose exec -T postgres psql -U ${POSTGRES_USER} ${POSTGRES_DB}
     ```

5) **Миграция данных из SQLite (опционально)**:
   - Для переноса данных можно использовать `pgloader` (или кастомный скрипт миграции).
   - Пример с `pgloader` через Docker (работает, если `data.db` доступен в корне и вы запускаете команду в папке проекта):
     ```bash
     docker run --rm --network $(docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production ps -q postgres | xargs docker inspect -f '{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}') -v "$(pwd):/work" dpage/pgloader:latest \
         pgloader /work/data.db postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres:5432/$POSTGRES_DB
     ```
   - Важно: после переноса проверьте целостность данных и пересчитайте индексы, если требуется.

   Скрипты (`scripts/backup_postgres.sh`, `scripts/sqlite_to_postgres.sh`) включены в репозитории как примеры, не забудьте сделать их исполняемыми или запускать через `bash`:
   ```bash
   chmod +x scripts/backup_postgres.sh scripts/sqlite_to_postgres.sh
   ./scripts/backup_postgres.sh backup.sql
   ./scripts/sqlite_to_postgres.sh
   ```

6) **Безопасность и рекомендации**:
   - Не экспонируйте порт Postgres наружу резко — держите его в Docker-сети, если возможно.
   - Используйте надёжные пароли, ключи и бэкапы.
   - Тестируйте миграции на копии данных, прежде чем применить к production.


5. **Доступ к админ-панели:**
   - После успешного запуска админ-панель будет доступна по https://<DOMAIN>/admin

6. **Резервное копирование и безопасность:**
   - `data.db` хранится в корне проекта, сделайте регулярные резервные копии.
   - Используйте надёжный пароль в `ADMIN_PASSWORD`.
   - Рассмотрите добавление базовой авторизации на прокси (Caddy поддерживает `basicauth`).

7. **Запуск как сервис (systemd):**
   - В качестве примера можно создать unit-файл для `docker compose` и запускать его как сервис. См. `systemd/secret_santa.service.example`.

Примеры systemd-команд для установки unit:

```bash
sudo cp systemd/secret_santa.service.example /etc/systemd/system/secret_santa.service
# отредактируйте путь к рабочей директории и файлу .env.production в unit при необходимости
sudo systemctl daemon-reload
sudo systemctl enable --now secret_santa.service
sudo journalctl -fu secret_santa.service
```

Если используется PostgreSQL, база запускается внутри Docker-сети и порт по умолчанию не открыт наружу — это безопаснее для production.

Если нужно, могу подготовить unit-файл под вашу систему и помочь с настройкой DNS/брандмауэра.

## Команды бота

### Для пользователей

- `/route1` — регистрация для маршрута 1 (полная форма)
- `/route2` — регистрация для маршрута 2 (только email)
- `/cancel` — отмена текущей регистрации

### Для админов (список ID в `ADMIN_IDS`)

- `/draw_route1` — запустить розыгрыш для маршрута 1
- `/draw_route2` — запустить розыгрыш для маршрута 2
- `/notify_route1` — отправить уведомления участникам маршрута 1
- `/notify_route2` — отправить уведомления участникам маршрута 2
- `/export_route1` — экспортировать данные маршрута 1 в CSV
- `/export_route2` — экспортировать данные маршрута 2 в CSV

## API админ-панели (FastAPI)

Документация доступна на `/docs` (Swagger UI).

### Основные endpoints:

- `GET /stats` — статистика (количество пользователей, заявок, распределений)
- `GET /users` — список пользователей
- `GET /users/{user_id}` — информация о пользователе
- `GET /route1` — список заявок маршрута 1
- `PATCH /route1/{entry_id}` — редактировать заявку маршрута 1
- `GET /route2` — список заявок маршрута 2
- `PATCH /route2/{entry_id}` — редактировать заявку маршрута 2
- `GET /assignments` — список распределений (пар)
- `PATCH /assignments/{assignment_id}` — отметить пару как отправленную (`sent`)
- `POST /draw/{route_type}` — запустить розыгрыш
- `GET /export/route1` — скачать CSV маршрута 1
- `GET /export/route2` — скачать CSV маршрута 2

## Структура проекта

```
.
├── bot/
│   ├── main.py                    # Точка входа бота
│   ├── config.py                  # Переменные окружения
│   ├── states.py                  # FSM состояния
│   ├── utils.py                   # Утилиты и валидация
│   ├── randomizer.py              # Алгоритм распределения
│   ├── scheduler.py               # Планировщик задач
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── route1.py              # Обработчики маршрута 1
│   │   ├── route2.py              # Обработчики маршрута 2
│   │   └── admin.py               # Админ-команды
│   └── db/
│       ├── models.py              # SQLAlchemy модели
│       └── database.py            # DB инициализация
├── admin_panel/
│   └── main.py                    # FastAPI приложение
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   ├── alembic.ini
│   └── versions/
│       └── 0001_initial.py        # Первая миграция
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env                           # Переменные окружения (не коммитить!)
└── README.md
```

## Пример использования

### Для пользователя:
1. Откройте чат с ботом
2. Отправьте `/route1` или `/route2`
3. Ответьте на все вопросы (для маршрута 1) или введите email (для маршрута 2)
4. Заявка сохранится в БД

### Для админа:
1. Когда закончится время регистрации, отправьте `/draw_route1`
2. Бот создаст случайные пары (защита от самоприсвоения)
3. Отправьте `/notify_route1` для уведомления участников
4. Когда люди отправят подарки, измените статус в админ-панели или командой в боте
5. Через 7 дней без отправки система автоматически пересоздаст распределение

## Разработка

### Создание новой миграции

```bash
alembic revision --autogenerate -m "описание изменений"
alembic upgrade head
```

### Запуск тестов (заготовка)

```bash
pytest tests/
```

## Требования

- Python 3.11+
- SQLite или PostgreSQL
- Telegram Bot API token

## Лицензия

MIT

## Контакты

По вопросам разработки — создавайте Issues или Pull Requests.
