from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from bot.states import Route2States
from bot.utils import get_or_create_user, is_valid_email, save_route2_entry, check_active_route2_entry
from bot.logger import get_logger
import os
from datetime import datetime
from pathlib import Path
from bot.keyboards import reply_menu
from bot.config import ADMIN_IDS

logger = get_logger("route2")
router = Router()


@router.message(Command("route2"))
async def cmd_route2(message: Message, state: FSMContext):
	# Check if user already has active entry
	has_active = await check_active_route2_entry(message.from_user.id)
	if has_active:
		logger.info(f"User {message.from_user.id} attempted duplicate route2 registration")
		await message.answer("⚠️ У вас уже есть активная заявка для маршрута 'Диджитал Санта (с поздравлениями)'. Одна заявка на маршрут.")
		return
	
	logger.info(f"User {message.from_user.id} started route2 registration")
	await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
	await message.answer(
		"💌 Добро пожаловать в «Диджитал Санта (с поздравлениями)»!\n\n"
		"В этом маршруте вы отправляете поздравления и открытки по email.\n\n"
		"Пожалуйста, введите ваш email:"
	)
	await state.set_state(Route2States.email)


@router.message(Route2States.email)
async def process_email(message: Message, state: FSMContext):
	email = message.text.strip()
	if not is_valid_email(email):
		logger.warning(f"User {message.from_user.id} provided invalid email for route2: {email}")
		await message.answer("❌ Неверный формат email. Попробуйте снова:")
		return

	logger.debug(f"User {message.from_user.id} provided valid email for route2: {email}")
	await state.update_data(email=email)
	await message.answer("Введите ваш телефон (опционально, или напишите 'пропустить'):")
	await state.set_state(Route2States.phone)


@router.message(Route2States.phone)
async def process_phone(message: Message, state: FSMContext):
	text = (message.text or "").strip()
	if text.lower() in ("пропустить", "skip", "нет", "-"):
		phone = None
	else:
		phone = text
	await state.update_data(phone=phone)
	
	data = await state.get_data()
	email = data.get("email")
	
	# Get current year for notify_date (Dec 21)
	notify_date = datetime(datetime.now().year, 12, 21)
	
	logger.info(f"User {message.from_user.id} submitting route2 entry: email={email}")
	await save_route2_entry(message.from_user.id, email, phone=phone, notify_date=notify_date)
	
	is_admin = message.from_user.id in ADMIN_IDS
	await message.answer(
		"✅ Спасибо! Ваша регистрация в Диджитал Санте успешно сохранена.\n\n"
		"21 декабря вы получите email своего Диджитал Санты. "
		"После этого вы сможете отправить открытку/поздравление вашему получателю! 🎄",
		reply_markup=reply_menu(is_admin=is_admin)
	)
	await state.clear()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
	logger.info(f"User {message.from_user.id} cancelled route2 registration")
	await state.clear()
	await message.answer("❌ Регистрация отменена.")


def register():
	return router
