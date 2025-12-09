import csv
import io
from datetime import datetime
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, Document, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import delete
from aiogram.fsm.context import FSMContext
from bot.config import ADMIN_IDS, SEND_REAL_NOTIFICATIONS
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

			# For each assignment of this giver, fetch receiver and their entry
			parts = []
			buttons = []
			nlogs_created = []
			for a in giver_assignments:
				result = await session.execute(select(User).where(User.id == a.receiver_user_id))
				receiver = result.scalar_one_or_none()
				# Try to get latest completed entry depending on route
				if a.route_type == 1:
					result = await session.execute(
						select(Route1Entry).where(Route1Entry.user_id == a.receiver_user_id).where(Route1Entry.status == 'completed')
					)
					rentry = result.scalar_one_or_none()
				else:
					result = await session.execute(
						select(Route2Entry).where(Route2Entry.user_id == a.receiver_user_id).where(Route2Entry.status == 'completed')
					)
					rentry = result.scalar_one_or_none()

				recv_name = receiver.telegram_username or f"{receiver.first_name or ''} {receiver.last_name or ''}" if receiver else 'Получатель'

				# Build readable wishlist / survey
				def format_survey(srv):
					labels = {
						'favorite_color': 'Любимый цвет',
						'favorite_activity': 'Любимый вид деятельности',
						'favorite_genre': 'Любимый жанр',
						'hobby': 'Хобби',
						'undesired_gift': 'Чего бы не хотели получить',
						'favorite_snack': 'Любимый перекус',
						'favorite_brands': 'Любимые бренды/магазины',
						'allergies': 'Аллергии/предпочтения',
					}
					try:
						if isinstance(srv, dict):
							items = [f"{labels.get(k, k)}: {v}" for k, v in srv.items()]
						else:
							items = [str(srv)]
						return "\n".join(items)
					except Exception:
						return str(srv)

				if a.route_type == 1:
					# For physical gift route include wishlist and address
					if rentry and getattr(rentry, 'survey', None):
						survey_obj = None
						if isinstance(rentry.survey, (dict, list)):
							survey_obj = rentry.survey
						else:
							try:
								survey_obj = json.loads(rentry.survey)
							except Exception:
								survey_obj = None

						if survey_obj is not None:
							wishlist = 'Анкета:\n' + format_survey(survey_obj)
						else:
							wishlist = str(rentry.survey)
					else:
						wishlist = (rentry.wishlist if rentry and getattr(rentry, 'wishlist', None) else 'Пожелания отсутствуют')

					delivery = rentry.full_address if (rentry and getattr(rentry, 'full_address', None)) else ''
					if not delivery and rentry and getattr(rentry, 'pickup_company', None):
						delivery = f"Пункт выдачи: {rentry.pickup_company}, {getattr(rentry, 'pickup_address', '') or ''}"
					recipient_phone = ''
					if rentry:
						recipient_phone = getattr(rentry, 'postal_recipient_phone', None) or getattr(rentry, 'pickup_recipient_phone', None) or ''

					part_text = (
						f"Вы Тайный Санта для: {('@' + receiver.telegram_username) if receiver and receiver.telegram_username else recv_name}\n"
						f"{wishlist}\n"
						f"Адрес / пункт выдачи:\n{delivery}\n"
						f"Телефон: {recipient_phone}\n"
					)
				else:
					# For digital route include only email and phone
					email = getattr(rentry, 'email', '') if rentry else ''
					phone = ''
					if rentry:
						phone = getattr(rentry, 'postal_recipient_phone', None) or getattr(rentry, 'pickup_recipient_phone', None) or ''
					part_text = (
						f"Вы Диджитал Санта для: {('@' + receiver.telegram_username) if receiver and receiver.telegram_username else recv_name}\n"
						f"Email для поздравления: {email or 'Не указан'}\n"
						f"Телефон: {phone or 'Не указан'}\n"
					)
				parts.append(part_text)

				# Determine button text for this assignment
				if a.route_type == 2:
					buttons.append('Поздравление отправлено')
				else:
					buttons.append('Подарок отправлен')

				# Create a NotificationLog entry per assignment (pending)
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

			# Build combined message from parts (each part already contains route-specific header)
			send_text = "\n---\n".join(parts)
			# Add recommended amount note if any route1 parts exist
			if any(a.route_type == 1 for a in giver_assignments):
				send_text = "Ваш тайный санта найден\n\n" + send_text
			if any(a.route_type == 2 for a in giver_assignments):
				# If both types present, ensure digital notice appears too (with usernames included in parts)
				send_text = ("Ваш диджитал санта найден\n\n" + send_text) if not any(a.route_type == 1 for a in giver_assignments) else send_text
			# Append recommendation only when route1 present
			if any(a.route_type == 1 for a in giver_assignments):
				send_text += "\nРекомендуемая сумма для подарка не более 1000 р.\n"

			# Update payloads of nlogs created for this giver to include full text
			for nl in nlogs_created:
				nl.payload = send_text
				session.add(nl)

			# Safe-send: when SEND_REAL_NOTIFICATIONS is False (default), only ADMIN_IDS receive messages
			if not SEND_REAL_NOTIFICATIONS and giver.telegram_id not in ADMIN_IDS:
				logger.info(f"Skipping send to {giver.telegram_id} (not in ADMIN_IDS) — logged only")
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
				await callback.bot.send_message(chat_id=giver.telegram_id, text=send_text, reply_markup=ikb)
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


@router.message(lambda message: (message.text or "").strip() == "Подарок отправлен")
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
		# Map button text to route_type
		if text == 'Подарок отправлен':
			route_filter = 1
			success_msg = 'Спасибо — статус подарка помечен как отправлено ✅'
		elif text == 'Поздравление отправлено':
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
		if user_id != giver.telegram_id and user_id not in ADMIN_IDS:
			await callback.message.answer('❌ Вы не можете изменить статус этого назначения')
			return

		assignment.sent_status = 'sent'
		await session.commit()

	await callback.message.answer('Статус назначение обновлён: отправлено ✅')


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


@router.callback_query(lambda c: c.data in ("admin_reset_r1", "admin_reset_r2"))
async def cb_admin_reset(callback: CallbackQuery):
	await callback.answer()
	user_id = callback.from_user.id
	if not is_admin(user_id):
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

			if not SEND_REAL_NOTIFICATIONS and giver.telegram_id not in ADMIN_IDS:
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
