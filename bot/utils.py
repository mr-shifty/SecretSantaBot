"""Utility helpers for interacting with DB and validating input."""
import re
from typing import Optional
from datetime import datetime
from sqlalchemy import select
from bot.db.models import User, Route1Entry, Route2Entry
from bot.db.database import get_session
from bot.logger import get_logger

logger = get_logger("utils")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def is_valid_email(email: str) -> bool:
	return bool(EMAIL_RE.match(email))

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
	phone: str | None = None,
	pickup_type: str | None = None,
	# Postal fields
	postal_city: str | None = None,
	postal_street: str | None = None,
	postal_building: str | None = None,
	postal_corpus: str | None = None,
	postal_apartment: str | None = None,
	postal_recipient_fullname: str | None = None,
	postal_recipient_phone: str | None = None,
	postal_telegram: str | None = None,
	# Pickup fields
	pickup_company: str | None = None,
	pickup_address: str | None = None,
	pickup_recipient_fullname: str | None = None,
	pickup_recipient_phone: str | None = None,
	# Legacy fields
	full_address: str | None = None,
	delivery_method: str | None = None,
):
	async_session = get_session()
	async with async_session as session:
		entry = Route1Entry(
			user_id=user_id,
			email=email,
			wishlist=wishlist,
			status="completed",
			pickup_type=pickup_type,
			postal_city=postal_city,
			postal_street=postal_street,
			postal_building=postal_building,
			postal_corpus=postal_corpus,
			postal_apartment=postal_apartment,
			postal_recipient_fullname=postal_recipient_fullname,
			postal_recipient_phone=postal_recipient_phone,
			pickup_company=pickup_company,
			pickup_address=pickup_address,
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
			result = await session.execute(select(User).where(User.id == user_id))
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
	async_session = get_session()
	async with async_session as session:
		entry = Route2Entry(
			user_id=user_id,
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
			result = await session.execute(select(User).where(User.id == user_id))
			user = result.scalar_one_or_none()
			if user:
				user.phone = phone or None
				await session.commit()
				logger.info(f"Updated phone for user {user_id} via route2 registration")
		return entry


async def check_active_route1_entry(user_id: int) -> bool:
	"""Check if user already has an active route1 entry."""
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(
			select(Route1Entry).where(
				Route1Entry.user_id == user_id
			).where(Route1Entry.status == "completed")
		)
		return result.scalar_one_or_none() is not None


async def check_active_route2_entry(user_id: int) -> bool:
	"""Check if user already has an active route2 entry."""
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(
			select(Route2Entry).where(
				Route2Entry.user_id == user_id
			).where(Route2Entry.status == "completed")
		)
		return result.scalar_one_or_none() is not None
