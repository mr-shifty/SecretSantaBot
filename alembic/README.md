Alembic folder for DB migrations.

How to generate and apply migrations locally:

1. Ensure your virtualenv is active and dependencies are installed:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Make sure `bot.config.settings.database_url` (or env `DATABASE_URL`) points to your DB. Example `.env`:

```
DATABASE_URL=sqlite+aiosqlite:///./data.db
BOT_TOKEN=your_token_here
```

3. Create an autogenerate revision (optional if you want to modify migration):

```bash
alembic revision --autogenerate -m "add initial tables"
```

4. Apply migrations:

```bash
alembic upgrade head
```

Notes:
- The repository already contains a starter migration `alembic/versions/0001_initial.py` which creates the initial tables.
- Alembic config uses `bot.config.settings.database_url` from your app settings (see `alembic/env.py`).
