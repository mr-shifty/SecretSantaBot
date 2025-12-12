"""FastAPI admin panel for Secret Santa Bot."""
import csv
import io
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Request, Form
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from bot.db.database import init_db, get_session
from bot.db.models import User, Route1Entry, Route2Entry, Assignment, NotificationLog, Setting
from bot.randomizer import perform_draw
from bot.logger import get_logger
import json
import re
import aiohttp
import os
BOT_INTERNAL_URL = os.getenv('BOT_INTERNAL_URL', 'http://bot:9000/internal/trigger_reminders')
BOT_INTERNAL_SECRET = os.getenv('BOT_INTERNAL_SECRET')

logger = get_logger("admin_panel")
app = FastAPI(title="Secret Santa Admin Panel", version="1.0.0")

# Templates and static
templates = Jinja2Templates(directory="admin_panel/templates")
app.mount("/static", StaticFiles(directory="admin_panel/static"), name="static")
# serve uploaded media (images) from local media/ folder
import os as _os
_os.makedirs("media/route2", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

# Simple admin UI auth (password from env)
import os
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), 'settings.json')


def load_settings() -> dict:
	defaults = {
		'assignment_reminder_hours': 48,
		'assignment_reminder_max': 3,
		'registration_reminder_hours': 24,
		'reminder_enabled': True,
		# how often (in minutes) the bot should check reminders and possibly send them
		# this controls the scheduler check interval (default: 60 minutes)
		'reminder_check_interval_minutes': 60,
		# optional: allow finer-grained minute-based reminder thresholds
		'assignment_reminder_minutes': None,
		'registration_reminder_minutes': None,
	}
	try:
		if os.path.exists(SETTINGS_PATH):
			with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
				data = json.load(f)
				defaults.update(data)
				# Normalize minute-like settings coming from JSON file
				for k, v in list(defaults.items()):
					if k.endswith('_minutes') and isinstance(v, str):
						# strip non-digits
						clean = re.sub(r"[^0-9]", "", v)
						if clean == '':
							defaults[k] = None
						else:
							try:
								defaults[k] = int(clean)
							except Exception:
								defaults[k] = None
	except Exception:
		pass
	return defaults


async def load_settings_async() -> dict:
	"""Async loader for settings: merge JSON defaults with DB-stored settings when available."""
	# Start from JSON/defaults for backward compatibility
	settings = load_settings()
	# Try to read overrides from DB
	try:
		async_session = get_session()
		async with async_session as session:
			result = await session.execute(select(Setting))
			rows = result.scalars().all()
			for r in rows:
				# Setting.value is stored as JSON-serializable object; merge
				try:
					val = r.value
					# Normalize minute-like settings that may have ended up quoted or escaped
					if r.key and r.key.endswith('_minutes') and isinstance(val, str):
						# remove surrounding quotes and any backslashes, keep digits only
						clean = re.sub(r"[^0-9]", "", val)
						if clean == '':
							settings[r.key] = None
						else:
							try:
								settings[r.key] = int(clean)
							except Exception:
								settings[r.key] = None
					else:
						settings[r.key] = val
				except Exception:
					settings[r.key] = r.value
	except Exception:
		# If DB unavailable, fall back to JSON-only settings
			pass
	return settings


def save_settings(data: dict):
	try:
		with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
			json.dump(data, f, ensure_ascii=False, indent=2)
	except Exception:
		pass


async def save_settings_to_db(data: dict):
	"""Persist settings into DB (async). Creates/updates rows in `settings` table."""
	async_session = get_session()
	async with async_session as session:
		for k, v in data.items():
			# upsert
			result = await session.execute(select(Setting).where(Setting.key == k))
			rec = result.scalar_one_or_none()
			if rec:
				rec.value = v
				session.add(rec)
			else:
				session.add(Setting(key=k, value=v))
		await session.commit()


@app.post("/admin/trigger_reminders")
async def ui_trigger_reminders(request: Request, trigger_assignment: str | None = Form(None), trigger_registration: str | None = Form(None)):
	"""Set a manual trigger in the DB so the bot watcher can pick it up and send reminders immediately."""
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	assignment = bool(trigger_assignment)
	registration = bool(trigger_registration)
	if not (assignment or registration):
		# nothing selected
		return RedirectResponse(url="/admin/settings", status_code=302)
	# upsert Setting('manual_trigger') with timestamp
	from datetime import datetime
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Setting).where(Setting.key == 'manual_trigger'))
		rec = result.scalar_one_or_none()
		payload = {
			"assignment": assignment,
			"registration": registration,
			"ts": datetime.utcnow().isoformat(),
		}
		if rec:
			rec.value = payload
			session.add(rec)
		else:
			session.add(Setting(key='manual_trigger', value=payload))
		await session.commit()

		# Persist an initial queued history entry (we will update it after calling bot)
		try:
			hist_entry = {
				'ts': payload['ts'],
				'requested_assignment': assignment,
				'requested_registration': registration,
				'status': 'queued',
			}
			result = await session.execute(select(Setting).where(Setting.key == 'manual_trigger_history'))
			rec_hist = result.scalar_one_or_none()
			if rec_hist and isinstance(rec_hist.value, list):
				history = rec_hist.value
			else:
				history = []
			history.append(hist_entry)
			# keep only last 10
			history = history[-10:]
			if rec_hist:
				rec_hist.value = history
				session.add(rec_hist)
			else:
				session.add(Setting(key='manual_trigger_history', value=history))
			await session.commit()
		except Exception:
			pass

		# Try to call bot internal endpoint for immediate feedback (only if secret provided)
		trigger_result = None
		if BOT_INTERNAL_URL and BOT_INTERNAL_SECRET:
			async with aiohttp.ClientSession() as client:
				try:
					resp = await client.post(BOT_INTERNAL_URL, json=payload, headers={'X-Internal-Token': BOT_INTERNAL_SECRET}, timeout=30)
					if resp.status == 200:
						trigger_result = await resp.json()
					else:
						try:
							text = await resp.text()
						except Exception:
							text = None
						trigger_result = {'error': f'bot returned status {resp.status}', 'detail': text}
				except Exception as e:
					trigger_result = {'error': 'failed_to_call_bot', 'detail': str(e)}

		# Update last history entry with result if available
		try:
			async_session2 = get_session()
			async with async_session2 as session2:
				result = await session2.execute(select(Setting).where(Setting.key == 'manual_trigger_history'))
				rec2 = result.scalar_one_or_none()
				if rec2 and isinstance(rec2.value, list) and len(rec2.value) > 0:
					last = rec2.value[-1]
					# attach result details
					if isinstance(trigger_result, dict) and not trigger_result.get('error'):
						last['assignment_sent'] = trigger_result.get('assignment_sent', 0)
						last['registration_sent'] = trigger_result.get('registration_sent', 0)
						last['status'] = 'done'
					else:
						last['status'] = 'error'
						last['error'] = trigger_result.get('error') if isinstance(trigger_result, dict) else 'no_result'
					# persist back
					rec2.value[-1] = last
					session2.add(rec2)
					await session2.commit()
		except Exception:
			pass

		settings = await load_settings_async()
		return templates.TemplateResponse("edit_settings.html", {"request": request, "settings": settings, "trigger_result": trigger_result})


# ===== Pydantic models for request/response =====
class UserResponse(BaseModel):
	id: int
	telegram_id: int
	telegram_username: str | None
	first_name: str | None
	last_name: str | None
	phone: str | None
	created_at: datetime

	class Config:
		from_attributes = True


class Route1EntryResponse(BaseModel):
	id: int
	user_id: int
	email: str
	full_address: str | None
	delivery_method: str | None
	wishlist: str | None
	status: str
	pickup_type: str | None
	postal_city: str | None
	postal_street: str | None
	postal_building: str | None
	postal_corpus: str | None
	postal_apartment: str | None
	postal_recipient_fullname: str | None
	postal_recipient_phone: str | None
	pickup_company: str | None
	pickup_address: str | None
	pickup_recipient_fullname: str | None
	pickup_recipient_phone: str | None
	started_at: datetime
	completed_at: datetime | None

	class Config:
		from_attributes = True


class Route2EntryResponse(BaseModel):
	id: int
	user_id: int
	email: str
	image_path: str | None
	notify_date: datetime | None
	status: str
	started_at: datetime
	completed_at: datetime | None

	class Config:
		from_attributes = True


class AssignmentResponse(BaseModel):
	id: int
	giver_user_id: int
	receiver_user_id: int
	route_type: int
	assigned_at: datetime
	sent_status: str

	class Config:
		from_attributes = True


@app.on_event("startup")
async def startup():
	await init_db()


def is_admin_ui(request: Request) -> bool:
	return request.cookies.get("admin_auth") == ADMIN_PASSWORD


@app.get("/admin")
async def admin_index(request: Request):
	if not is_admin_ui(request):
		return templates.TemplateResponse("login.html", {"request": request, "error": None})

	# show basic dashboard
	async_session = get_session()
	async with async_session as session:
		total_users = len((await session.execute(select(User))).scalars().all())
		route1_entries = len((await session.execute(select(Route1Entry))).scalars().all())
		route2_entries = len((await session.execute(select(Route2Entry))).scalars().all())
		assignments = len((await session.execute(select(Assignment))).scalars().all())

	return templates.TemplateResponse("dashboard.html", {"request": request, "stats": {
		"total_users": total_users,
		"route1_entries": route1_entries,
		"route2_entries": route2_entries,
		"assignments": assignments,
	}})


@app.post("/admin/login")
async def admin_login(request: Request, password: str = Form(...)):
	if password != ADMIN_PASSWORD:
		return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})
	response = RedirectResponse(url="/admin", status_code=302)
	response.set_cookie("admin_auth", ADMIN_PASSWORD, httponly=True)
	return response


@app.get("/admin/logout")
async def admin_logout(request: Request):
	response = RedirectResponse(url="/admin", status_code=302)
	response.delete_cookie("admin_auth")
	return response


@app.get("/")
async def root():
	return {"status": "ok", "message": "Secret Santa Admin Panel API"}


@app.get("/stats")
async def get_stats():
	"""Get overall statistics."""
	logger.info("API request: GET /stats")
	async_session = get_session()
	async with async_session as session:
		total_users = len((await session.execute(select(User))).scalars().all())
		route1_entries = len((await session.execute(select(Route1Entry))).scalars().all())
		route2_entries = len((await session.execute(select(Route2Entry))).scalars().all())
		assignments = len((await session.execute(select(Assignment))).scalars().all())

	logger.debug(f"Stats: users={total_users}, route1={route1_entries}, route2={route2_entries}, assignments={assignments}")
	return {
		"total_users": total_users,
		"route1_entries": route1_entries,
		"route2_entries": route2_entries,
		"assignments": assignments,
	}


@app.get("/users")
async def get_users(skip: int = 0, limit: int = 100) -> list[UserResponse]:
	"""Get list of users."""
	logger.info(f"API request: GET /users (skip={skip}, limit={limit})")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User).offset(skip).limit(limit))
		users = result.scalars().all()
		logger.debug(f"Returned {len(users)} users")
		return users


@app.get("/admin/users")
async def ui_users(request: Request):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User))
		users = result.scalars().all()
	# load admin ids from DB-backed settings if present
	settings = await load_settings_async()
	admin_ids = settings.get('admin_ids') or []
	return templates.TemplateResponse("list_users.html", {"request": request, "users": users, "admin_ids": admin_ids})


@app.get("/admin/users/{user_id}/edit")
async def ui_edit_user(request: Request, user_id: int):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User).where(User.id == user_id))
		user = result.scalar_one_or_none()
		if not user:
			return RedirectResponse(url="/admin/users")
	return templates.TemplateResponse("edit_user.html", {"request": request, "user": user})


@app.post("/admin/users/{user_id}/edit")
async def ui_edit_user_post(request: Request, user_id: int, phone: str | None = Form(None)):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User).where(User.id == user_id))
		user = result.scalar_one_or_none()
		if not user:
			return RedirectResponse(url="/admin/users")
		user.phone = phone or None
		await session.commit()
	return RedirectResponse(url="/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/delete")
async def ui_delete_user(request: Request, user_id: int):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User).where(User.id == user_id))
		user = result.scalar_one_or_none()
		if user:
			# Find assignments where this user is giver or receiver
			result = await session.execute(
				select(Assignment).where((Assignment.giver_user_id == user_id) | (Assignment.receiver_user_id == user_id))
			)
			assignments = result.scalars().all()
			for a in assignments:
				# determine counterpart
				other_id = a.receiver_user_id if a.giver_user_id == user_id else a.giver_user_id
				# create notification log for the counterpart so admins or system can notify them
				payload = f"Assignment {a.id} for route {a.route_type} became invalid because user {user_id} was deleted."
				notif = NotificationLog(user_id=other_id, channel="telegram", notif_type="assignment_orphaned", payload=payload, status="pending")
				session.add(notif)
				# delete the assignment
				await session.delete(a)
				logger.info(f"Admin removed assignment {a.id} because user {user_id} was deleted")

			# remove any route entries belonging to the user
			result = await session.execute(select(Route1Entry).where(Route1Entry.user_id == user_id))
			r1_entries = result.scalars().all()
			for e in r1_entries:
				await session.delete(e)
				logger.info(f"Deleted Route1Entry {e.id} for removed user {user_id}")

			result = await session.execute(select(Route2Entry).where(Route2Entry.user_id == user_id))
			r2_entries = result.scalars().all()
			for e in r2_entries:
				await session.delete(e)
				logger.info(f"Deleted Route2Entry {e.id} for removed user {user_id}")

			# finally delete the user
			await session.delete(user)
			await session.commit()
			logger.info(f"Admin deleted user {user_id} and cleaned related assignments/entries")
	return RedirectResponse(url="/admin/users", status_code=302)


def _update_env_admin_ids(admin_ids: list[int]):
	"""Update local .env file's ADMIN_IDS line (best-effort)."""
	# project root /.env
	env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
	try:
		if os.path.exists(env_path):
			with open(env_path, 'r', encoding='utf-8') as f:
				lines = f.readlines()
			found = False
			new_line = f"ADMIN_IDS={','.join(str(x) for x in admin_ids)}\n"
			for i, l in enumerate(lines):
				if l.strip().startswith('ADMIN_IDS='):
					lines[i] = new_line
					found = True
					break
			if not found:
				lines.append(new_line)
			with open(env_path, 'w', encoding='utf-8') as f:
				f.writelines(lines)
	except Exception:
		# best-effort only; ignore failures
		pass


@app.post("/admin/users/{user_id}/make_admin")
async def ui_make_admin(request: Request, user_id: int):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User).where(User.id == user_id))
		user = result.scalar_one_or_none()
		if not user or not getattr(user, 'telegram_id', None):
			return RedirectResponse(url="/admin/users", status_code=302)

		# load or create Setting row
		result = await session.execute(select(Setting).where(Setting.key == 'admin_ids'))
		rec = result.scalar_one_or_none()
		if rec and isinstance(rec.value, list):
			ids = [int(x) for x in rec.value]
		else:
			ids = []

		if int(user.telegram_id) not in ids:
			ids.append(int(user.telegram_id))
		# persist
		if rec:
			rec.value = ids
			session.add(rec)
		else:
			session.add(Setting(key='admin_ids', value=ids))
		await session.commit()

	# also update local .env for convenience
	_update_env_admin_ids(ids)
	return RedirectResponse(url="/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/remove_admin")
async def ui_remove_admin(request: Request, user_id: int):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User).where(User.id == user_id))
		user = result.scalar_one_or_none()
		if not user or not getattr(user, 'telegram_id', None):
			return RedirectResponse(url="/admin/users", status_code=302)

		result = await session.execute(select(Setting).where(Setting.key == 'admin_ids'))
		rec = result.scalar_one_or_none()
		if rec and isinstance(rec.value, list):
			ids = [int(x) for x in rec.value]
		else:
			ids = []

		if int(user.telegram_id) in ids:
			ids = [x for x in ids if x != int(user.telegram_id)]
		if rec:
			rec.value = ids
			session.add(rec)
			await session.commit()

	_update_env_admin_ids(ids)
	return RedirectResponse(url="/admin/users", status_code=302)


@app.get("/users/{user_id}")
async def get_user(user_id: int) -> UserResponse:
	"""Get a specific user by ID."""
	logger.info(f"API request: GET /users/{user_id}")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User).where(User.id == user_id))
		user = result.scalar_one_or_none()
		if not user:
			logger.warning(f"User {user_id} not found")
			raise HTTPException(status_code=404, detail="User not found")
		logger.debug(f"Found user {user_id}: {user.telegram_id}")
		return user


@app.get("/route1")
async def get_route1_entries(skip: int = 0, limit: int = 100) -> list[Route1EntryResponse]:
	"""Get all route1 entries."""
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route1Entry).offset(skip).limit(limit))
		return result.scalars().all()


@app.get("/admin/route1")
async def ui_route1(request: Request):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route1Entry))
		entries = result.scalars().all()
		# preload users for mapping usernames
		user_ids = [e.user_id for e in entries]
		users = {}
		if user_ids:
			result = await session.execute(select(User).where(User.id.in_(user_ids)))
			for u in result.scalars().all():
				users[u.id] = u
	return templates.TemplateResponse("list_route1.html", {"request": request, "entries": entries, "users": users})


@app.get("/admin/settings")
async def ui_settings(request: Request):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	settings = await load_settings_async()
	return templates.TemplateResponse("edit_settings.html", {"request": request, "settings": settings})


@app.post("/admin/settings")
async def ui_settings_post(
	request: Request,
	assignment_reminder_hours: int = Form(48),
	registration_reminder_hours: int = Form(24),
	assignment_reminder_max: int = Form(3),
	reminder_enabled: str | None = Form(None),
	reminder_check_interval_minutes: int = Form(60),
	assignment_reminder_minutes: str | None = Form(None),
	registration_reminder_minutes: str | None = Form(None),
):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	
	# Валидация входных данных
	try:
		assignment_reminder_hours = int(assignment_reminder_hours)
		registration_reminder_hours = int(registration_reminder_hours)
		assignment_reminder_max = int(assignment_reminder_max)
		reminder_check_interval_minutes = int(reminder_check_interval_minutes)
		# optional minute overrides (can be blank)
		import re
		def norm_minutes(val):
			if val in (None, '', 'None'):
				return None
			# strip non-digits (handles inputs like '"30"' or '\\"30\\"')
			if isinstance(val, str):
				clean = re.sub(r'[^0-9]', '', val)
				if clean == '':
					return None
					return int(clean)
			# fallback
			return int(val)
		assignment_reminder_minutes = norm_minutes(assignment_reminder_minutes)
		registration_reminder_minutes = norm_minutes(registration_reminder_minutes)
		
		# Проверка диапазонов
		if not (1 <= assignment_reminder_hours <= 720):  # 1 час - 30 дней
			raise ValueError("Интервал напоминаний о назначении должен быть между 1 и 720 часами")
		if not (1 <= registration_reminder_hours <= 720):  # 1 час - 30 дней
			raise ValueError("Интервал напоминаний о регистрации должен быть между 1 и 720 часами")
		# if not (1 <= assignment_reminder_max <= 10):
		if not (1 <= assignment_reminder_max <= 999):
			raise ValueError("Максимум напоминаний должен быть между 1 и 999")
		if not (1 <= reminder_check_interval_minutes <= 1440):
			raise ValueError("Интервал проверки напоминаний должен быть между 1 и 1440 минут (1 день)")
		if assignment_reminder_minutes is not None and not (1 <= assignment_reminder_minutes <= 60*24):
			raise ValueError("Интервал напоминаний о назначении в минутах должен быть между 1 и 1440")
		if registration_reminder_minutes is not None and not (1 <= registration_reminder_minutes <= 60*24):
			raise ValueError("Интервал напоминаний о регистрации в минутах должен быть между 1 и 1440")
	except (ValueError, TypeError) as e:
		logger.warning(f"Invalid settings input: {e}")
		# Возвращаем с ошибкой
		settings = await load_settings_async()
		return templates.TemplateResponse(
			"edit_settings.html",
			{
				"request": request,
				"settings": settings,
				"error": str(e)
			},
			status_code=400
		)
	
	# Загружаем текущие настройки
	settings = await load_settings_async()
	
	# Обновляем значения
	old_settings = settings.copy()
	settings['assignment_reminder_hours'] = assignment_reminder_hours
	settings['registration_reminder_hours'] = registration_reminder_hours
	settings['assignment_reminder_max'] = assignment_reminder_max
	settings['reminder_enabled'] = bool(reminder_enabled)
	settings['assignment_reminder_minutes'] = assignment_reminder_minutes
	settings['registration_reminder_minutes'] = registration_reminder_minutes
	settings['reminder_check_interval_minutes'] = reminder_check_interval_minutes
	
	# Сохраняем в JSON для обратной совместимости
	save_settings(settings)
	
	# Сохраняем в БД асинхронно
	try:
		await save_settings_to_db(settings)
		logger.info(f"Settings updated successfully: {settings}")
	except Exception as e:
		logger.exception("Failed to save settings to DB; falling back to JSON only")
	
	return RedirectResponse(url="/admin/settings", status_code=302)


@app.get("/admin/route1/{entry_id}/edit")
async def ui_edit_route1(request: Request, entry_id: int):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route1Entry).where(Route1Entry.id == entry_id))
		entry = result.scalar_one_or_none()
		if not entry:
			return RedirectResponse(url="/admin/route1")
		result = await session.execute(select(User).where(User.id == entry.user_id))
		user = result.scalar_one_or_none()
	return templates.TemplateResponse("edit_route1.html", {"request": request, "entry": entry, "user": user})


@app.post("/admin/route1/{entry_id}/edit")
async def ui_edit_route1_post(
    request: Request,
    entry_id: int,
    email: str = Form(...),
    wishlist: str = Form(...),
    phone: str | None = Form(None),
    # Postal fields
    postal_city: str | None = Form(None),
    postal_street: str | None = Form(None),
    postal_building: str | None = Form(None),
    postal_corpus: str | None = Form(None),
    postal_apartment: str | None = Form(None),
    postal_recipient_fullname: str | None = Form(None),
    postal_recipient_phone: str | None = Form(None),
    # Pickup fields
    pickup_company: str | None = Form(None),
    pickup_address: str | None = Form(None),
    pickup_recipient_fullname: str | None = Form(None),
    pickup_recipient_phone: str | None = Form(None),
):
    if not is_admin_ui(request):
        return RedirectResponse(url="/admin")
    async_session = get_session()
    async with async_session as session:
        result = await session.execute(select(Route1Entry).where(Route1Entry.id == entry_id))
        entry = result.scalar_one_or_none()
        if not entry:
            return RedirectResponse(url="/admin/route1")
        entry.email = email
        entry.wishlist = wishlist
        
        # Update postal fields if pickup_type is postal
        if entry.pickup_type == 'postal':
            entry.postal_city = postal_city
            entry.postal_street = postal_street
            entry.postal_building = postal_building
            entry.postal_corpus = postal_corpus or None
            entry.postal_apartment = postal_apartment or None
            entry.postal_recipient_fullname = postal_recipient_fullname
            entry.postal_recipient_phone = postal_recipient_phone
        
        # Update pickup fields if pickup_type is pickup
        elif entry.pickup_type == 'pickup':
            entry.pickup_company = pickup_company
            entry.pickup_address = pickup_address
            entry.pickup_recipient_fullname = pickup_recipient_fullname
            entry.pickup_recipient_phone = pickup_recipient_phone
        
        # Update user phone if provided
        result = await session.execute(select(User).where(User.id == entry.user_id))
        user = result.scalar_one_or_none()
        if user and phone is not None:
            user.phone = phone or None
        await session.commit()
        logger.info(f"Admin updated route1 entry {entry_id}")
    return RedirectResponse(url="/admin/route1", status_code=302)
@app.post("/admin/route1/{entry_id}/delete")
async def ui_delete_route1(request: Request, entry_id: int):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route1Entry).where(Route1Entry.id == entry_id))
		entry = result.scalar_one_or_none()
		if entry:
			await session.delete(entry)
			await session.commit()
			logger.info(f"Admin deleted route1 entry {entry_id}")
	return RedirectResponse(url="/admin/route1", status_code=302)


@app.get("/route1/{entry_id}")
async def get_route1_entry(entry_id: int) -> Route1EntryResponse:
	"""Get a specific route1 entry."""
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route1Entry).where(Route1Entry.id == entry_id))
		entry = result.scalar_one_or_none()
		if not entry:
			raise HTTPException(status_code=404, detail="Entry not found")
		return entry


@app.patch("/route1/{entry_id}")
async def update_route1_entry(entry_id: int, status: str | None = None, email: str | None = None, full_address: str | None = None) -> Route1EntryResponse:
	"""Update a route1 entry."""
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route1Entry).where(Route1Entry.id == entry_id))
		entry = result.scalar_one_or_none()
		if not entry:
			raise HTTPException(status_code=404, detail="Entry not found")

		if status:
			entry.status = status
		if email:
			entry.email = email
		if full_address:
			entry.full_address = full_address

		await session.commit()
		await session.refresh(entry)
		return entry


@app.get("/route2")
async def get_route2_entries(skip: int = 0, limit: int = 100) -> list[Route2EntryResponse]:
	"""Get all route2 entries."""
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route2Entry).offset(skip).limit(limit))
		return result.scalars().all()


@app.get("/admin/route2")
async def ui_route2(request: Request):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route2Entry))
		entries = result.scalars().all()
		user_ids = [e.user_id for e in entries]
		users = {}
		if user_ids:
			result = await session.execute(select(User).where(User.id.in_(user_ids)))
			for u in result.scalars().all():
				users[u.id] = u
	return templates.TemplateResponse("list_route2.html", {"request": request, "entries": entries, "users": users})


@app.get("/admin/route2/{entry_id}/edit")
async def ui_edit_route2(request: Request, entry_id: int):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route2Entry).where(Route2Entry.id == entry_id))
		entry = result.scalar_one_or_none()
		if not entry:
			return RedirectResponse(url="/admin/route2")
		result = await session.execute(select(User).where(User.id == entry.user_id))
		user = result.scalar_one_or_none()
	return templates.TemplateResponse("edit_route2.html", {"request": request, "entry": entry, "user": user})


@app.post("/admin/route2/{entry_id}/edit")
async def ui_edit_route2_post(request: Request, entry_id: int, email: str = Form(...), phone: str | None = Form(None)):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route2Entry).where(Route2Entry.id == entry_id))
		entry = result.scalar_one_or_none()
		if not entry:
			return RedirectResponse(url="/admin/route2")
		entry.email = email
		result = await session.execute(select(User).where(User.id == entry.user_id))
		user = result.scalar_one_or_none()
		if user and phone is not None:
			user.phone = phone or None
		await session.commit()
	return RedirectResponse(url="/admin/route2", status_code=302)


@app.post("/admin/route2/{entry_id}/delete")
async def ui_delete_route2(request: Request, entry_id: int):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route2Entry).where(Route2Entry.id == entry_id))
		entry = result.scalar_one_or_none()
		if entry:
			await session.delete(entry)
			await session.commit()
			logger.info(f"Admin deleted route2 entry {entry_id}")
	return RedirectResponse(url="/admin/route2", status_code=302)


@app.get("/route2/{entry_id}")
async def get_route2_entry(entry_id: int) -> Route2EntryResponse:
	"""Get a specific route2 entry."""
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route2Entry).where(Route2Entry.id == entry_id))
		entry = result.scalar_one_or_none()
		if not entry:
			raise HTTPException(status_code=404, detail="Entry not found")
		return entry


@app.patch("/route2/{entry_id}")
async def update_route2_entry(entry_id: int, status: str | None = None, email: str | None = None) -> Route2EntryResponse:
	"""Update a route2 entry."""
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route2Entry).where(Route2Entry.id == entry_id))
		entry = result.scalar_one_or_none()
		if not entry:
			raise HTTPException(status_code=404, detail="Entry not found")

		if status:
			entry.status = status
		if email:
			entry.email = email

		await session.commit()
		await session.refresh(entry)
		return entry


@app.get("/assignments")
async def get_assignments(route_type: int | None = None, skip: int = 0, limit: int = 100) -> list[AssignmentResponse]:
	"""Get assignments, optionally filtered by route."""
	async_session = get_session()
	async with async_session as session:
		if route_type:
			result = await session.execute(
				select(Assignment).where(Assignment.route_type == route_type).offset(skip).limit(limit)
			)
		else:
			result = await session.execute(select(Assignment).offset(skip).limit(limit))
		return result.scalars().all()


@app.get("/admin/assignments")
async def ui_assignments(request: Request):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Assignment))
		assignments = result.scalars().all()
		# preload users for display
		user_ids = set()
		for a in assignments:
			user_ids.add(a.giver_user_id)
			user_ids.add(a.receiver_user_id)
		users = {}
		if user_ids:
			result = await session.execute(select(User).where(User.id.in_(list(user_ids))))
			for u in result.scalars().all():
				users[u.id] = u
	return templates.TemplateResponse("list_assignments.html", {"request": request, "assignments": assignments, "users": users})


@app.post("/admin/assignments/{assignment_id}/mark")
async def ui_mark_assignment(request: Request, assignment_id: int, sent_status: str = Form(...)):
	if not is_admin_ui(request):
		return RedirectResponse(url="/admin")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Assignment).where(Assignment.id == assignment_id))
		assignment = result.scalar_one_or_none()
		if assignment:
			assignment.sent_status = sent_status
			await session.commit()
			logger.info(f"Admin marked assignment {assignment_id} as {sent_status}")
	return RedirectResponse(url="/admin/assignments", status_code=302)


@app.patch("/assignments/{assignment_id}")
async def update_assignment(assignment_id: int, sent_status: str | None = None) -> AssignmentResponse:
	"""Update an assignment status."""
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Assignment).where(Assignment.id == assignment_id))
		assignment = result.scalar_one_or_none()
		if not assignment:
			raise HTTPException(status_code=404, detail="Assignment not found")

		if sent_status:
			assignment.sent_status = sent_status

		await session.commit()
		await session.refresh(assignment)
		return assignment


@app.post("/draw/{route_type}")
async def draw_route(route_type: int):
	"""Trigger draw for a route."""
	if route_type not in [1, 2]:
		logger.warning(f"API request: POST /draw/{route_type} - invalid route_type")
		raise HTTPException(status_code=400, detail="route_type must be 1 or 2")

	logger.info(f"API request: POST /draw/{route_type}")
	success, msg, count = await perform_draw(route_type)
	if not success:
		logger.error(f"Draw route{route_type} failed: {msg}")
		raise HTTPException(status_code=400, detail=msg)

	logger.info(f"Draw route{route_type} successful: {count} assignments created")
	return {"success": True, "message": msg, "assignments_count": count}


@app.get("/export/route1")
async def export_route1():
	"""Export route1 data as CSV."""
	logger.info("API request: GET /export/route1")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route1Entry))
		entries = result.scalars().all()

	logger.debug(f"Exporting {len(entries)} route1 entries")
	output = io.StringIO()
	writer = csv.writer(output)
	writer.writerow(['ID', 'Telegram ID', 'Telegram Username', 'Email', 'Адрес', 'Способ доставки', 'Пожелания/Анкета', 'Статус'])

	for entry in entries:
		async with async_session as session:
			result = await session.execute(select(User).where(User.id == entry.user_id))
			user = result.scalar_one_or_none()

		writer.writerow([
			entry.id,
			user.telegram_id if user else '',
			user.telegram_username if user else '',
			entry.email,
			entry.full_address,
			entry.delivery_method or '',
			entry.survey or entry.wishlist or '',
			entry.status
		])

	csv_bytes = output.getvalue().encode('utf-8-sig')
	return StreamingResponse(
		iter([csv_bytes]),
		media_type="text/csv",
		headers={"Content-Disposition": "attachment; filename=route1_export.csv"}
	)


@app.get("/export/route2")
async def export_route2():
	"""Export route2 data as CSV."""
	logger.info("API request: GET /export/route2")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route2Entry))
		entries = result.scalars().all()

	logger.debug(f"Exporting {len(entries)} route2 entries")
	output = io.StringIO()
	writer = csv.writer(output)
	writer.writerow(['ID', 'Telegram ID', 'Telegram Username', 'Email', 'Статус'])

	for entry in entries:
		async with async_session as session:
			result = await session.execute(select(User).where(User.id == entry.user_id))
			user = result.scalar_one_or_none()

		writer.writerow([
			entry.id,
			user.telegram_id if user else '',
			user.telegram_username if user else '',
			entry.email,
			entry.status
		])

	csv_bytes = output.getvalue().encode('utf-8-sig')
	return StreamingResponse(
		iter([csv_bytes]),
		media_type="text/csv",
		headers={"Content-Disposition": "attachment; filename=route2_export.csv"}
	)


@app.on_event("startup")
async def startup_event():
	"""Initialize database on startup."""
	logger.info("FastAPI admin panel starting up")
	await init_db()
	logger.info("Database initialized")

