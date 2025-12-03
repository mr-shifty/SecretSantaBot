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
	await message.answer("🎁 Добро пожаловать в Тайного Санту (Маршрут 1)!\n\nПожалуйста, введите ваш email:")
	await state.set_state(Route1States.email)

@router.message(Route1States.email)
async def process_email(message: Message, state: FSMContext):
	email = message.text.strip()
	if not is_valid_email(email):
		logger.warning(f"User {message.from_user.id} provided invalid email: {email}")
		await message.answer("❌ Неверный формат email. Попробуйте снова:")
		return
	logger.debug(f"User {message.from_user.id} provided valid email: {email}")
	await state.update_data(email=email)
	await message.answer("Введите ваш телефон (обязательно для связи):")
	await state.set_state(Route1States.phone)

@router.message(Route1States.phone)
async def process_phone(message: Message, state: FSMContext):
	phone = message.text.strip()
	if not phone:
		logger.warning(f"User {message.from_user.id} provided empty phone")
		await message.answer("❌ Телефон обязателен. Введите ваш номер:")
		return
	logger.debug(f"User {message.from_user.id} provided phone: {phone}")
	await state.update_data(phone=phone)
	
	# Ask about pickup method
	await message.answer(
		"📦 Выберите способ получения подарка:\n\n"
		"1️⃣ <b>Почта России</b> - отправка по почтовому адресу\n"
		"2️⃣ <b>Пункт выдачи</b> - самовывоз (СДЭК, Яндекс.Карго и т.д.)\n\n"
		"Напишите <b>1</b> или <b>2</b>:",
		parse_mode="HTML"
	)
	await state.set_state(Route1States.pickup_method)

@router.message(Route1States.pickup_method)
async def process_pickup_method(message: Message, state: FSMContext):
	choice = message.text.strip()
	if choice == "1":
		pickup_type = "postal"
		logger.debug(f"User {message.from_user.id} chose postal delivery")
		await message.answer("📮 Вы выбрали доставку Почтой России.\n\nУкажите город:")
		await state.update_data(pickup_type=pickup_type)
		await state.set_state(Route1States.postal_city)
	elif choice == "2":
		pickup_type = "pickup"
		logger.debug(f"User {message.from_user.id} chose pickup point")
		await message.answer("🏢 Вы выбрали пункт выдачи.\n\nУкажите компанию доставки (СДЭК, Яндекс.Карго и т.д.):")
		await state.update_data(pickup_type=pickup_type)
		await state.set_state(Route1States.pickup_company)
	else:
		await message.answer("❌ Пожалуйста, напишите 1 или 2")
		return

# ===== POSTAL DELIVERY PATH =====
@router.message(Route1States.postal_city)
async def process_postal_city(message: Message, state: FSMContext):
	city = message.text.strip()
	if not city:
		await message.answer("❌ Город не может быть пустым. Укажите город:")
		return
	await state.update_data(postal_city=city)
	await message.answer("Укажите улицу:")
	await state.set_state(Route1States.postal_street)

@router.message(Route1States.postal_street)
async def process_postal_street(message: Message, state: FSMContext):
	street = message.text.strip()
	if not street:
		await message.answer("❌ Улица не может быть пустой. Укажите улицу:")
		return
	await state.update_data(postal_street=street)
	await message.answer("Укажите номер дома:")
	await state.set_state(Route1States.postal_building)

@router.message(Route1States.postal_building)
async def process_postal_building(message: Message, state: FSMContext):
	building = message.text.strip()
	if not building:
		await message.answer("❌ Номер дома не может быть пустым. Укажите номер дома:")
		return
	await state.update_data(postal_building=building)
	await message.answer("Корпус или строение (опционально, или напишите '-'):")
	await state.set_state(Route1States.postal_corpus)

@router.message(Route1States.postal_corpus)
async def process_postal_corpus(message: Message, state: FSMContext):
	corpus = message.text.strip()
	if corpus in ("-", ""):
		corpus = None
	await state.update_data(postal_corpus=corpus)
	await message.answer("Номер квартиры (или опционально напишите '-'):")
	await state.set_state(Route1States.postal_apartment)

@router.message(Route1States.postal_apartment)
async def process_postal_apartment(message: Message, state: FSMContext):
	apartment = message.text.strip()
	if apartment in ("-", ""):
		apartment = None
	await state.update_data(postal_apartment=apartment)
	await message.answer("Ваше полное имя (ФИ или как вас зовут):")
	await state.set_state(Route1States.postal_fullname)

@router.message(Route1States.postal_fullname)
async def process_postal_fullname(message: Message, state: FSMContext):
	fullname = message.text.strip()
	if not fullname:
		await message.answer("❌ ФИ не может быть пусто. Укажите ваше имя:")
		return
	await state.update_data(postal_fullname=fullname)
	await message.answer("Телефон получателя (для курьера/почты):")
	await state.set_state(Route1States.postal_phone)

@router.message(Route1States.postal_phone)
async def process_postal_phone(message: Message, state: FSMContext):
	phone = message.text.strip()
	if not phone:
		await message.answer("❌ Телефон получателя обязателен. Укажите номер:")
		return
	await state.update_data(postal_phone=phone)
	await message.answer("Напишите ваши пожелания к подарку (что вы хотели бы получить):")
	await state.set_state(Route1States.wishlist)

# ===== PICKUP POINT PATH =====
@router.message(Route1States.pickup_company)
async def process_pickup_company(message: Message, state: FSMContext):
	company = message.text.strip()
	if not company:
		await message.answer("❌ Компания не может быть пустой. Укажите компанию доставки:")
		return
	await state.update_data(pickup_company=company)
	await message.answer("Укажите адрес пункта выдачи (полный адрес с индексом):")
	await state.set_state(Route1States.pickup_address)

@router.message(Route1States.pickup_address)
async def process_pickup_address(message: Message, state: FSMContext):
	address = message.text.strip()
	if not address:
		await message.answer("❌ Адрес не может быть пустым. Укажите адрес:")
		return
	await state.update_data(pickup_address=address)
	await message.answer("Ваше полное имя для получения посылки:")
	await state.set_state(Route1States.pickup_fullname)

@router.message(Route1States.pickup_fullname)
async def process_pickup_fullname(message: Message, state: FSMContext):
	fullname = message.text.strip()
	if not fullname:
		await message.answer("❌ ФИ не может быть пусто. Укажите ваше имя:")
		return
	await state.update_data(pickup_fullname=fullname)
	await message.answer("Телефон для получения посылки в пункте выдачи:")
	await state.set_state(Route1States.pickup_phone)

@router.message(Route1States.pickup_phone)
async def process_pickup_phone(message: Message, state: FSMContext):
	phone = message.text.strip()
	if not phone:
		await message.answer("❌ Телефон обязателен. Укажите номер:")
		return
	await state.update_data(pickup_phone=phone)
	await message.answer("Напишите ваши пожелания к подарку:")
	await state.set_state(Route1States.wishlist)

# ===== WISHLIST (common for both paths) =====
@router.message(Route1States.wishlist)
async def process_wishlist(message: Message, state: FSMContext):
	wishlist = message.text.strip()
	if not wishlist:
		logger.warning(f"User {message.from_user.id} provided empty wishlist")
		await message.answer("❌ Пожелания не могут быть пустыми. Напишите ваши пожелания к подарку:")
		return
	
	data = await state.get_data()
	email = data.get("email")
	phone = data.get("phone")
	pickup_type = data.get("pickup_type")
	
	# Build full_address from pickup_type
	if pickup_type == "postal":
		postal_city = data.get("postal_city")
		postal_street = data.get("postal_street")
		postal_building = data.get("postal_building")
		postal_corpus = data.get("postal_corpus")
		postal_apartment = data.get("postal_apartment")
		full_address = f"{postal_city}, {postal_street} д.{postal_building}"
		if postal_corpus:
			full_address += f" корп.{postal_corpus}"
		if postal_apartment:
			full_address += f" кв.{postal_apartment}"
	elif pickup_type == "pickup":
		pickup_company = data.get("pickup_company")
		pickup_address = data.get("pickup_address")
		full_address = f"{pickup_company}, {pickup_address}"
	else:
		full_address = "Unknown"
	
	# Prepare entry data based on pickup_type
	entry_kwargs = {
		"email": email,
		"phone": phone,
		"wishlist": wishlist,
		"pickup_type": pickup_type,
		"full_address": full_address,
	}
	
	if pickup_type == "postal":
		entry_kwargs.update({
			"postal_city": data.get("postal_city"),
			"postal_street": data.get("postal_street"),
			"postal_building": data.get("postal_building"),
			"postal_corpus": data.get("postal_corpus"),
			"postal_apartment": data.get("postal_apartment"),
			"postal_recipient_fullname": data.get("postal_fullname"),
			"postal_recipient_phone": data.get("postal_phone"),
			"postal_telegram": message.from_user.username,  # автоматически собираем username
		})
	elif pickup_type == "pickup":
		entry_kwargs.update({
			"pickup_company": data.get("pickup_company"),
			"pickup_address": data.get("pickup_address"),
			"pickup_recipient_fullname": data.get("pickup_fullname"),
			"pickup_recipient_phone": data.get("pickup_phone"),
		})
	
	logger.info(f"User {message.from_user.id} submitting route1 entry: pickup_type={pickup_type}, email={email}")
	await save_route1_entry(message.from_user.id, **entry_kwargs)
	
	await message.answer("✅ Спасибо! Ваша регистрация в маршруте 1 успешно сохранена. Ждём вас 21 декабря! 🎄")
	await state.clear()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
	logger.info(f"User {message.from_user.id} cancelled route1 registration")
	await state.clear()
	await message.answer("❌ Регистрация отменена.")

def register():
	return router
