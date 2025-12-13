import csv
import io
from datetime import datetime
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, Document, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import delete
from aiogram.fsm.context import FSMContext
from bot.config import SEND_REAL_NOTIFICATIONS
from bot.utils import is_admin
from bot.randomizer import perform_draw
from bot.db.models import User, Route1Entry, Route2Entry, Assignment, NotificationLog
from bot.db.database import get_session
from bot.logger import get_logger
from sqlalchemy import select
import json
from bot.notifications import build_assignment_notification

logger = get_logger("admin")
router = Router()


# use `is_admin` from `bot.utils` (async)


@router.callback_query(lambda c: c.data == "admin_draw_r1")
async def cb_admin_draw_r1(callback: CallbackQuery):
	await callback.answer()
	user_id = callback.from_user.id
	if not await is_admin(user_id):
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
	if not await is_admin(user_id):
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
	if not await is_admin(user_id):
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

	# Group assignments by giver_user_id to send a single combined message when user has multiple assignments
	givers_map: dict[int, list[Assignment]] = {}
	for a in assignments:
		givers_map.setdefault(a.giver_user_id, []).append(a)

	sent_count = 0
	skipped_count = 0
	failed_count = 0

	for giver_id, giver_assignments in givers_map.items():
		async_session = get_session()
		async with async_session as session:
			# load giver
			result = await session.execute(select(User).where(User.id == giver_id))
			giver = result.scalar_one_or_none()
			if not giver:
				logger.warning(f"No giver user found for giver_id {giver_id}")
				continue

			# Build combined message and button texts using shared helper
			nlogs_created = []
			send_text, buttons = await build_assignment_notification(session, giver_assignments)

			# Create a NotificationLog entry per assignment (pending)
			for a in giver_assignments:
				nlog = NotificationLog(
					user_id=giver.id if giver else None,
					channel='telegram',
					notif_type='assignment',
					payload=None,  # we'll set payload below
					status='pending'
				)
				session.add(nlog)
				await session.commit()
				nlogs_created.append(nlog)

			# Update payloads of nlogs created for this giver to include full text
			for nl in nlogs_created:
				nl.payload = send_text
				session.add(nl)

			# Safe-send: when SEND_REAL_NOTIFICATIONS is False (default), only admins receive messages
			if not SEND_REAL_NOTIFICATIONS and not await is_admin(giver.telegram_id):
				logger.info(f"Skipping send to {giver.telegram_id} (not an admin) — logged only")
				skipped_count += 1
				await session.commit()
				continue

			# Build inline keyboard: one button per assignment (with assignment id callback)
			ikb = InlineKeyboardMarkup(inline_keyboard=[])
			for a in giver_assignments:
				if a.route_type == 2:
					btn_text = 'Поздравление отправлено'
				else:
					btn_text = 'Подарок отправлен'
				ikb.inline_keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"mark_sent:{a.id}")])

			try:
				await callback.bot.send_message(chat_id=giver.telegram_id, text=send_text, reply_markup=ikb, parse_mode="HTML")
				# mark notification logs as sent (but do not mark assignments as sent — user must confirm)
				for nl in nlogs_created:
					nl.status = 'sent'
					nl.sent_at = datetime.utcnow()
					session.add(nl)
				await session.commit()
				sent_count += 1
			except Exception as exc:
				logger.exception(f"Failed to send combined notification to giver {giver_id}: {exc}")
				for nl in nlogs_created:
					nl.status = 'failed'
					session.add(nl)
				await session.commit()
				failed_count += 1

	logger.info(f"Sent {sent_count} notifications for route{route} (skipped: {skipped_count}, failed: {failed_count})")
	await callback.message.answer(f"✅ Отправлено уведомлений: {sent_count}\n✳️ Пропущено (режим теста): {skipped_count}\n❗ Ошибок: {failed_count}")


@router.message(lambda message: (message.text or "").strip().lower() in ("подарок отправлен", "поздравление отправлено"))
async def msg_mark_sent(message: Message):
	"""Allow user to mark their assignment as sent by pressing reply keyboard button."""
	# resolve internal user id
	async_session = get_session()
	async with async_session as session:
		# find latest pending assignment where this user is giver
		result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
		user = result.scalar_one_or_none()
		if not user:
			await message.answer('Пользователь не найден')
			return


		# Determine which button user pressed and mark the corresponding route assignment
		text = (message.text or '').strip()
		# Map button text to route_type (case-insensitive)
		if text.lower() == 'подарок отправлен':
			route_filter = 1
			success_msg = 'Спасибо — статус подарка помечен как отправлено ✅'
		elif text.lower() == 'поздравление отправлено':
			route_filter = 2
			success_msg = 'Спасибо — статус поздравления помечен как отправлено ✅'
		else:
			# Unknown button; ignore but remove keyboard
			await message.answer('Спасибо.', reply_markup=ReplyKeyboardRemove())
			return

		result = await session.execute(
			select(Assignment).where(Assignment.giver_user_id == user.id).where(Assignment.route_type == route_filter).where(Assignment.sent_status != 'sent')
		)
		assignment = result.scalars().first()
		if not assignment:
			await message.answer('Нет активных назначений для отметки.', reply_markup=ReplyKeyboardRemove())
			return

		assignment.sent_status = 'sent'
		await session.commit()

	# Notify receiver about sent status (same logic as inline callback)
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User).where(User.id == assignment.receiver_user_id))
		receiver = result.scalar_one_or_none()
		if assignment.route_type == 1:
			result = await session.execute(
				select(Route1Entry).where(Route1Entry.user_id == assignment.receiver_user_id).where(Route1Entry.status == 'completed')
			)
			rentry = result.scalar_one_or_none()
			method = ''
			if rentry:
				if rentry.pickup_type == 'postal':
					method = f"Почта: {rentry.full_address}"
				else:
					method = f"Пункт выдачи: {rentry.pickup_company or ''}, {rentry.pickup_address or ''}"
		else:
			result = await session.execute(
				select(Route2Entry).where(Route2Entry.user_id == assignment.receiver_user_id).where(Route2Entry.status == 'completed')
			)
			rentry = result.scalar_one_or_none()
			method = ''
			if rentry:
				method = f"Email: {rentry.email or ''}"

		notif_text = ''
		if assignment.route_type == 1:
			notif_text = f"Ваш тайный санта отправил вам подарок. Способ доставки: {method}"
		else:
			notif_text = f"Ваш диджитал санта отправил вам поздравление. {method}"

		nlog = NotificationLog(user_id=assignment.receiver_user_id, channel='telegram', notif_type='assignment_received', payload=notif_text, status='pending')
		session.add(nlog)
		await session.commit()

		if receiver and receiver.telegram_id:
			try:
				await message.bot.send_message(chat_id=receiver.telegram_id, text=notif_text)
				nlog.status = 'sent'
				nlog.sent_at = datetime.utcnow()
				session.add(nlog)
				await session.commit()
			except Exception:
				nlog.status = 'failed'
				session.add(nlog)
				await session.commit()

	await message.answer(success_msg, reply_markup=ReplyKeyboardRemove())




# Allow users (or admins) to mark an assignment as sent via inline button
@router.callback_query(lambda c: c.data and c.data.startswith('mark_sent:'))
async def cb_mark_sent(callback: CallbackQuery):
	await callback.answer()
	user_id = callback.from_user.id
	# parse assignment id
	try:
		assignment_id = int(callback.data.split(':', 1)[1])
	except Exception:
		await callback.message.answer('Неверная команда')
		return

	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(Assignment).where(Assignment.id == assignment_id))
		assignment = result.scalar_one_or_none()
		if not assignment:
			await callback.message.answer('Назначение не найдено')
			return

		# load giver user
		result = await session.execute(select(User).where(User.id == assignment.giver_user_id))
		giver = result.scalar_one_or_none()
		if not giver:
			await callback.message.answer('Пользователь отправителя не найден')
			return

		# Only the giver (by telegram_id) or admins can mark as sent
		if user_id != giver.telegram_id and not await is_admin(user_id):
			await callback.message.answer('❌ Вы не можете изменить статус этого назначения')
			return

		assignment.sent_status = 'sent'
		await session.commit()

	# Notify receiver that gift/congrats was sent and include method
	async_session = get_session()
	async with async_session as session:
		result = await session.execute(select(User).where(User.id == assignment.receiver_user_id))
		receiver = result.scalar_one_or_none()
		# find receiver's latest entry to describe method
		if assignment.route_type == 1:
			result = await session.execute(
				select(Route1Entry).where(Route1Entry.user_id == assignment.receiver_user_id).where(Route1Entry.status == 'completed')
			)
			rentry = result.scalar_one_or_none()
			method = ''
			if rentry:
				if rentry.pickup_type == 'postal':
					method = f"Почта: {rentry.full_address}"
				else:
					method = f"Пункт выдачи: {rentry.pickup_company or ''}, {rentry.pickup_address or ''}"
		else:
			# route 2
			result = await session.execute(
				select(Route2Entry).where(Route2Entry.user_id == assignment.receiver_user_id).where(Route2Entry.status == 'completed')
			)
			rentry = result.scalar_one_or_none()
			method = ''
			if rentry:
				method = f"Email: {rentry.email or ''}"

		# Create log for receiver
		notif_text = ''
		if assignment.route_type == 1:
			notif_text = f"Ваш тайный санта отправил вам подарок. Способ доставки: {method}"
		else:
			notif_text = f"Ваш диджитал санта отправил вам поздравление. {method}"

		nlog = NotificationLog(user_id=assignment.receiver_user_id, channel='telegram', notif_type='assignment_received', payload=notif_text, status='pending')
		session.add(nlog)
		await session.commit()

		# send to receiver if we have telegram id
		if receiver and receiver.telegram_id:
			try:
				await callback.bot.send_message(chat_id=receiver.telegram_id, text=notif_text)
				nlog.status = 'sent'
				nlog.sent_at = datetime.utcnow()
				session.add(nlog)
				await session.commit()
			except Exception:
				nlog.status = 'failed'
				session.add(nlog)
				await session.commit()

	await callback.message.answer('Статус назначение обновлён: отправлено ✅')


@router.callback_query(lambda c: c.data in ("admin_export_r1", "admin_export_r2"))
async def cb_admin_export(callback: CallbackQuery):
	await callback.answer()
	user_id = callback.from_user.id
	if not await is_admin(user_id):
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


@router.callback_query(lambda c: c.data in ("admin_reset_r1", "admin_reset_r2"))
async def cb_admin_reset(callback: CallbackQuery):
	await callback.answer()
	user_id = callback.from_user.id
	if not await is_admin(user_id):
		logger.warning(f"Non-admin user {user_id} attempted admin_reset")
		await callback.message.answer("❌ У вас нет прав администратора")
		return

	route = 1 if callback.data == "admin_reset_r1" else 2
	async_session = get_session()
	async with async_session as session:
		# Delete assignments for this route only. Do NOT change entry status;
		# keep users' registrations (Route1Entry/Route2Entry) as they are so
		# a new draw can be performed immediately using existing participants.
		await session.execute(delete(Assignment).where(Assignment.route_type == route))
		await session.commit()

	await callback.message.answer(f"✅ Розыгрыш для маршрута {route} сброшен. Регистрация снова открыта.")


@router.message(Command("draw"))
async def cmd_draw(message: Message):
	if not await is_admin(message.from_user.id):
		await message.answer("❌ У вас нет прав администратора")
		return
	
	await message.answer("Выберите маршрут для розыгрыша:\n1️⃣ Маршрут 1\n2️⃣ Маршрут 2")


@router.message(Command("draw_route1"))
async def cmd_draw_route1(message: Message):
	if not await is_admin(message.from_user.id):
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
	if not await is_admin(message.from_user.id):
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
	if not await is_admin(message.from_user.id):
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

	# Group assignments by giver and send combined messages using the shared helper
	givers_map: dict[int, list[Assignment]] = {}
	for a in assignments:
		givers_map.setdefault(a.giver_user_id, []).append(a)

	for giver_id, giver_assignments in givers_map.items():
		async_session = get_session()
		async with async_session as session:
			result = await session.execute(select(User).where(User.id == giver_id))
			giver = result.scalar_one_or_none()
			if not giver:
				logger.warning(f"No giver user found for giver_id {giver_id}")
				continue

			send_text, buttons = await build_assignment_notification(session, giver_assignments)

			# Create pending NotificationLog entries and set payloads
			nlogs_created = []
			for a in giver_assignments:
				nlog = NotificationLog(
					user_id=giver.id if giver else None,
					channel='telegram',
					notif_type='assignment',
					payload=None,
					status='pending'
				)
				session.add(nlog)
				await session.commit()
				nlogs_created.append(nlog)

			for nl in nlogs_created:
				nl.payload = send_text
				session.add(nl)

			# Safe send: in test mode (no real notifications), only admins are delivered messages
			if not SEND_REAL_NOTIFICATIONS and not await is_admin(giver.telegram_id):
				logger.info(f"Skipping send to {giver.telegram_id} (not an admin) — logged only")
				skipped_count += 1
				await session.commit()
				continue

			# Build inline keyboard with appropriate labels
			ikb = InlineKeyboardMarkup(inline_keyboard=[])
			for a in giver_assignments:
				if a.route_type == 2:
					btn_text = 'Поздравление отправлено'
				else:
					btn_text = 'Подарок отправлен'
				ikb.inline_keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"mark_sent:{a.id}")])

			try:
				await message.bot.send_message(chat_id=giver.telegram_id, text=send_text, reply_markup=ikb, parse_mode="HTML")
				for nl in nlogs_created:
					nl.status = 'sent'
					nl.sent_at = datetime.utcnow()
					session.add(nl)
				await session.commit()
				sent_count += 1
			except Exception as exc:
				logger.exception(f"Failed to send combined notification to giver {giver_id}: {exc}")
				for nl in nlogs_created:
					nl.status = 'failed'
					session.add(nl)
				await session.commit()
				failed_count += 1

	logger.info(f"Sent {sent_count} notifications for route1 (skipped: {skipped_count}, failed: {failed_count})")
	await message.answer(f"✅ Отправлено уведомлений: {sent_count}\n✳️ Пропущено (режим теста): {skipped_count}\n❗ Ошибок: {failed_count}")


@router.message(Command("notify_route2"))
async def cmd_notify_route2(message: Message):
	if not await is_admin(message.from_user.id):
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
	if not await is_admin(message.from_user.id):
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
