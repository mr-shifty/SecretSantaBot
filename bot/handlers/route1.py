from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from bot.states import Route1States
from bot.utils import get_or_create_user, is_valid_email, save_route1_entry, check_active_route1_entry
from bot.logger import get_logger

logger = get_logger("route1")
router = Router()

@router.message(Command("route1"))
async def cmd_route1(message: Message, state: FSMContext):
	# Check if user already has active entry
	has_active = await check_active_route1_entry(message.from_user.id)
	if has_active:
		logger.info(f"User {message.from_user.id} attempted duplicate route1 registration")
		await message.answer("⚠️ У вас уже есть активная заявка для маршрута 1. Одна заявка на маршрут.")
		return
	
	logger.info(f"User {message.from_user.id} started route1 registration")
	await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
	await message.answer("Вы начали регистрацию для маршрута 1. Пожалуйста, введите ваш email:")
	await state.set_state(Route1States.email)

@router.message(Route1States.email)
async def process_email(message: Message, state: FSMContext):
	email = message.text.strip()
	if not is_valid_email(email):
		logger.warning(f"User {message.from_user.id} provided invalid email: {email}")
		await message.answer("Неверный формат email. Попробуйте снова:")
		return
	logger.debug(f"User {message.from_user.id} provided valid email: {email}")
	await state.update_data(email=email)
	await message.answer("Введите ваш телефон (опционально) или напишите 'пропустить':")
	await state.set_state(Route1States.phone)

@router.message(Route1States.phone)
async def process_phone(message: Message, state: FSMContext):
	text = (message.text or "").strip()
	if text.lower() in ("пропустить", "skip", "нет", "-"):
		phone = None
	else:
		phone = text
	await state.update_data(phone=phone)
	await message.answer("Укажите полный адрес доставки (улица, дом, квартира):")
	await state.set_state(Route1States.address)


@router.message(Route1States.address)
async def process_address(message: Message, state: FSMContext):
	addr = message.text.strip()
	if not addr:
		logger.warning(f"User {message.from_user.id} provided empty address")
		await message.answer("Адрес не может быть пустым. Введите адрес:")
		return
	logger.debug(f"User {message.from_user.id} provided address: {addr}")
	await state.update_data(address=addr)
	await message.answer("Укажите предпочитаемый способ доставки (например: Почта, Курьер):")
	await state.set_state(Route1States.delivery)

@router.message(Route1States.delivery)
async def process_delivery(message: Message, state: FSMContext):
	delivery = message.text.strip()
	logger.debug(f"User {message.from_user.id} provided delivery method: {delivery}")
	await state.update_data(delivery=delivery)
	await message.answer("Напишите ваши пожелания к подарку (можно коротко):")
	await state.set_state(Route1States.wishlist)

@router.message(Route1States.wishlist)
async def process_wishlist(message: Message, state: FSMContext):
	wishlist = message.text.strip()
	if not wishlist:
		logger.warning(f"User {message.from_user.id} provided empty wishlist")
		await message.answer("Пожелания не могут быть пустыми. Напишите ваши пожелания к подарку:")
		return
	data = await state.get_data()
	email = data.get("email")
	address = data.get("address")
	delivery = data.get("delivery")
	phone = data.get("phone")

	# basic safety: ensure required fields exist
	if not email or not address:
		logger.error(f"User {message.from_user.id} submitted route1 with missing required fields")
		await message.answer("Похоже, не все поля заполнены. Начните регистрацию снова командой /route1")
		await state.clear()
		return

	logger.info(f"User {message.from_user.id} submitting route1 entry with email: {email}")
	# persist
	await save_route1_entry(message.from_user.id, email, address, delivery, wishlist, phone=phone)
	await message.answer("✅ Ваша регистрация в маршруте 1 успешно сохранена. Спасибо!")
	await state.clear()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
	logger.info(f"User {message.from_user.id} cancelled route1 registration")
	await state.clear()
	await message.answer("Регистрация отменена.")

def register():
	return router
