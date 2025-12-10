from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.logger import get_logger
from bot.keyboards import main_menu, admin_menu, reply_menu
from bot.utils import is_admin
from bot.utils import get_or_create_user, check_active_route1_entry, check_active_route2_entry
from bot.states import Route1States, Route2States

logger = get_logger("start")
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Send main menu with buttons."""
    is_admin_flag = await is_admin(message.from_user.id)
    logger.info(f"User {message.from_user.id} requested /start (admin={is_admin_flag})")
    # Show reply keyboard (buttons at bottom)
    await message.answer("Выберите маршрут:", reply_markup=reply_menu(is_admin=is_admin_flag))


@router.message(lambda message: (message.text or "").strip().lower() in ("маршрут 1", "регистрация с поздравлениями", "диджитал санта (с поздравлениями)", "диджитал санта"))
async def text_start_route1(message: Message, state: FSMContext):
    user = message.from_user
    has_active = await check_active_route1_entry(user.id)
    if has_active:
        logger.info(f"User {user.id} attempted duplicate route1 via button-text")
        await message.answer("⚠️ У вас уже есть активная заявка для маршрута 'Диджитал Санта (с поздравлениями)'. Одна заявка на маршрут.")
        return

    await get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    logger.info(f"User {user.id} started route1 registration via text button")
    await message.answer("Вы начали регистрацию для 'Диджитал Санта (с поздравлениями)'. Пожалуйста, введите ваш email:")
    await state.set_state(Route1States.email)


@router.message(lambda message: (message.text or "").strip().lower() in ("маршрут 2", "регистрация с подарками", "тайный санта (с подарками)", "тайный санта"))
async def text_start_route2(message: Message, state: FSMContext):
    user = message.from_user
    has_active = await check_active_route2_entry(user.id)
    if has_active:
        logger.info(f"User {user.id} attempted duplicate route2 via button-text")
        await message.answer("⚠️ У вас уже есть активная заявка для маршрута 'Тайный Санта (с подарками)'. Одна заявка на маршрут.")
        return

    await get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    logger.info(f"User {user.id} started route2 registration via text button")
    await message.answer("Вы начали регистрацию для 'Тайный Санта (с подарками)'. Пожалуйста, введите ваш email:")
    await state.set_state(Route2States.email)


@router.message(lambda message: (message.text or "").strip().lower() == "админ")
async def text_admin(message: Message):
    user = message.from_user
    if not await is_admin(user.id):
        logger.warning(f"Non-admin user {user.id} attempted to open admin via text button")
        await message.answer("❌ У вас нет прав администратора")
        return

    logger.info(f"Admin {user.id} opened admin panel via text button")
    await message.answer("Админ-панель:", reply_markup=admin_menu())


@router.callback_query(lambda c: c.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    await callback.answer()
    user = callback.from_user
    if not await is_admin(user.id):
        logger.warning(f"Non-admin user {user.id} attempted to open admin panel")
        await callback.message.answer("❌ У вас нет прав администратора")
        return

    logger.info(f"Admin {user.id} opened admin panel via button")
    await callback.message.answer("Админ-панель:", reply_markup=admin_menu())


@router.callback_query(lambda c: c.data == "start_route1")
async def cb_start_route1(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = callback.from_user
    # duplicate check
    has_active = await check_active_route1_entry(user.id)
    if has_active:
        logger.info(f"User {user.id} attempted duplicate route1 via button")
        await callback.message.answer("⚠️ У вас уже есть активная заявка для маршрута 'Диджитал Санта (с поздравлениями)'. Одна заявка на маршрут.")
        return

    await get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    logger.info(f"User {user.id} started route1 registration via button")
    await callback.message.answer("Вы начали регистрацию для 'Диджитал Санта (с поздравлениями)'. Пожалуйста, введите ваш email:")
    await state.set_state(Route1States.email)


@router.callback_query(lambda c: c.data == "start_route2")
async def cb_start_route2(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    user = callback.from_user
    has_active = await check_active_route2_entry(user.id)
    if has_active:
        logger.info(f"User {user.id} attempted duplicate route2 via button")
        await callback.message.answer("⚠️ У вас уже есть активная заявка для маршрута 'Тайный Санта (с подарками)'. Одна заявка на маршрут.")
        return

    await get_or_create_user(user.id, user.username, user.first_name, user.last_name)
    logger.info(f"User {user.id} started route2 registration via button")
    await callback.message.answer("Вы начали регистрацию для 'Тайный Санта (с подарками)'. Пожалуйста, введите ваш email:")
    await state.set_state(Route2States.email)


def register():
    return router
