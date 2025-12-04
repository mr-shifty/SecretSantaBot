from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from bot.states import Route1States
from bot.utils import get_or_create_user, is_valid_email, save_route1_entry, check_active_route1_entry
from bot.logger import get_logger
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

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


@router.message(lambda message: (message.text or "").strip().lower() == "анкета")
async def start_anketa(message: Message, state: FSMContext):
	"""Start survey-only flow (ask minimal contact info then survey)."""
	# Prevent starting if already in an active route1
	has_active = await check_active_route1_entry(message.from_user.id)
	if has_active:
		await message.answer("⚠️ У вас уже есть активная заявка для маршрута 1. Если хотите обновить анкету, сначала отмените старую заявку.")
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
		await message.answer("1) Какой ваш любимый цвет?\n(например: Красный / Синий / Зеленый / Другой)")
		await state.set_state(Route1States.survey_q1)
		return
	
	# Ask about pickup method
	await message.answer(
		"📦 Выберите способ получения подарка:\n\n"
		"1️⃣ <b>Почта России</b> - отправка по почтовому адресу\n"
		"2️⃣ <b>Пункт выдачи</b> - самовывоз (СДЭК, Яндекс-Карго и т.д.)\n\n"
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
		await message.answer("1) Какой ваш любимый цвет?\n(например: Красный / Синий / Зеленый / Другой)")
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


# ===== SURVEY HANDLERS =====
@router.message(Route1States.survey_q1)
async def survey_q1(message: Message, state: FSMContext):
	answer = message.text.strip()
	await state.update_data(s_q1=answer)
	kb = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text='Красный', callback_data='s2:Красный'), InlineKeyboardButton(text='Синий', callback_data='s2:Синий')],
		[InlineKeyboardButton(text='Зелёный', callback_data='s2:Зелёный'), InlineKeyboardButton(text='Жёлтый', callback_data='s2:Жёлтый')],
		[InlineKeyboardButton(text='Фиолетовый', callback_data='s2:Фиолетовый'), InlineKeyboardButton(text='Другой', callback_data='s2:other')],
	])
	await message.answer('2) Какой ваш любимый вид деятельности?', reply_markup=kb)
	await state.set_state(Route1States.survey_q2)


@router.message(Route1States.survey_q2)
async def survey_q2(message: Message, state: FSMContext):
	answer = message.text.strip()
	await state.update_data(s_q2=answer)
	kb = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text='Поп', callback_data='s3:Поп'), InlineKeyboardButton(text='Рок', callback_data='s3:Рок')],
		[InlineKeyboardButton(text='Классика', callback_data='s3:Классика'), InlineKeyboardButton(text='Ужасы', callback_data='s3:Ужасы')],
		[InlineKeyboardButton(text='Комедия', callback_data='s3:Комедия'), InlineKeyboardButton(text='Другой', callback_data='s3:other')],
	])
	await message.answer('3) Какой ваш любимый жанр музыки или фильма?', reply_markup=kb)
	await state.set_state(Route1States.survey_q3)


@router.message(Route1States.survey_q3)
async def survey_q3(message: Message, state: FSMContext):
	answer = message.text.strip()
	await state.update_data(s_q3=answer)
	await message.answer("4) Есть ли у вас хобби или увлечения? Пожалуйста, опишите:")
	await state.set_state(Route1States.survey_q4)


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

	# Build survey summary and proceed to saving as wishlist
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

	# reuse same saving logic as wishlist: collect earlier state data
	prev = await state.get_data()
	email = prev.get('email')
	phone = prev.get('phone')
	pickup_type = prev.get('pickup_type')
+
+	# Build structured survey dict to store as JSON
+	survey_dict = {
+		'favorite_color': data.get('s_q1',''),
+		'favorite_activity': data.get('s_q2',''),
+		'favorite_genre': data.get('s_q3',''),
+		'hobby': data.get('s_q4',''),
+		'undesired_gift': data.get('s_q5',''),
+		'favorite_snack': data.get('s_q6',''),
+		'favorite_brands': data.get('s_q7',''),
+		'allergies': data.get('s_q8',''),
+	}

	# Build full_address similar to normal flow
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
		full_address = "Unknown"

	entry_kwargs = {
		"email": email,
		"phone": phone,
		"wishlist": wishlist_text,
		"pickup_type": pickup_type,
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
	await message.answer("✅ Спасибо! Анкета и регистрация сохранены. Ждём вас 21 декабря! 🎄")
	await state.clear()


@router.callback_query(lambda c: c.data.startswith('s1:'))
async def cb_survey_q1(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	# Only proceed if user in survey_q1
	cur = await state.get_state()
	if cur != Route1States.survey_q1.state:
		return
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await callback.message.answer('Напишите ваш любимый цвет (свой вариант):')
		await state.set_state(Route1States.survey_q1)
		return
	await state.update_data(s_q1=val)
	# Ask next question with inline options
	kb = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text='Чтение книг', callback_data='s2:Чтение книг'), InlineKeyboardButton(text='Спорт', callback_data='s2:Спорт')],
		[InlineKeyboardButton(text='Рисование/Творчество', callback_data='s2:Рисование/Творчество'), InlineKeyboardButton(text='Путешествия', callback_data='s2:Путешествия')],
		[InlineKeyboardButton(text='Другой', callback_data='s2:other')],
	])
	await callback.message.answer('2) Какой ваш любимый вид деятельности?', reply_markup=kb)
	await state.set_state(Route1States.survey_q2)


@router.callback_query(lambda c: c.data.startswith('s2:'))
async def cb_survey_q2(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	cur = await state.get_state()
	if cur != Route1States.survey_q2.state:
		return
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await callback.message.answer('Напишите ваш любимый вид деятельности (свой вариант):')
		await state.set_state(Route1States.survey_q2)
		return
	await state.update_data(s_q2=val)
	# Ask next question with inline options
	kb = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text='Поп', callback_data='s3:Поп'), InlineKeyboardButton(text='Рок', callback_data='s3:Рок')],
		[InlineKeyboardButton(text='Классика', callback_data='s3:Классика'), InlineKeyboardButton(text='Ужасы', callback_data='s3:Ужасы')],
		[InlineKeyboardButton(text='Комедия', callback_data='s3:Комедия'), InlineKeyboardButton(text='Другой', callback_data='s3:other')],
	])
	await callback.message.answer('3) Какой ваш любимый жанр музыки или фильма?', reply_markup=kb)
	await state.set_state(Route1States.survey_q3)


@router.callback_query(lambda c: c.data.startswith('s3:'))
async def cb_survey_q3(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	cur = await state.get_state()
	if cur != Route1States.survey_q3.state:
		return
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await callback.message.answer('Напишите ваш любимый жанр (свой вариант):')
		await state.set_state(Route1States.survey_q3)
		return
	await state.update_data(s_q3=val)
	# proceed to question 4 with inline options
	kb = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text='Чтение', callback_data='s4:Чтение'), InlineKeyboardButton(text='Спорт', callback_data='s4:Спорт')],
		[InlineKeyboardButton(text='Творчество', callback_data='s4:Творчество'), InlineKeyboardButton(text='Видеоигры', callback_data='s4:Видеоигры')],
		[InlineKeyboardButton(text='Готовка', callback_data='s4:Готовка'), InlineKeyboardButton(text='Путешествия', callback_data='s4:Путешествия')],
		[InlineKeyboardButton(text='Другое', callback_data='s4:other')],
	])
	await callback.message.answer('4) Есть ли у вас хобби или увлечения? Выберите или напишите:',reply_markup=kb)
	await state.set_state(Route1States.survey_q4)


@router.callback_query(lambda c: c.data.startswith('s4:'))
async def cb_survey_q4(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	cur = await state.get_state()
	if cur != Route1States.survey_q4.state:
		return
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await callback.message.answer('Напишите ваше хобби (свой вариант):')
		await state.set_state(Route1States.survey_q4)
		return
	await state.update_data(s_q4=val)
	# Ask Q5 with inline options
	kb = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text='Носки', callback_data='s5:Носки'), InlineKeyboardButton(text='Игрушки', callback_data='s5:Игрушки')],
		[InlineKeyboardButton(text='Электроника', callback_data='s5:Электроника'), InlineKeyboardButton(text='Косметика', callback_data='s5:Косметика')],
		[InlineKeyboardButton(text='Одежда', callback_data='s5:Одежда'), InlineKeyboardButton(text='Другое', callback_data='s5:other')],
	])
	await callback.message.answer('5) Какой подарок вы бы никогда не хотели получить?', reply_markup=kb)
	await state.set_state(Route1States.survey_q5)


@router.callback_query(lambda c: c.data.startswith('s5:'))
async def cb_survey_q5(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	cur = await state.get_state()
	if cur != Route1States.survey_q5.state:
		return
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await callback.message.answer('Напишите нежелательный подарок (свой вариант):')
		await state.set_state(Route1States.survey_q5)
		return
	await state.update_data(s_q5=val)
	# Ask Q6 with inline options
	kb = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text='Чипсы/Сухарики', callback_data='s6:Чипсы/Сухарики'), InlineKeyboardButton(text='Шоколад/Конфеты', callback_data='s6:Шоколад/Конфеты')],
		[InlineKeyboardButton(text='Орехи', callback_data='s6:Орехи'), InlineKeyboardButton(text='Фрукты', callback_data='s6:Фрукты')],
		[InlineKeyboardButton(text='Печенье', callback_data='s6:Печенье'), InlineKeyboardButton(text='Другое', callback_data='s6:other')],
	])
	await callback.message.answer('6) Какой ваш любимый сладкий или соленый перекус?', reply_markup=kb)
	await state.set_state(Route1States.survey_q6)


@router.callback_query(lambda c: c.data.startswith('s6:'))
async def cb_survey_q6(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	cur = await state.get_state()
	if cur != Route1States.survey_q6.state:
		return
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await callback.message.answer('Напишите ваш перекус (свой вариант):')
		await state.set_state(Route1States.survey_q6)
		return
	await state.update_data(s_q6=val)
	# Ask Q7 with inline options
	kb = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text='IKEA', callback_data='s7:IKEA'), InlineKeyboardButton(text='Decathlon', callback_data='s7:Decathlon')],
		[InlineKeyboardButton(text='Lush', callback_data='s7:Lush'), InlineKeyboardButton(text='Aliexpress', callback_data='s7:Aliexpress')],
		[InlineKeyboardButton(text='Marks & Spencer', callback_data='s7:Marks & Spencer'), InlineKeyboardButton(text='Другое', callback_data='s7:other')],
	])
	await callback.message.answer('7) Есть ли у вас любимые бренды или магазины?', reply_markup=kb)
	await state.set_state(Route1States.survey_q7)


@router.callback_query(lambda c: c.data.startswith('s7:'))
async def cb_survey_q7(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	cur = await state.get_state()
	if cur != Route1States.survey_q7.state:
		return
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await callback.message.answer('Напишите ваши любимые бренды/магазины (свой вариант):')
		await state.set_state(Route1States.survey_q7)
		return
	await state.update_data(s_q7=val)
	# Ask Q8 with inline options
	kb = InlineKeyboardMarkup(inline_keyboard=[
		[InlineKeyboardButton(text='Нет', callback_data='s8:Нет'), InlineKeyboardButton(text='Лактоза', callback_data='s8:Лактоза')],
		[InlineKeyboardButton(text='Глютен', callback_data='s8:Глютен'), InlineKeyboardButton(text='Орехи', callback_data='s8:Орехи')],
		[InlineKeyboardButton(text='Морепродукты', callback_data='s8:Морепродукты'), InlineKeyboardButton(text='Другое', callback_data='s8:other')],
	])
	await callback.message.answer('8) Есть ли у вас аллергии или предпочтения в еде?', reply_markup=kb)
	await state.set_state(Route1States.survey_q8)


@router.callback_query(lambda c: c.data.startswith('s8:'))
async def cb_survey_q8(callback: CallbackQuery, state: FSMContext):
	await callback.answer()
	cur = await state.get_state()
	if cur != Route1States.survey_q8.state:
		return
	val = callback.data.split(':', 1)[1]
	if val == 'other':
		await callback.message.answer('Напишите ваши аллергии/предпочтения (свой вариант):')
		await state.set_state(Route1States.survey_q8)
		return
	await state.update_data(s_q8=val)

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
			"postal_telegram": callback.from_user.username,
		})
	elif pickup_type == "pickup":
		entry_kwargs.update({
			"pickup_company": prev.get("pickup_company"),
			"pickup_address": prev.get("pickup_address"),
			"pickup_recipient_fullname": prev.get("pickup_fullname"),
			"pickup_recipient_phone": prev.get("pickup_phone"),
		})

	await save_route1_entry(callback.from_user.id, survey=survey_dict, **entry_kwargs)
	await callback.message.answer("✅ Спасибо! Анкета и регистрация сохранены. Ждём вас 21 декабря! 🎄")
	await state.clear()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
	logger.info(f"User {message.from_user.id} cancelled route1 registration")
	await state.clear()
	await message.answer("❌ Регистрация отменена.")

def register():
	return router
