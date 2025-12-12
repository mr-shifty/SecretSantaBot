"""Scheduler for reminders and deadline handling using APScheduler."""
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, exists
from bot.db.models import Route1Entry, Route2Entry, Assignment, NotificationLog, User, Setting
from bot.db.database import get_session
from bot.randomizer import perform_draw
from bot.logger import get_logger
from admin_panel.main import load_settings_async
from datetime import timezone
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = get_logger("scheduler")


scheduler = AsyncIOScheduler()
# Keep track of current scheduled intervals (minutes) to avoid unnecessary reschedules
_current_reminder_check_interval = None
_last_manual_trigger_ts = None


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
	"""Send periodic reminders to givers who haven't marked their assignment as sent.

	Returns number of reminders successfully sent (notification log entries marked 'sent').
	"""
	logger.info("Running send_assignment_reminders")
	settings = await load_settings_async()
	# compute cutoff: prefer minute override if present
	min_override = settings.get('assignment_reminder_minutes')
	if min_override:
		hours = None
	else:
		hours = settings.get('assignment_reminder_hours', 48)
	enabled = settings.get('reminder_enabled', True)
	if not enabled:
		logger.debug('Reminders disabled in settings')
		return 0

	if min_override:
		cutoff = datetime.utcnow() - timedelta(minutes=int(min_override))
	else:
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

		total_sent = 0
		for giver_id, lst in by_giver.items():
			result = await session.execute(select(User).where(User.id == giver_id))
			giver = result.scalar_one_or_none()
			if not giver or not giver.telegram_id:
				continue

			# check last reminder for this giver: if we already sent reminder within configured window, skip
			result = await session.execute(
				select(NotificationLog)
				.where(NotificationLog.user_id == giver.id)
				.where(NotificationLog.notif_type == 'assignment_reminder')
				.order_by(NotificationLog.sent_at.desc())
			)
			last = result.scalars().first()
			# determine recent window: use minutes override if present, otherwise hours
			if last and last.sent_at:
				try:
					if min_override:
						recent_window = timedelta(minutes=int(min_override))
					else:
						recent_window = timedelta(hours=int(hours))
				except Exception:
					recent_window = None
				if recent_window and last.sent_at > (datetime.utcnow() - recent_window):
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
				route_label = 'Тайный Санта' if a.route_type == 1 else ('Диджитал Санта' if a.route_type == 2 else f'Маршрут {a.route_type}')
				parts.append(f"{route_label} — Для: {recv_name}")
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
				total_sent += len(nlogs)
			except Exception as exc:
				logger.exception(f"Failed to send assignment reminder to {giver_id}: {exc}")
				for nl in nlogs:
					nl.status = 'failed'
					session.add(nl)
				await session.commit()

		return total_sent


async def send_registration_reminders(bot=None, force: bool = False):
	"""Send reminders to users who started registration but didn't complete."""
	logger.info("Running send_registration_reminders")
	settings = await load_settings_async()
	min_override = settings.get('registration_reminder_minutes')
	hours = settings.get('registration_reminder_hours', 24)
	enabled = settings.get('reminder_enabled', True)
	if not enabled:
		logger.debug('Reminders disabled in settings')
		return 0

	# Determine the interval window to use: prefer minute override if present
	interval_minutes = min_override if min_override else (hours * 60 if hours else 24*60)
	interval_minutes = int(interval_minutes)
	
	logger.info(f"Registration reminders: min_override={min_override}, hours={hours}, using interval={interval_minutes} minutes")

	# compute cutoff (unless forced)
	if not force:
		cutoff = datetime.utcnow() - timedelta(minutes=interval_minutes)
	else:
		# when forced (manual trigger) we don't enforce a time cutoff — consider all users
		cutoff = None
	async_session = get_session()
	async with async_session as session:
		# Find route1 pending entries
		if cutoff is not None:
			result = await session.execute(select(Route1Entry).where(Route1Entry.status != 'completed').where(Route1Entry.started_at <= cutoff))
		else:
			result = await session.execute(select(Route1Entry).where(Route1Entry.status != 'completed'))
		r1_entries = result.scalars().all()
		logger.debug(f"Found {len(r1_entries)} pending route1 entries with started_at <= {cutoff}")
		# route2 pending entries
		if cutoff is not None:
			result = await session.execute(select(Route2Entry).where(Route2Entry.status != 'completed').where(Route2Entry.started_at <= cutoff))
		else:
			result = await session.execute(select(Route2Entry).where(Route2Entry.status != 'completed'))
		r2_entries = result.scalars().all()
		logger.debug(f"Found {len(r2_entries)} pending route2 entries with started_at <= {cutoff}")

		# Find users who have NO entries in either route
		# Users without any entries should get reminders regardless of when they were created
		# (they haven't started registration yet, so they're all candidates for reminder)
		q = select(User).where(~exists().where(Route1Entry.user_id == User.id)).where(~exists().where(Route2Entry.user_id == User.id))
		result = await session.execute(q)
		users_without_entries = result.scalars().all()
		logger.debug(f"Found {len(users_without_entries)} users without any route entries")

		# send reminders individually for both sets
		total_sent = 0
		candidates = []
		# build unified candidate list: users from pending entries
		for e in r1_entries + r2_entries:
			candidates.append((e.user_id, 'entry'))
		# and users with no entries
		for u in users_without_entries:
			candidates.append((u.id, 'no_entry'))

		# deduplicate by user id preserving order
		seen = set()
		unique_candidates = []
		for uid, kind in candidates:
			if uid in seen:
				continue
			seen.add(uid)
			unique_candidates.append(uid)

		for user_id in unique_candidates:
			result = await session.execute(select(User).where(User.id == user_id))
			user = result.scalar_one_or_none()
			if not user or not user.telegram_id:
				continue
			# check last registration reminder
			result = await session.execute(
				select(NotificationLog)
				.where(NotificationLog.user_id == user.id)
				.where(NotificationLog.notif_type == 'registration_reminder')
				.order_by(NotificationLog.sent_at.desc())
			)
			last = result.scalars().first()
			# Always check if we've sent a reminder recently (to respect the configured interval)
			if last and last.sent_at:
				# Use the same interval window as computed above
				recent_window = timedelta(minutes=interval_minutes)
				
				# If force=True (manual), ignore recent-window to allow immediate spam
				# If force=False (schedule), respect the window to avoid duplicate sends
				if not force and last.sent_at > (datetime.utcnow() - recent_window):
					logger.info(f"Skipping user {user.id}: last reminder was {(datetime.utcnow() - last.sent_at).total_seconds():.0f} secs ago, window is {interval_minutes} minutes")
					continue

			text = 'Напоминание: пожалуйста, завершите вашу регистрацию. Отправьте /start в боте и выберите нужный маршрут.'
			nlog = NotificationLog(user_id=user.id, channel='telegram', notif_type='registration_reminder', payload=text, status='pending')
			session.add(nlog)
			await session.commit()
			try:
				logger.info(f"Sending registration reminder to user.id={user.id}, telegram_id={getattr(user,'telegram_id', None)}")
				await bot.send_message(chat_id=user.telegram_id, text=text)
				nlog.status = 'sent'
				nlog.sent_at = datetime.utcnow()
				total_sent += 1
			except Exception as exc:
				logger.exception(f"Failed to send registration reminder to user.id={user.id}, telegram_id={getattr(user,'telegram_id', None)}: {exc}")
				nlog.status = 'failed'
			session.add(nlog)
			await session.commit()
		return total_sent if total_sent else 0
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
		# Always have the daily cleanup job
		scheduler.add_job(
			check_and_cancel_unpaid,
			IntervalTrigger(hours=24),  # Run every 24 hours
			id="cancel_unpaid",
		)

		# Initial scheduling for reminders: we will set them according to settings
		# Use the settings watcher to (re)configure these jobs dynamically
		scheduler.add_job(
			update_jobs_from_settings,
			IntervalTrigger(minutes=1),
			id="reminder_settings_watcher",
			args=[bot]
		)
		scheduler.start()
		logger.info("Background scheduler started (watcher active)")


async def update_jobs_from_settings(bot=None):
	"""Reload reminder-related settings from DB and (re)schedule reminder jobs.
	This runs periodically (watcher) and will reschedule jobs only when interval changed.
	"""
	global _current_reminder_check_interval
	try:
		settings = await load_settings_async()
		n_minutes = int(settings.get('reminder_check_interval_minutes', 60))
		# if unchanged, nothing to do
		if _current_reminder_check_interval == n_minutes and scheduler.get_job('assignment_reminders'):
			return

		# remove existing reminder jobs if present
		for jid in ('assignment_reminders', 'registration_reminders'):
			if scheduler.get_job(jid):
				scheduler.remove_job(jid)

		# schedule with new interval (in minutes)
		scheduler.add_job(
			send_assignment_reminders,
			IntervalTrigger(minutes=n_minutes),
			id='assignment_reminders',
			args=[bot]
		)
		scheduler.add_job(
			send_registration_reminders,
			IntervalTrigger(minutes=n_minutes),
			id='registration_reminders',
			args=[bot]
		)

		_current_reminder_check_interval = n_minutes
		logger.info(f"Scheduler reminder jobs configured to run every {n_minutes} minutes")

		# Check manual trigger flag in settings: if present and newer than last processed, run immediately
		try:
			manual = settings.get('manual_trigger')
			if manual and isinstance(manual, dict):
				ts = manual.get('ts')
				if ts:
					try:
						parsed = datetime.fromisoformat(ts)
					except Exception:
						parsed = None
					if parsed:
						timestamp = parsed.timestamp()
						global _last_manual_trigger_ts
						if _last_manual_trigger_ts is None or timestamp > _last_manual_trigger_ts:
							_last_manual_trigger_ts = timestamp
							# launch selected triggers
							if manual.get('assignment'):
								logger.info('Manual trigger: running assignment reminders now')
								await send_assignment_reminders(bot=bot)
							if manual.get('registration'):
								logger.info('Manual trigger: running registration reminders now')
								# For manual triggers via DB, force bypass cutoff
								await send_registration_reminders(bot=bot, force=True)
							# clear manual trigger to avoid re-processing (optional)
							if scheduler.get_job('reminder_settings_watcher'):
								# remove manual_trigger key by setting it to None in DB
								async_session = get_session()
								async with async_session as session:
									result = await session.execute(select(Setting).where(Setting.key == 'manual_trigger'))
									rec = result.scalar_one_or_none()
									if rec:
										rec.value = None
										session.add(rec)
										await session.commit()
							
		except Exception as exc:
			logger.exception(f"Failed to process manual_trigger: {exc}")
	except Exception as exc:
		logger.exception(f"Failed to update scheduler jobs from settings: {exc}")


def stop_scheduler():
	"""Stop the async scheduler."""
	if scheduler.running:
		scheduler.shutdown()
		logger.info("Background scheduler stopped")
