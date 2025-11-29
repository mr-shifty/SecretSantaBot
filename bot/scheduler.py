"""Scheduler for reminders and deadline handling using APScheduler."""
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from bot.db.models import Route1Entry, Route2Entry, Assignment, NotificationLog, User
from bot.db.database import get_session
from bot.randomizer import perform_draw
from bot.logger import get_logger

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
		scheduler.start()
		logger.info("Background scheduler started")


def stop_scheduler():
	"""Stop the async scheduler."""
	if scheduler.running:
		scheduler.shutdown()
		logger.info("Background scheduler stopped")
