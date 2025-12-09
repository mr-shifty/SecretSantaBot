"""Randomizer: Secret Santa assignment algorithm with deduplication and safety."""
import random
from sqlalchemy import select, and_
from bot.db.models import User, Route1Entry, Route2Entry, Assignment
from bot.db.database import get_session
from bot.logger import get_logger

logger = get_logger("randomizer")


async def get_active_entries(route_type: int):
    """Get all active (completed, not cancelled) entries for a route."""
    async_session = get_session()
    async with async_session as session:
        if route_type == 1:
            query = select(Route1Entry).where(Route1Entry.status == "completed")
        else:
            query = select(Route2Entry).where(Route2Entry.status == "completed")
        result = await session.execute(query)
        return result.scalars().all()


async def perform_draw(route_type: int, bot=None):
	"""Perform Secret Santa draw for a given route.
	
	Returns (success: bool, message: str, assignments_count: int)
	"""
	logger.info(f"Starting draw for route {route_type}")
	entries = await get_active_entries(route_type)
	
	if not entries:
		msg = f"Нет активных участников для маршрута {route_type}"
		logger.warning(msg)
		return False, msg, 0
	
	if len(entries) < 2:
		msg = f"Недостаточно участников (минимум 2). Есть только {len(entries)}"
		logger.warning(msg)
		return False, msg, 0
	
	logger.info(f"Route {route_type}: Found {len(entries)} participants")
	
	# Delete old assignments for this route
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(
			select(Assignment).where(Assignment.route_type == route_type)
		)
		old_assignments = result.scalars().all()
		for assignment in old_assignments:
			await session.delete(assignment)
		await session.commit()
		logger.info(f"Deleted {len(old_assignments)} old assignments for route {route_type}")
	
	# Create new assignments with protection against self-assignment
	participants = list(entries)
	random.shuffle(participants)
	
	assignments = []
	max_attempts = 100
	attempt = 0
	
	while attempt < max_attempts:
		valid = True
		temp_assignments = []
		
		for i, giver_entry in enumerate(participants):
			# Try to assign to next participant, avoiding self-assignment
			for j in range(len(participants)):
				receiver_entry = participants[(i + 1 + j) % len(participants)]
				if giver_entry.user_id != receiver_entry.user_id:
					temp_assignments.append((giver_entry, receiver_entry))
					break
			else:
				valid = False
				break
		
		if valid and len(temp_assignments) == len(participants):
			assignments = temp_assignments
			break
		
		random.shuffle(participants)
		attempt += 1
	
	if not assignments:
		msg = "Не удалось создать распределение (циклическая проблема)"
		logger.error(msg)
		return False, msg, 0
	
	# Save assignments to DB
	async with async_session as session:
		for giver_entry, receiver_entry in assignments:
			assignment = Assignment(
				giver_user_id=giver_entry.user_id,
				receiver_user_id=receiver_entry.user_id,
				route_type=route_type,
				sent_status="pending",
			)
			session.add(assignment)
		await session.commit()

		# Ensure all newly created assignments for this route are explicitly marked as pending
		# (guards against DB defaults or previous inconsistent states)
		await session.execute(
			select(Assignment).where(Assignment.route_type == route_type)
		)
		for a in (await session.execute(select(Assignment).where(Assignment.route_type == route_type))).scalars().all():
			if a.sent_status != 'pending':
				a.sent_status = 'pending'
		await session.commit()
	
	logger.info(f"Successfully created {len(assignments)} assignments for route {route_type}")
	return True, f"Распределение для маршрута {route_type} успешно создано", len(assignments)
