from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from bot.states import Route1States
from bot.utils import get_or_create_user, is_valid_email, save_route1_entry, check_active_route1_entry
from bot.logger import get_logger
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.keyboards import reply_menu
from bot.config import ADMIN_IDS
from aiogram.types import CallbackQuery

logger = get_logger("route1")
router = Router()

@router.message(Command("route1"))
async def cmd_route1(message: Message, state: FSMContext):
	# Check if user already has active entry
	has_active = await check_active_route1_entry(message.from_user.id)
	if has_active:
		logger.info(f"User {message.from_user.id} attempted duplicate route1 registration")
		await message.answer("⚠️ У вас уже есть активная заявка для маршрута 'Тайный Санта (с подарками)'. Одна заявка на маршрут.")
		return
	
	logger.info(f"User {message.from_user.id} started route1 registration")
	await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
	await message.answer("🎁 Добро пожаловать в «Тайный Санта (с подарками)»!\n\nПожалуйста, введите ваш email:")
	await state.set_state(Route1States.email)


@router.message(lambda message: (message.text or "").strip().lower() == "анкета")
async def start_anketa(message: Message, state: FSMContext):
	"""Start survey-only flow (ask minimal contact info then survey)."""
	# Prevent starting if already in an active route1
	has_active = await check_active_route1_entry(message.from_user.id)
	if has_active:
		await message.answer("⚠️ У вас уже есть активная заявка для маршрута 'Тайный Санта (с подарками)'. Если хотите обновить анкету, сначала отмените старую заявку.")
		return

	await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
	# mark that this flow is survey-only
	await state.update_data(survey_only=True)
	await message.answer("Вы начали заполнение анкеты Тайного Санты. Сначала укажите ваш email:")
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

	# If this flow was started as survey-only, jump to survey questions
	data = await state.get_data()
	if data.get('survey_only'):
		await message.answer("Вы выбрали заполнение анкеты. Отвечайте кратко на вопросы.")
		# Send buttons for q1
		kb = InlineKeyboardMarkup(inline_keyboard=[
			[InlineKeyboardButton(text="Красный", callback_data="s1:Красный"), InlineKeyboardButton(text="Синий", callback_data="s1:Синий")],
			[InlineKeyboardButton(text="Зеленый", callback_data="s1:Зеленый"), InlineKeyboardButton(text="Другое", callback_data="s1:other")],
		])
		await message.answer("1) Какой ваш любимый цвет? Выберите вариант или напишите свой:", reply_markup=kb)
		await state.set_state(Route1States.survey_q1)
		return
	
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
		# Offer quick choices for common delivery companies or allow manual entry
		kb = InlineKeyboardMarkup(inline_keyboard=[
			[InlineKeyboardButton(text="СДЭК", callback_data="pc:СДЭК"), InlineKeyboardButton(text="Яндекс.Карго", callback_data="pc:Яндекс.Карго")],
			[InlineKeyboardButton(text="Boxberry", callback_data="pc:Boxberry"), InlineKeyboardButton(text="DPD", callback_data="pc:DPD")],
			[InlineKeyboardButton(text="Другое", callback_data="pc:other")],
		])
		await message.answer("🏢 Вы выбрали пункт выдачи. Выберите компанию доставки или укажите вручную:", reply_markup=kb)
		await state.update_data(pickup_type=pickup_type)
		await state.set_state(Route1States.pickup_company_choice)
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
	# Offer to reuse user's phone or enter a new one
	kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Оставить свой номер")]], resize_keyboard=True, one_time_keyboard=True)
	await message.answer("Телефон получателя (для курьера/почты). Напишите номер или нажмите 'Оставить свой номер':", reply_markup=kb)
	await state.set_state(Route1States.postal_phone)

@router.message(Route1States.postal_phone)
async def process_postal_phone(message: Message, state: FSMContext):
	text = (message.text or "").strip()
	data = await state.get_data()
	if text == "Оставить свой номер":
		phone = data.get('phone')
	else:
		phone = text
	if not phone:
		await message.answer("❌ Телефон получателя обязателен. Укажите номер:")
		return
	await state.update_data(postal_phone=phone)
	# Offer survey option if user doesn't know what to write
	kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Заполнить анкету")]], resize_keyboard=True, one_time_keyboard=True)
	await message.answer("Напишите ваши пожелания к подарку (что вы хотели бы получить).\nЕсли не знаете — нажмите кнопку 'Заполнить анкету' или напишите 'Анкета':", reply_markup=kb)
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


# Handle quick-selection callbacks for pickup company
@router.callback_query(lambda c: c.data and c.data.startswith('pc:'))
async def cb_pickup_company(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		# Ask user to input company manually
		await state.set_state(Route1States.pickup_company)
		await callback.message.answer('Пожалуйста, напишите название компании доставки:')
		return
	# Save chosen company and proceed to address
	await state.update_data(pickup_company=val)
	await callback.message.answer(f'Вы выбрали компанию: {val}. Укажите адрес пункта выдачи (полный адрес с индексом):')
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
	kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Оставить свой номер")]], resize_keyboard=True, one_time_keyboard=True)
	await message.answer("Телефон для получения посылки в пункте выдачи. Напишите номер или нажмите 'Оставить свой номер':", reply_markup=kb)
	await state.set_state(Route1States.pickup_phone)

@router.message(Route1States.pickup_phone)
async def process_pickup_phone(message: Message, state: FSMContext):
	text = (message.text or "").strip()
	data = await state.get_data()
	if text == "Оставить свой номер":
		phone = data.get('phone')
	else:
		phone = text
	if not phone:
		await message.answer("❌ Телефон обязателен. Укажите номер:")
		return
	await state.update_data(pickup_phone=phone)
	kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Заполнить анкету")]], resize_keyboard=True, one_time_keyboard=True)
	await message.answer("Напишите ваши пожелания к подарку.\nЕсли не знаете — нажмите кнопку 'Заполнить анкету' или напишите 'Анкета':", reply_markup=kb)
	await state.set_state(Route1States.wishlist)

# ===== WISHLIST (common for both paths) =====
@router.message(Route1States.wishlist)
async def process_wishlist(message: Message, state: FSMContext):
	wishlist = message.text.strip()
	# If user chose to fill survey, start survey flow
	if wishlist.lower() in ("заполнить анкету", "анкета", "не знаю", "не знаю что написать"):
		await message.answer("Вы выбрали заполнение анкеты. Отвечайте кратко на вопросы.")
		# Send buttons for q1
		kb = InlineKeyboardMarkup(inline_keyboard=[
			[InlineKeyboardButton(text="Красный", callback_data="s1:Красный"), InlineKeyboardButton(text="Синий", callback_data="s1:Синий")],
			[InlineKeyboardButton(text="Зеленый", callback_data="s1:Зеленый"), InlineKeyboardButton(text="Другое", callback_data="s1:other")],
		])
		await message.answer("1) Какой ваш любимый цвет? Выберите вариант или напишите свой:", reply_markup=kb)
		await state.set_state(Route1States.survey_q1)
		return

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
			"postal_telegram": message.from_user.username,
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
	
	is_admin = message.from_user.id in ADMIN_IDS
	await message.answer("✅ Спасибо! Ваша регистрация в Тайном Санте успешно сохранена. Ждём вас 21 декабря! 🎄", reply_markup=reply_menu(is_admin=is_admin))
	await state.clear()


# ===== SURVEY HANDLERS =====
@router.message(Route1States.survey_q1)
async def survey_q1(message: Message, state: FSMContext):
	# If user typed an answer (free text), save it and move to q2
	answer = (message.text or "").strip()
	if answer:
		await state.update_data(s_q1=answer)
		# Send buttons for q2
		kb = InlineKeyboardMarkup(inline_keyboard=[
			[InlineKeyboardButton(text="Чтение книг", callback_data="s2:Чтение книг"), InlineKeyboardButton(text="Спорт", callback_data="s2:Спорт")],
			[InlineKeyboardButton(text="Рисование", callback_data="s2:Рисование"), InlineKeyboardButton(text="Путешествия", callback_data="s2:Путешествия")],
			[InlineKeyboardButton(text="Другое", callback_data="s2:other")],
		])
		await message.answer("2) Какой ваш любимый вид деятельности? Выберите вариант или напишите свой:", reply_markup=kb)
		await state.set_state(Route1States.survey_q2)
		return


@router.message(Route1States.survey_q2)
async def survey_q2(message: Message, state: FSMContext):
	# If user typed an answer (free text), save it and move to q3
	answer = (message.text or "").strip()
	if answer:
		await state.update_data(s_q2=answer)
		# Send buttons for q3
		kb = InlineKeyboardMarkup(inline_keyboard=[
			[InlineKeyboardButton(text="Поп", callback_data="s3:Поп"), InlineKeyboardButton(text="Рок", callback_data="s3:Рок")],
			[InlineKeyboardButton(text="Классика", callback_data="s3:Классика"), InlineKeyboardButton(text="Ужасы", callback_data="s3:Ужасы")],
			[InlineKeyboardButton(text="Комедия", callback_data="s3:Комедия"), InlineKeyboardButton(text="Другое", callback_data="s3:other")],
		])
		await message.answer("3) Какой ваш любимый жанр музыки или фильма? Выберите вариант или напишите свой:", reply_markup=kb)
		await state.set_state(Route1States.survey_q3)
		return


@router.message(Route1States.survey_q3)
async def survey_q3(message: Message, state: FSMContext):
	# If user typed an answer (free text), save it and move to q4
	answer = (message.text or "").strip()
	if answer:
		await state.update_data(s_q3=answer)
		await message.answer("4) Есть ли у вас хобби или увлечения? Пожалуйста, опишите:")
		await state.set_state(Route1States.survey_q4)
		return


@router.message(Route1States.survey_q4)
async def survey_q4(message: Message, state: FSMContext):
	answer = message.text.strip()
	await state.update_data(s_q4=answer)
	await message.answer("5) Какой подарок вы бы никогда не хотели получить? Укажите:")
	await state.set_state(Route1States.survey_q5)


@router.message(Route1States.survey_q5)
async def survey_q5(message: Message, state: FSMContext):
	answer = message.text.strip()
	await state.update_data(s_q5=answer)
	await message.answer("6) Какой ваш любимый сладкий или соленый перекус? Укажите:")
	await state.set_state(Route1States.survey_q6)


@router.message(Route1States.survey_q6)
async def survey_q6(message: Message, state: FSMContext):
	answer = message.text.strip()
	await state.update_data(s_q6=answer)
	await message.answer("7) Есть ли у вас любимые бренды или магазины? Укажите:")
	await state.set_state(Route1States.survey_q7)


@router.message(Route1States.survey_q7)
async def survey_q7(message: Message, state: FSMContext):
	answer = message.text.strip()
	await state.update_data(s_q7=answer)
	await message.answer("8) Есть ли у вас аллергии или предпочтения в еде? Укажите:")
	await state.set_state(Route1States.survey_q8)


@router.message(Route1States.survey_q8)
async def survey_q8(message: Message, state: FSMContext):
	answer = message.text.strip()
	await state.update_data(s_q8=answer)

	# Build survey summary and proceed to saving
	data = await state.get_data()
	survey_parts = [
		f"1) Любимый цвет: {data.get('s_q1','')}",
		f"2) Любимый вид деятельности: {data.get('s_q2','')}",
		f"3) Любимый жанр: {data.get('s_q3','')}",
		f"4) Хобби: {data.get('s_q4','')}",
		f"5) Нежелательный подарок: {data.get('s_q5','')}",
		f"6) Любимый перекус: {data.get('s_q6','')}",
		f"7) Любимые бренды/магазины: {data.get('s_q7','')}",
		f"8) Аллергии/предпочтения: {data.get('s_q8','')}",
	]
	wishlist_text = "Анкета Тайного Санты:\n" + "\n".join(survey_parts)

	prev = await state.get_data()
	email = prev.get('email')
	phone = prev.get('phone')
	pickup_type = prev.get('pickup_type')

	# Build structured survey dict
	survey_dict = {
		'favorite_color': data.get('s_q1',''),
		'favorite_activity': data.get('s_q2',''),
		'favorite_genre': data.get('s_q3',''),
		'hobby': data.get('s_q4',''),
		'undesired_gift': data.get('s_q5',''),
		'favorite_snack': data.get('s_q6',''),
		'favorite_brands': data.get('s_q7',''),
		'allergies': data.get('s_q8',''),
	}

	# Build full_address if survey was part of full route1 flow (not survey-only)
	if pickup_type == "postal":
		postal_city = prev.get("postal_city")
		postal_street = prev.get("postal_street")
		postal_building = prev.get("postal_building")
		postal_corpus = prev.get("postal_corpus")
		postal_apartment = prev.get("postal_apartment")
		full_address = f"{postal_city}, {postal_street} д.{postal_building}"
		if postal_corpus:
			full_address += f" корп.{postal_corpus}"
		if postal_apartment:
			full_address += f" кв.{postal_apartment}"
	elif pickup_type == "pickup":
		pickup_company = prev.get("pickup_company")
		pickup_address = prev.get("pickup_address")
		full_address = f"{pickup_company}, {pickup_address}"
	else:
		full_address = "Анкета"

	entry_kwargs = {
		"email": email,
		"phone": phone,
		"wishlist": wishlist_text,
		"pickup_type": pickup_type or "unknown",
		"full_address": full_address,
	}

	if pickup_type == "postal":
		entry_kwargs.update({
			"postal_city": prev.get("postal_city"),
			"postal_street": prev.get("postal_street"),
			"postal_building": prev.get("postal_building"),
			"postal_corpus": prev.get("postal_corpus"),
			"postal_apartment": prev.get("postal_apartment"),
			"postal_recipient_fullname": prev.get("postal_fullname"),
			"postal_recipient_phone": prev.get("postal_phone"),
			"postal_telegram": message.from_user.username,
		})
	elif pickup_type == "pickup":
		entry_kwargs.update({
			"pickup_company": prev.get("pickup_company"),
			"pickup_address": prev.get("pickup_address"),
			"pickup_recipient_fullname": prev.get("pickup_fullname"),
			"pickup_recipient_phone": prev.get("pickup_phone"),
		})

	await save_route1_entry(message.from_user.id, survey=survey_dict, **entry_kwargs)
	is_admin = message.from_user.id in ADMIN_IDS
	await message.answer("✅ Спасибо! Анкета и регистрация сохранены. Ждём вас 21 декабря! 🎄", reply_markup=reply_menu(is_admin=is_admin))
	await state.clear()


# ---- Callback handlers for quick choices (q1-q3) ----
@router.callback_query(lambda c: c.data and c.data.startswith('s1:'))
async def cb_s1(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await state.set_state(Route1States.survey_q1_other)
		await callback.message.answer('Напишите свой вариант для "Любимый цвет":')
		return
	await state.update_data(s_q1=val)
	await callback.message.answer('2) Какой ваш любимый вид деятельности?')
	await state.set_state(Route1States.survey_q2)


@router.callback_query(lambda c: c.data and c.data.startswith('s2:'))
async def cb_s2(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await state.set_state(Route1States.survey_q2_other)
		await callback.message.answer('Напишите свой вариант для "Вид деятельности":')
		return
	await state.update_data(s_q2=val)
	await callback.message.answer('3) Какой ваш любимый жанр музыки или фильма?')
	await state.set_state(Route1States.survey_q3)


@router.callback_query(lambda c: c.data and c.data.startswith('s3:'))
async def cb_s3(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await state.set_state(Route1States.survey_q3_other)
		await callback.message.answer('Напишите свой вариант для "Жанр":')
		return
	await state.update_data(s_q3=val)
	await callback.message.answer('4) Есть ли у вас хобби или увлечения? Пожалуйста, опишите:')
	await state.set_state(Route1States.survey_q4)


# ---- Handlers for "Другое" free-text after pressing Другое ----
@router.message(Route1States.survey_q1_other)
async def survey_q1_other(message: Message, state: FSMContext):
	answer = (message.text or '').strip()
	if not answer:
		await message.answer('Пожалуйста, введите ваш вариант:')
		return
	await state.update_data(s_q1=answer)
	await message.answer('2) Какой ваш любимый вид деятельности?')
	await state.set_state(Route1States.survey_q2)


@router.message(Route1States.survey_q2_other)
async def survey_q2_other(message: Message, state: FSMContext):
	answer = (message.text or '').strip()
	if not answer:
		await message.answer('Пожалуйста, введите ваш вариант:')
		return
	await state.update_data(s_q2=answer)
	await message.answer('3) Какой ваш любимый жанр музыки или фильма?')
	await state.set_state(Route1States.survey_q3)


@router.message(Route1States.survey_q3_other)
async def survey_q3_other(message: Message, state: FSMContext):
	answer = (message.text or '').strip()
	if not answer:
		await message.answer('Пожалуйста, введите ваш вариант:')
		return
	await state.update_data(s_q3=answer)
	await message.answer('4) Есть ли у вас хобби или увлечения? Пожалуйста, опишите:')
	await state.set_state(Route1States.survey_q4)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
	logger.info(f"User {message.from_user.id} cancelled route1 registration")
	await state.clear()
	await message.answer("❌ Регистрация отменена.")

def register():
	return router
