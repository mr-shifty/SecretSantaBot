from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import ADMIN_IDS


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Return main inline keyboard with route buttons.

    Buttons use callback_data to avoid depending on exact message text.
    """
    buttons = [
        [InlineKeyboardButton(text="Тайный Санта (с подарками)", callback_data="start_route1")],
        [InlineKeyboardButton(text="Диджитал Санта (с поздравлениями)", callback_data="start_route2")],
    ]

    if is_admin:
        buttons.append([InlineKeyboardButton(text="Админ", callback_data="admin_panel")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_menu() -> InlineKeyboardMarkup:
    """Return admin inline keyboard with common admin actions."""
    buttons = [
        [InlineKeyboardButton(text="Розыгрыш: Тайный Санта (с подарками)", callback_data="admin_draw_r1")],
        [InlineKeyboardButton(text="Розыгрыш: Диджитал Санта (с поздравлениями)", callback_data="admin_draw_r2")],
        [InlineKeyboardButton(text="Уведомить: Тайный Санта (с подарками)", callback_data="admin_notify_r1")],
        [InlineKeyboardButton(text="Уведомить: Диджитал Санта (с поздравлениями)", callback_data="admin_notify_r2")],
        # [InlineKeyboardButton(text="Сбросить розыгрыш: Тайный Санта (с подарками)", callback_data="admin_reset_r1")],
        # [InlineKeyboardButton(text="Сбросить розыгрыш: Диджитал Санта (с поздравлениями)", callback_data="admin_reset_r2")],
        # [InlineKeyboardButton(text="Экспорт: С подарками", callback_data="admin_export_r1")],
        # [InlineKeyboardButton(text="Экспорт: С поздравлениями", callback_data="admin_export_r2")],
        [InlineKeyboardButton(text="Закрыть", callback_data="admin_close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def reply_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Return a reply keyboard (buttons at bottom) with route buttons.

    This keyboard is persistent and appears under the input field.
    """
    rows = [
        [KeyboardButton(text="Тайный Санта (с подарками)")],
        [KeyboardButton(text="Диджитал Санта (с поздравлениями)")],
    ]

    # Quick access to the survey for users who don't know what to write
    # rows.append([KeyboardButton(text="Анкета")])

    if is_admin:
        rows.append([KeyboardButton(text="Админ")])

    # One button per row to make them full-width on mobile
    kb = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
    return kb
