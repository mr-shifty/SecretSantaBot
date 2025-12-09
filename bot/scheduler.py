"""Scheduler for reminders and deadline handling using APScheduler."""
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from bot.db.models import Route1Entry, Route2Entry, Assignment, NotificationLog, User
from bot.db.database import get_session
from bot.randomizer import perform_draw
from bot.logger import get_logger
from admin_panel.main import load_settings_async
from datetime import timezone
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = get_logger("scheduler")


scheduler = AsyncIOScheduler()


async def send_reminder_to_user(user_id: int, message_text: str):
	"""Send a reminder notification (placeholder for actual send logic)."""
	async_session = get_session()
	async with async_session as session:
		log = NotificationLog(
			user_id=user_id,
			channel="telegram",
			notif_type="reminder",
			payload=message_text,
			status="pending",
		)
		session.add(log)
		await session.commit()


async def check_reminders():
	"""Check and send reminders to users 2 days before deadline (stub)."""
	# This would be called periodically. For now, it's a placeholder.
	pass


async def send_assignment_reminders(bot=None):
	"""Send periodic reminders to givers who haven't marked their assignment as sent."""
	logger.info("Running send_assignment_reminders")
	settings = await load_settings_async()
	hours = settings.get('assignment_reminder_hours', 48)
	enabled = settings.get('reminder_enabled', True)
	if not enabled:
		logger.debug('Reminders disabled in settings')
		return

	cutoff = datetime.utcnow() - timedelta(hours=hours)
	async_session = get_session()
	async with async_session as session:
		# find assignments not sent
		result = await session.execute(select(Assignment).where(Assignment.sent_status != 'sent'))
		assignments = result.scalars().all()

		# group by giver
		by_giver = {}
		for a in assignments:
			if a.assigned_at and a.assigned_at <= cutoff:
				by_giver.setdefault(a.giver_user_id, []).append(a)

		for giver_id, lst in by_giver.items():
			result = await session.execute(select(User).where(User.id == giver_id))
			giver = result.scalar_one_or_none()
			if not giver or not giver.telegram_id:
				continue

			# check last reminder for this giver: if we already sent reminder within hours, skip
			result = await session.execute(select(NotificationLog).where(NotificationLog.user_id == giver.id).where(NotificationLog.notif_type == 'assignment_reminder').order_by(NotificationLog.sent_at.desc()))
			last = result.scalars().first()
			if last and last.sent_at and last.sent_at > (datetime.utcnow() - timedelta(hours=hours)):
				continue
			# Respect maximum number of reminders sent overall
			max_reminders = settings.get('assignment_reminder_max', 3)
			result = await session.execute(select(NotificationLog).where(NotificationLog.user_id == giver.id).where(NotificationLog.notif_type == 'assignment_reminder').where(NotificationLog.status == 'sent'))
			sent_count_for_giver = len(result.scalars().all())
			if sent_count_for_giver >= max_reminders:
				logger.info(f"Giver {giver.id} reached max reminders ({sent_count_for_giver} >= {max_reminders}), skipping")
				continue

			# build message combining all their pending assignments
			parts = []
			buttons = []
			nlogs = []
			for a in lst:
				# get receiver name
				result = await session.execute(select(User).where(User.id == a.receiver_user_id))
				receiver = result.scalar_one_or_none()
				recv_name = (('@' + receiver.telegram_username) if receiver and receiver.telegram_username else (receiver.first_name or 'Получатель'))
				# minimal info
				parts.append(f"Маршрут {a.route_type} — Для: {recv_name}")
				buttons.append(InlineKeyboardButton(text=( 'Поздравление отправлено' if a.route_type==2 else 'Подарок отправлен'), callback_data=f"mark_sent:{a.id}"))
				nl = NotificationLog(user_id=giver.id, channel='telegram', notif_type='assignment_reminder', payload=None, status='pending')
				session.add(nl)
				nlogs.append(nl)

			text = "Напоминание: вы ещё не отметили отправку для следующих назначений:\n\n" + "\n".join(parts)
			# inline keyboard
			ikb = InlineKeyboardMarkup(inline_keyboard=[[b] for b in buttons])
			# update payloads for logs
			for nl in nlogs:
				nl.payload = text
				session.add(nl)
			await session.commit()
			try:
				await bot.send_message(chat_id=giver.telegram_id, text=text, reply_markup=ikb)
				for nl in nlogs:
					nl.status = 'sent'
					nl.sent_at = datetime.utcnow()
					session.add(nl)
				await session.commit()
			except Exception as exc:
				logger.exception(f"Failed to send assignment reminder to {giver_id}: {exc}")
				for nl in nlogs:
					nl.status = 'failed'
					session.add(nl)
				await session.commit()


async def send_registration_reminders(bot=None):
	"""Send reminders to users who started registration but didn't complete."""
	logger.info("Running send_registration_reminders")
	settings = await load_settings_async()
	hours = settings.get('registration_reminder_hours', 24)
	enabled = settings.get('reminder_enabled', True)
	if not enabled:
		logger.debug('Reminders disabled in settings')
		return

	cutoff = datetime.utcnow() - timedelta(hours=hours)
	async_session = get_session()
	async with async_session as session:
		# Find route1 pending entries
		result = await session.execute(select(Route1Entry).where(Route1Entry.status != 'completed').where(Route1Entry.started_at <= cutoff))
		r1_entries = result.scalars().all()
		# route2
		result = await session.execute(select(Route2Entry).where(Route2Entry.status != 'completed').where(Route2Entry.started_at <= cutoff))
		r2_entries = result.scalars().all()

		# send reminders individually
		for e in r1_entries + r2_entries:
			result = await session.execute(select(User).where(User.id == e.user_id))
			user = result.scalar_one_or_none()
			if not user or not user.telegram_id:
				continue
			# check last registration reminder
			result = await session.execute(select(NotificationLog).where(NotificationLog.user_id == user.id).where(NotificationLog.notif_type == 'registration_reminder').order_by(NotificationLog.sent_at.desc()))
			last = result.scalars().first()
			if last and last.sent_at and last.sent_at > (datetime.utcnow() - timedelta(hours=hours)):
				continue

			text = 'Напоминание: пожалуйста, завершите вашу регистрацию. Отправьте /start в боте и выберите нужный маршрут.'
			nlog = NotificationLog(user_id=user.id, channel='telegram', notif_type='registration_reminder', payload=text, status='pending')
			session.add(nlog)
			await session.commit()
			try:
				await bot.send_message(chat_id=user.telegram_id, text=text)
				nlog.status = 'sent'
				nlog.sent_at = datetime.utcnow()
			except Exception:
				nlog.status = 'failed'
			session.add(nlog)
			await session.commit()


async def check_and_cancel_unpaid():
	"""Auto-cancel assignments that haven't been marked as sent after 7 days."""
	logger.info("Running check_and_cancel_unpaid task")
	async_session = get_session()
	async with async_session as session:
		deadline = datetime.utcnow() - timedelta(days=7)
		
		# Find assignments that are still pending and older than 7 days
		result = await session.execute(
			select(Assignment).where(
				Assignment.assigned_at < deadline
			).where(Assignment.sent_status == "pending")
		)
		old_assignments = result.scalars().all()
		
		if old_assignments:
			logger.warning(f"Found {len(old_assignments)} unpaid assignments older than 7 days")
		
		cancelled_routes = {1: [], 2: []}
		
		for assignment in old_assignments:
			# Mark as failed
			assignment.sent_status = "failed"
			await session.commit()
			cancelled_routes[assignment.route_type].append(assignment.id)
		
		# Re-run draw for affected routes
		for route_type in [1, 2]:
			if cancelled_routes[route_type]:
				logger.info(f"Re-running draw for route {route_type} due to {len(cancelled_routes[route_type])} failed assignments")
				success, msg, count = await perform_draw(route_type)


async def start_scheduler(bot=None):
	"""Start the async scheduler for background tasks."""
	if not scheduler.running:
		scheduler.add_job(
			check_and_cancel_unpaid,
			IntervalTrigger(hours=24),  # Run every 24 hours
			id="cancel_unpaid",
		)
		# assignment reminders job: run hourly and send reminders according to settings
		scheduler.add_job(
			send_assignment_reminders,
			IntervalTrigger(hours=1),
			id="assignment_reminders",
		)
		# registration reminders job: run hourly
		scheduler.add_job(
			send_registration_reminders,
			IntervalTrigger(hours=1),
			id="registration_reminders",
		)
		scheduler.start()
		logger.info("Background scheduler started")


def stop_scheduler():
	"""Stop the async scheduler."""
	if scheduler.running:
		scheduler.shutdown()
		logger.info("Background scheduler stopped")
