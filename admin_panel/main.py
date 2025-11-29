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
from bot.db.models import User, Route1Entry, Route2Entry, Assignment, NotificationLog
from bot.randomizer import perform_draw
from bot.logger import get_logger

logger = get_logger("admin_panel")
app = FastAPI(title="Secret Santa Admin Panel", version="1.0.0")

# Templates and static
templates = Jinja2Templates(directory="admin_panel/templates")
app.mount("/static", StaticFiles(directory="admin_panel/static"), name="static")

# Simple admin UI auth (password from env)
import os
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")


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
	full_address: str
	delivery_method: str | None
	wishlist: str | None
	status: str
	started_at: datetime
	completed_at: datetime | None

	class Config:
		from_attributes = True


class Route2EntryResponse(BaseModel):
	id: int
	user_id: int
	email: str
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
	return templates.TemplateResponse("list_users.html", {"request": request, "users": users})


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
	return templates.TemplateResponse("list_route1.html", {"request": request, "entries": entries})


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
async def ui_edit_route1_post(request: Request, entry_id: int, email: str = Form(...), full_address: str = Form(...), wishlist: str = Form(...), phone: str | None = Form(None)):
    if not is_admin_ui(request):
        return RedirectResponse(url="/admin")
    async_session = get_session()
    async with async_session as session:
        result = await session.execute(select(Route1Entry).where(Route1Entry.id == entry_id))
        entry = result.scalar_one_or_none()
        if not entry:
            return RedirectResponse(url="/admin/route1")
        entry.email = email
        entry.full_address = full_address
        entry.wishlist = wishlist
        # update user phone if provided
        result = await session.execute(select(User).where(User.id == entry.user_id))
        user = result.scalar_one_or_none()
        if user and phone is not None:
            user.phone = phone or None
        await session.commit()
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
	return templates.TemplateResponse("list_route2.html", {"request": request, "entries": entries})


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
	return templates.TemplateResponse("list_assignments.html", {"request": request, "assignments": assignments})


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
	writer.writerow(['ID', 'Telegram ID', 'Email', 'Адрес', 'Способ доставки', 'Пожелания', 'Статус'])

	for entry in entries:
		async with async_session as session:
			result = await session.execute(select(User).where(User.id == entry.user_id))
			user = result.scalar_one_or_none()

		writer.writerow([
			entry.id,
			user.telegram_id if user else '',
			entry.email,
			entry.full_address,
			entry.delivery_method or '',
			entry.wishlist or '',
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
	writer.writerow(['ID', 'Telegram ID', 'Email', 'Статус'])

	for entry in entries:
		async with async_session as session:
			result = await session.execute(select(User).where(User.id == entry.user_id))
			user = result.scalar_one_or_none()

		writer.writerow([
			entry.id,
			user.telegram_id if user else '',
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

