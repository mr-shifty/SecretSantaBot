"""Utility helpers for interacting with DB and validating input."""
import re
from typing import Optional
from datetime import datetime
from sqlalchemy import select
import json
from bot.db.models import User, Route1Entry, Route2Entry, Setting
from bot.db.database import get_session
from bot.logger import get_logger

logger = get_logger("utils")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def is_valid_email(email: str) -> bool:
	return bool(EMAIL_RE.match(email))


async def _resolve_internal_user_id(user_identifier: int) -> int | None:
	"""Resolve a provided identifier (could be internal `User.id` or `User.telegram_id`) to the internal `User.id`.
	Returns None if no user found.
	"""
	async_session = get_session()
	async with async_session as session:
		# First try as internal id
		result = await session.execute(select(User).where(User.id == user_identifier))
		user = result.scalar_one_or_none()
		if user:
			return user.id

		# Then try as telegram_id
		result = await session.execute(select(User).where(User.telegram_id == user_identifier))
		user = result.scalar_one_or_none()
		if user:
			return user.id

		return None

async def get_or_create_user(telegram_id: int, username: Optional[str] = None, first_name: Optional[str] = None, last_name: Optional[str] = None, phone: Optional[str] = None) -> User:
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User).where(User.telegram_id == telegram_id))
		user = result.scalar_one_or_none()
		if user:
			changed = False
			if username and user.telegram_username != username:
				user.telegram_username = username
				changed = True
			if first_name and user.first_name != first_name:
				user.first_name = first_name
				changed = True
			if last_name and user.last_name != last_name:
				user.last_name = last_name
				changed = True
			if phone is not None and user.phone != phone:
				user.phone = phone
				changed = True
			if changed:
				await session.commit()
				logger.info(f"Updated user {telegram_id}")
			return user

		user = User(
			telegram_id=telegram_id,
			telegram_username=username,
			first_name=first_name,
			last_name=last_name,
		)
		session.add(user)
		await session.commit()
		await session.refresh(user)
		logger.info(f"Created new user {telegram_id} (@{username})")
		return user

async def save_route1_entry(
	user_id: int,
	email: str,
	wishlist: str,
	survey: dict | None = None,
	phone: str | None = None,
	pickup_type: str | None = None,
	# Postal fields
	postal_city: str | None = None,
	postal_street: str | None = None,
	postal_building: str | None = None,
	postal_corpus: str | None = None,
	postal_apartment: str | None = None,
	postal_recipient_fullname: str | None = None,
	postal_recipient_last_name: str | None = None,
	postal_recipient_first_name: str | None = None,
	postal_recipient_patronymic: str | None = None,
	postal_index: str | None = None,
	postal_branch_number: str | None = None,
	postal_recipient_phone: str | None = None,
	postal_telegram: str | None = None,
	# Pickup fields
	pickup_company: str | None = None,
	pickup_address: str | None = None,
	pickup_recipient_fullname: str | None = None,
	pickup_recipient_phone: str | None = None,
	pickup_index: str | None = None,
	pickup_point_id: str | None = None,
	pickup_delivery_mode: str | None = None,
	# Legacy fields
	full_address: str | None = None,
	delivery_method: str | None = None,
):
	# Resolve user identifier to internal User.id (handlers may pass telegram_id)
	resolved_user_id = await _resolve_internal_user_id(user_id)
	if resolved_user_id is None:
		# As a fallback, still use given id (to not break existing callers), but log
		logger.warning(f"save_route1_entry: unable to resolve user {user_id} to internal id; storing as-is")
		resolved_user_id = user_id

	async_session = get_session()
	async with async_session as session:
		entry = Route1Entry(
			user_id=resolved_user_id,
			email=email,
			wishlist=wishlist,
			survey=json.dumps(survey) if survey is not None else None,
			status="completed",
			pickup_type=pickup_type,
			postal_city=postal_city,
			postal_street=postal_street,
			postal_building=postal_building,
			postal_corpus=postal_corpus,
			postal_apartment=postal_apartment,
			postal_recipient_fullname=postal_recipient_fullname or (
				f"{postal_recipient_last_name or ''} {postal_recipient_first_name or ''} {postal_recipient_patronymic or ''}".strip()
			),
			postal_recipient_last_name=postal_recipient_last_name,
			postal_recipient_first_name=postal_recipient_first_name,
			postal_recipient_patronymic=postal_recipient_patronymic,
			postal_index=postal_index,
			postal_branch_number=postal_branch_number,
			postal_recipient_phone=postal_recipient_phone,
			pickup_company=pickup_company,
			pickup_address=pickup_address,
			pickup_index=pickup_index,
			pickup_point_id=pickup_point_id,
			pickup_delivery_mode=pickup_delivery_mode,
			pickup_recipient_fullname=pickup_recipient_fullname,
			pickup_recipient_phone=pickup_recipient_phone,
			# Keep legacy fields for backward compatibility
			full_address=full_address,
			delivery_method=delivery_method,
		)
		session.add(entry)
		await session.commit()
		await session.refresh(entry)
		logger.info(f"Route1 entry created for user {user_id}: {email}, pickup_type={pickup_type}")
		# Optionally update user phone
		if phone is not None:
			result = await session.execute(select(User).where(User.id == resolved_user_id))
			user = result.scalar_one_or_none()
			if user:
				user.phone = phone or None
				await session.commit()
				logger.info(f"Updated phone for user {user_id} via route1 registration")
		return entry

async def save_route2_entry(
	user_id: int,
	email: str,
	phone: str | None = None,
	image_path: str | None = None,
	notify_date: datetime | None = None,
):
	# Resolve user identifier to internal User.id
	if resolved_user_id is None:
		logger.warning(f"save_route2_entry: unable to resolve user {user_id} to internal id; storing as-is")
		resolved_user_id = user_id

	async_session = get_session()
	async with async_session as session:
		entry = Route2Entry(
			user_id=resolved_user_id,
			email=email,
			status="completed",
			image_path=image_path,
			notify_date=notify_date,
		)
		session.add(entry)
		await session.commit()
		await session.refresh(entry)
		logger.info(f"Route2 entry created for user {user_id}: {email}")
		# Optionally update user phone
		if phone is not None:
			result = await session.execute(select(User).where(User.id == resolved_user_id))
			user = result.scalar_one_or_none()
			if user:
				user.phone = phone or None
				await session.commit()
				logger.info(f"Updated phone for user {user_id} via route2 registration")
		return entry


async def check_active_route1_entry(user_id: int) -> bool:
	"""Check if user already has an active route1 entry."""
	resolved_user_id = await _resolve_internal_user_id(user_id)
	if resolved_user_id is None:
		return False
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(
			select(Route1Entry).where(
				Route1Entry.user_id == resolved_user_id
			).where(Route1Entry.status == "completed")
		)
		return result.scalar_one_or_none() is not None


async def check_active_route2_entry(user_id: int) -> bool:
	"""Check if user already has an active route2 entry."""
	resolved_user_id = await _resolve_internal_user_id(user_id)
	if resolved_user_id is None:
		return False
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(
			select(Route2Entry).where(
				Route2Entry.user_id == resolved_user_id
			).where(Route2Entry.status == "completed")
		)
		return result.scalar_one_or_none() is not None


async def is_admin(user_identifier: int) -> bool:
	"""Return True if given identifier (telegram id or internal id) is an admin.

	Checks DB `settings` table key `admin_ids` (list) and falls back/merges with
	environment `ADMIN_IDS` from `bot.config`.
	"""
	from bot.config import ADMIN_IDS as ENV_ADMIN_IDS
	# Try DB stored admin ids
	async_session = get_session()
	db_ids: list[int] = []
	try:
		async with async_session as session:
			result = await session.execute(select(Setting).where(Setting.key == 'admin_ids'))
			rec = result.scalar_one_or_none()
			if rec and isinstance(rec.value, list):
				try:
					db_ids = [int(x) for x in rec.value]
				except Exception:
					db_ids = []
	except Exception:
		db_ids = []

	merged = set(ENV_ADMIN_IDS or []) | set(db_ids or [])
	try:
		return int(user_identifier) in merged
	except Exception:
		return False
