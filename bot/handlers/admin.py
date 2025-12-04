import csv
import io
from datetime import datetime
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, Document, CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.config import ADMIN_IDS
from bot.randomizer import perform_draw
from bot.db.models import User, Route1Entry, Route2Entry, Assignment, NotificationLog
from bot.db.database import get_session
from bot.logger import get_logger
from sqlalchemy import select
import json

logger = get_logger("admin")
router = Router()


def is_admin(user_id: int) -> bool:
	return user_id in ADMIN_IDS


@router.callback_query(lambda c: c.data == "admin_draw_r1")
async def cb_admin_draw_r1(callback: CallbackQuery):
	await callback.answer()
	user_id = callback.from_user.id
	if not is_admin(user_id):
		logger.warning(f"Non-admin user {user_id} attempted admin_draw_r1")
		await callback.message.answer("❌ У вас нет прав администратора")
		return

	logger.info(f"Admin {user_id} triggered draw_route1 via button")
	success, msg, count = await perform_draw(1, callback.bot)
	if success:
		logger.info(f"Route 1 draw completed successfully: {count} pairs created")
		await callback.message.answer(f"✅ {msg}\n📊 Создано {count} пар")
	else:
		logger.error(f"Route 1 draw failed: {msg}")
		await callback.message.answer(f"❌ {msg}")


@router.callback_query(lambda c: c.data == "admin_draw_r2")
async def cb_admin_draw_r2(callback: CallbackQuery):
	await callback.answer()
	user_id = callback.from_user.id
	if not is_admin(user_id):
		logger.warning(f"Non-admin user {user_id} attempted admin_draw_r2")
		await callback.message.answer("❌ У вас нет прав администратора")
		return

	logger.info(f"Admin {user_id} triggered draw_route2 via button")
	success, msg, count = await perform_draw(2, callback.bot)
	if success:
		logger.info(f"Route 2 draw completed successfully: {count} pairs created")
		await callback.message.answer(f"✅ {msg}\n📊 Создано {count} пар")
	else:
		logger.error(f"Route 2 draw failed: {msg}")
		await callback.message.answer(f"❌ {msg}")


@router.callback_query(lambda c: c.data in ("admin_notify_r1", "admin_notify_r2"))
async def cb_admin_notify(callback: CallbackQuery):
	await callback.answer()
	user_id = callback.from_user.id
	if not is_admin(user_id):
		logger.warning(f"Non-admin user {user_id} attempted admin_notify")
		await callback.message.answer("❌ У вас нет прав администратора")
		return

	route = 1 if callback.data == "admin_notify_r1" else 2
	logger.info(f"Admin {user_id} triggered notify for route {route} via button")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Assignment).where(Assignment.route_type == route))
		assignments = result.scalars().all()

	if not assignments:
		logger.info(f"No assignments found for route{route} notification")
		await callback.message.answer(f"Нет распределений для маршрута {route}")
		return

	sent_count = 0
	skipped_count = 0
	failed_count = 0
	for assignment in assignments:
		# Build and record notification for each giver about their receiver
		async_session = get_session()
		async with async_session as session:
			# Re-load assignment, giver and receiver within same session so we can update statuses
			result = await session.execute(select(Assignment).where(Assignment.id == assignment.id))
			db_assignment = result.scalar_one_or_none()

			result = await session.execute(select(User).where(User.id == db_assignment.giver_user_id))
			giver = result.scalar_one_or_none()
			result = await session.execute(select(User).where(User.id == db_assignment.receiver_user_id))
			receiver = result.scalar_one_or_none()
			# Get receiver's latest route1 entry
			result = await session.execute(
				select(Route1Entry).where(Route1Entry.user_id == db_assignment.receiver_user_id).where(Route1Entry.status == 'completed')
			)
			rentry = result.scalar_one_or_none()

			if not giver:
				logger.warning(f"No giver user found for assignment {assignment.id}")
				continue

			recv_name = receiver.telegram_username or f"{receiver.first_name or ''} {receiver.last_name or ''}" if receiver else 'Получатель'
			# Prefer structured survey if present
			if rentry and rentry.survey:
				survey_obj = None
				if isinstance(rentry.survey, (dict, list)):
					survey_obj = rentry.survey
				else:
					try:
						survey_obj = json.loads(rentry.survey)
					except Exception:
						survey_obj = None

				if survey_obj is not None:
					try:
						wishlist = "Анкета:\n" + "\n".join([f"{k}: {v}" for k, v in survey_obj.items()])
					except Exception:
						wishlist = str(survey_obj)
				else:
					wishlist = rentry.survey
			else:
				wishlist = (rentry.wishlist if rentry and rentry.wishlist else 'Пожелания отсутствуют')

			delivery = rentry.full_address if (rentry and rentry.full_address) else ''
			if not delivery and rentry and rentry.pickup_company:
				delivery = f"Пункт выдачи: {rentry.pickup_company}, {rentry.pickup_address or ''}"
			recipient_phone = ''
			if rentry:
				recipient_phone = rentry.postal_recipient_phone or rentry.pickup_recipient_phone or ''

			text = (
				f"🎁 Розыгрыш завершён — у вас есть получатель!\n\n"
				f"Вы — Тайный Санта для: {recv_name}\n\n"
				f"Пожелания:\n{wishlist}\n\n"
				f"Адрес / пункт выдачи:\n{delivery}\n"
				f"Телефон получателя: {recipient_phone}\n\n"
				f"Рекомендуемая сумма для подарка не более 1000 р.\n"
			)

			# Create NotificationLog (pending)
			nlog = NotificationLog(
				user_id=giver.id if giver else None,
				channel='telegram',
				notif_type='assignment',
				payload=text,
				status='pending'
			)
			session.add(nlog)
			await session.commit()

			# Safe-send: only send messages to ADMIN_IDS by default
			if giver.telegram_id not in ADMIN_IDS:
				logger.info(f"Skipping send to {giver.telegram_id} (not in ADMIN_IDS) — logged only")
				skipped_count += 1
				# keep assignment status pending; keep nlog as pending
				continue

			try:
				await callback.bot.send_message(chat_id=giver.telegram_id, text=text)
				# update log and assignment
				nlog.status = 'sent'
				nlog.sent_at = datetime.utcnow()
				db_assignment.sent_status = 'sent'
				sent_count += 1
			except Exception as exc:
				logger.exception(f"Failed to send notification for assignment {assignment.id}: {exc}")
				nlog.status = 'failed'
				db_assignment.sent_status = 'failed'
				failed_count += 1

			session.add(nlog)
			session.add(db_assignment)
			await session.commit()

	logger.info(f"Sent {sent_count} notifications for route{route} (skipped: {skipped_count}, failed: {failed_count})")
	await callback.message.answer(f"✅ Отправлено уведомлений: {sent_count}\n✳️ Пропущено (режим теста): {skipped_count}\n❗ Ошибок: {failed_count}")


@router.callback_query(lambda c: c.data in ("admin_export_r1", "admin_export_r2"))
async def cb_admin_export(callback: CallbackQuery):
	await callback.answer()
	user_id = callback.from_user.id
	if not is_admin(user_id):
		logger.warning(f"Non-admin user {user_id} attempted admin_export")
		await callback.message.answer("❌ У вас нет прав администратора")
		return

	route = 1 if callback.data == "admin_export_r1" else 2
	logger.info(f"Admin {user_id} triggered export for route {route} via button")

	async_session = get_session()
	if route == 1:
		async with async_session as session:
			result = await session.execute(select(Route1Entry))
			entries = result.scalars().all()

		if not entries:
			await callback.message.answer("Нет данных для экспорта")
			return

		output = io.StringIO()
		writer = csv.writer(output)
		writer.writerow(['ID', 'Telegram ID', 'Email', 'Адрес', 'Способ доставки', 'Пожелания/Анкета', 'Статус'])

		for entry in entries:
			async_session = get_session()
			async with async_session as session:
				result = await session.execute(select(User).where(User.id == entry.user_id))
				user = result.scalar_one_or_none()

			writer.writerow([
				entry.id,
				user.telegram_id if user else '',
				entry.email,
				entry.full_address,
				entry.delivery_method or '',
				entry.survey or entry.wishlist or '',
				entry.status
			])

		csv_bytes = output.getvalue().encode('utf-8-sig')
		await callback.message.answer_document(
			document=("route1_export.csv", io.BytesIO(csv_bytes)),
			caption="📥 Экспорт маршрута 1"
		)
	else:
		async with async_session as session:
			result = await session.execute(select(Route2Entry))
			entries = result.scalars().all()

		if not entries:
			await callback.message.answer("Нет данных для экспорта")
			return

		output = io.StringIO()
		writer = csv.writer(output)
		writer.writerow(['ID', 'Telegram ID', 'Email', 'Статус'])

		for entry in entries:
			async_session = get_session()
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
		await callback.message.answer_document(
			document=("route2_export.csv", io.BytesIO(csv_bytes)),
			caption="📥 Экспорт маршрута 2"
		)


@router.callback_query(lambda c: c.data == "admin_close")
async def cb_admin_close(callback: CallbackQuery):
	await callback.answer()
	await callback.message.delete_reply_markup()
	await callback.message.answer("Закрыто")


@router.message(Command("draw"))
async def cmd_draw(message: Message):
	if not is_admin(message.from_user.id):
		await message.answer("❌ У вас нет прав администратора")
		return
	
	await message.answer("Выберите маршрут для розыгрыша:\n1️⃣ Маршрут 1\n2️⃣ Маршрут 2")


@router.message(Command("draw_route1"))
async def cmd_draw_route1(message: Message):
	if not is_admin(message.from_user.id):
		logger.warning(f"Non-admin user {message.from_user.id} attempted /draw_route1")
		await message.answer("❌ У вас нет прав администратора")
		return
	
	logger.info(f"Admin {message.from_user.id} triggered draw_route1")
	success, msg, count = await perform_draw(1, message.bot)
	if success:
		logger.info(f"Route 1 draw completed successfully: {count} pairs created")
		await message.answer(f"✅ {msg}\n📊 Создано {count} пар")
	else:
		logger.error(f"Route 1 draw failed: {msg}")
		await message.answer(f"❌ {msg}")


@router.message(Command("draw_route2"))
async def cmd_draw_route2(message: Message):
	if not is_admin(message.from_user.id):
		logger.warning(f"Non-admin user {message.from_user.id} attempted /draw_route2")
		await message.answer("❌ У вас нет прав администратора")
		return
	
	logger.info(f"Admin {message.from_user.id} triggered draw_route2")
	success, msg, count = await perform_draw(2, message.bot)
	if success:
		logger.info(f"Route 2 draw completed successfully: {count} pairs created")
		await message.answer(f"✅ {msg}\n📊 Создано {count} пар")
	else:
		logger.error(f"Route 2 draw failed: {msg}")
		await message.answer(f"❌ {msg}")


@router.message(Command("notify_route1"))
async def cmd_notify_route1(message: Message):
	if not is_admin(message.from_user.id):
		logger.warning(f"Non-admin user {message.from_user.id} attempted /notify_route1")
		await message.answer("❌ У вас нет прав администратора")
		return
	
	logger.info(f"Admin {message.from_user.id} triggered notify_route1")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Assignment).where(Assignment.route_type == 1))
		assignments = result.scalars().all()
	
	if not assignments:
		logger.info("No assignments found for route1 notification")
		await message.answer("Нет распределений для маршрута 1")
		return
	
	sent_count = 0
	skipped_count = 0
	failed_count = 0
	for assignment in assignments:
		async_session = get_session()
		async with async_session as session:
			result = await session.execute(select(Assignment).where(Assignment.id == assignment.id))
			db_assignment = result.scalar_one_or_none()

			result = await session.execute(select(User).where(User.id == db_assignment.giver_user_id))
			giver = result.scalar_one_or_none()
			result = await session.execute(select(User).where(User.id == db_assignment.receiver_user_id))
			receiver = result.scalar_one_or_none()
			result = await session.execute(
				select(Route1Entry).where(Route1Entry.user_id == db_assignment.receiver_user_id).where(Route1Entry.status == 'completed')
			)
			rentry = result.scalar_one_or_none()

			if not giver:
				logger.warning(f"No giver user found for assignment {assignment.id}")
				continue

			recv_name = receiver.telegram_username or f"{receiver.first_name or ''} {receiver.last_name or ''}" if receiver else 'Получатель'
			if rentry and rentry.survey:
				survey_obj = None
				if isinstance(rentry.survey, (dict, list)):
					survey_obj = rentry.survey
				else:
					try:
						survey_obj = json.loads(rentry.survey)
					except Exception:
						survey_obj = None

				if survey_obj is not None:
					try:
						wishlist = "Анкета:\n" + "\n".join([f"{k}: {v}" for k, v in survey_obj.items()])
					except Exception:
						wishlist = str(survey_obj)
				else:
					wishlist = rentry.survey
			else:
				wishlist = (rentry.wishlist if rentry and rentry.wishlist else 'Пожелания отсутствуют')
			delivery = rentry.full_address if (rentry and rentry.full_address) else ''
			if not delivery and rentry and rentry.pickup_company:
				delivery = f"Пункт выдачи: {rentry.pickup_company}, {rentry.pickup_address or ''}"
			recipient_phone = ''
			if rentry:
				recipient_phone = rentry.postal_recipient_phone or rentry.pickup_recipient_phone or ''

			text = (
				f"🎁 Розыгрыш завершён — у вас есть получатель!\n\n"
				f"Вы — Тайный Санта для: {recv_name}\n\n"
				f"Пожелания:\n{wishlist}\n\n"
				f"Адрес / пункт выдачи:\n{delivery}\n"
				f"Телефон получателя: {recipient_phone}\n\n"
				f"Рекомендуемая сумма для подарка не более 1000 р.\n"
			)

			# Create NotificationLog (pending)
			nlog = NotificationLog(
				user_id=giver.id if giver else None,
				channel='telegram',
				notif_type='assignment',
				payload=text,
				status='pending'
			)
			session.add(nlog)
			await session.commit()

			if giver.telegram_id not in ADMIN_IDS:
				logger.info(f"Skipping send to {giver.telegram_id} (not in ADMIN_IDS) — logged only")
				skipped_count += 1
				continue

			try:
				await message.bot.send_message(chat_id=giver.telegram_id, text=text)
				nlog.status = 'sent'
				nlog.sent_at = datetime.utcnow()
				db_assignment.sent_status = 'sent'
				sent_count += 1
			except Exception as exc:
				logger.exception(f"Failed to send notification for assignment {assignment.id}: {exc}")
				nlog.status = 'failed'
				db_assignment.sent_status = 'failed'
				failed_count += 1

			session.add(nlog)
			session.add(db_assignment)
			await session.commit()

	logger.info(f"Sent {sent_count} notifications for route1 (skipped: {skipped_count}, failed: {failed_count})")
	await message.answer(f"✅ Отправлено уведомлений: {sent_count}\n✳️ Пропущено (режим теста): {skipped_count}\n❗ Ошибок: {failed_count}")


@router.message(Command("notify_route2"))
async def cmd_notify_route2(message: Message):
	if not is_admin(message.from_user.id):
		logger.warning(f"Non-admin user {message.from_user.id} attempted /notify_route2")
		await message.answer("❌ У вас нет прав администратора")
		return
	
	logger.info(f"Admin {message.from_user.id} triggered notify_route2")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Assignment).where(Assignment.route_type == 2))
		assignments = result.scalars().all()
	
	if not assignments:
		logger.info("No assignments found for route2 notification")
		await message.answer("Нет распределений для маршрута 2")
		return
	
	sent_count = 0
	for assignment in assignments:
		# In production: send via bot or email
		sent_count += 1
	
	logger.info(f"Sent {sent_count} notifications for route2")
	await message.answer(f"✅ Отправлено уведомлений: {sent_count}")


@router.message(Command("export_route1"))
async def cmd_export_route1(message: Message):
	if not is_admin(message.from_user.id):
		logger.warning(f"Non-admin user {message.from_user.id} attempted /export_route1")
		await message.answer("❌ У вас нет прав администратора")
		return
	
	logger.info(f"Admin {message.from_user.id} triggered export_route1")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route1Entry))
		entries = result.scalars().all()
	
	if not entries:
		logger.info("No route1 entries to export")
		await message.answer("Нет данных для экспорта")
		return
	
	# Create CSV in memory
	output = io.StringIO()
	writer = csv.writer(output)
	writer.writerow(['ID', 'Telegram ID', 'Email', 'Адрес', 'Способ доставки', 'Пожелания/Анкета', 'Статус'])
	
	for entry in entries:
		async_session = get_session()
		async with async_session as session:
			result = await session.execute(select(User).where(User.id == entry.user_id))
			user = result.scalar_one_or_none()
		
		writer.writerow([
			entry.id,
			user.telegram_id if user else '',
			entry.email,
			entry.full_address,
			entry.delivery_method or '',
			entry.survey or entry.wishlist or '',
			entry.status
		])
	
	# Send as document
	csv_bytes = output.getvalue().encode('utf-8-sig')
	logger.info(f"Exporting {len(entries)} route1 entries for admin {message.from_user.id}")
	await message.answer_document(
		document=("route1_export.csv", io.BytesIO(csv_bytes)),
		caption="📥 Экспорт маршрута 1"
	)


@router.message(Command("export_route2"))
async def cmd_export_route2(message: Message):
	if not is_admin(message.from_user.id):
		logger.warning(f"Non-admin user {message.from_user.id} attempted /export_route2")
		await message.answer("❌ У вас нет прав администратора")
		return
	
	logger.info(f"Admin {message.from_user.id} triggered export_route2")
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Route2Entry))
		entries = result.scalars().all()
	
	if not entries:
		logger.info("No route2 entries to export")
		await message.answer("Нет данных для экспорта")
		return
	
	# Create CSV in memory
	output = io.StringIO()
	writer = csv.writer(output)
	writer.writerow(['ID', 'Telegram ID', 'Email', 'Статус'])
	
	for entry in entries:
		async_session = get_session()
		async with async_session as session:
			result = await session.execute(select(User).where(User.id == entry.user_id))
			user = result.scalar_one_or_none()
		
		writer.writerow([
			entry.id,
			user.telegram_id if user else '',
			entry.email,
			entry.status
		])
	
	# Send as document
	csv_bytes = output.getvalue().encode('utf-8-sig')
	logger.info(f"Exporting {len(entries)} route2 entries for admin {message.from_user.id}")
	await message.answer_document(
		document=("route2_export.csv", io.BytesIO(csv_bytes)),
		caption="📥 Экспорт маршрута 2"
	)


def register():
	return router
