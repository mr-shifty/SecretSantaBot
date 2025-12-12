import json
from datetime import datetime
from typing import List, Tuple
from sqlalchemy import select
from bot.db.models import User, Route1Entry, Route2Entry, Assignment


async def build_assignment_notification(session, giver_assignments: List[Assignment]) -> Tuple[str, List[str]]:
    """Build combined send_text and list of button texts for given assignments.

    Returns (send_text, button_texts)
    """
    parts = []
    buttons = []

    # Helper to format survey dict/list
    def format_survey_obj(srv):
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
                return "\n".join([f"{labels.get(k,k)}: {v}" for k, v in srv.items()])
            else:
                return str(srv)
        except Exception:
            return str(srv)

    for a in giver_assignments:
        # load receiver
        res = await session.execute(select(User).where(User.id == a.receiver_user_id))
        receiver = res.scalar_one_or_none()

        # load appropriate entry
        if a.route_type == 1:
            res = await session.execute(
                select(Route1Entry).where(Route1Entry.user_id == a.receiver_user_id).where(Route1Entry.status == 'completed')
            )
            rentry = res.scalar_one_or_none()
        else:
            res = await session.execute(
                select(Route2Entry).where(Route2Entry.user_id == a.receiver_user_id).where(Route2Entry.status == 'completed')
            )
            rentry = res.scalar_one_or_none()

        recv_name = receiver.telegram_username or f"{receiver.first_name or ''} {receiver.last_name or ''}" if receiver else 'Получатель'

        # build wishlist / survey
        wishlist = 'Пожелания отсутствуют'
        if a.route_type == 1 and rentry:
            if getattr(rentry, 'survey', None):
                survey_obj = None
                if isinstance(rentry.survey, (dict, list)):
                    survey_obj = rentry.survey
                else:
                    try:
                        survey_obj = json.loads(rentry.survey)
                    except Exception:
                        survey_obj = None

                if survey_obj is not None:
                    wishlist = "Анкета:\n" + format_survey_obj(survey_obj)
                else:
                    wishlist = str(rentry.survey)
            elif getattr(rentry, 'wishlist', None):
                wishlist = rentry.wishlist

        delivery = (getattr(rentry, 'full_address', None) or '') if rentry else ''
        if not delivery and rentry and getattr(rentry, 'pickup_company', None):
            delivery = f"Пункт выдачи: {getattr(rentry, 'pickup_company', '')}, {getattr(rentry, 'pickup_address', '') or ''}"
        recipient_phone = ''
        if rentry:
            recipient_phone = getattr(rentry, 'postal_recipient_phone', None) or getattr(rentry, 'pickup_recipient_phone', None) or ''

        if a.route_type == 1:
            # Determine delivery method
            if rentry and getattr(rentry, 'pickup_type', None) == 'postal':
                delivery_method = f"📮 Почта: {getattr(rentry, 'postal_city', '') or ''}, {getattr(rentry, 'postal_street', '') or ''}, д. {getattr(rentry, 'postal_building', '') or ''}"
            else:
                delivery_method = f"🏢 {getattr(rentry, 'pickup_company', '') or 'Пункт выдачи'}: {getattr(rentry, 'pickup_address', '') or ''}"

            part_text = (
                f"<b>Твой адресат выбран! ❄️</b>\n\n"
                f"Ты — Тайный Санта для: @{recv_name} ⛄\n\n"
                f"<b>Пожелания:</b>\n"
                f"{wishlist}\n\n"
                f"<b>Способ доставки:</b>\n"
                f"{delivery_method}\n"
                f"<b>Телефон:</b> {recipient_phone or 'Не указан'}\n\n"
                f"Рекомендуемая сумма для подарка не более 1000 р. 💝\n\n"
                f"Пусть твой подарок станет для кого-то маленьким, но очень важным зимним чудом. 🎄🍪"
            )
            buttons.append('Подарок отправлен')
        else:
            email_addr = getattr(rentry, 'email', '') if rentry else ''
            part_text = (
                f"<b>Твой адресат выбран! 🎁</b>\n\n"
                f"Тебе выпал участник, которому ты присылаешь открытку в рамках Диджитал Санты. ☃️\n"
                f"Вот его анкета и информация для отправки:\n\n"
                f"<b>Имя:</b> @{recv_name}\n"
                f"<b>Почта:</b> {email_addr or 'Не указана'}\n\n"
                f"Пришли открытку до 30.12 на указанный email.\n"
                f"Если захочется уточнить детали или что-то пойдёт не так — просто напиши нам, мы рядом.\n\n"
                f"Пусть твои слова станут для кого-то маленьким, но очень важным зимним чудом. 🍪🎁"
            )
            buttons.append('Поздравление отправлено')

        parts.append(part_text)

    # Combine parts and add possible prefix/suffix
    send_text = "🎁 Розыгрыш завершён — у вас есть получатели!\n\n" + "\n---\n".join(parts)
    return send_text, buttons
