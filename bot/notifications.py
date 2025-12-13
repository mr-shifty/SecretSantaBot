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

    # Helper to normalize values: treat None or string 'None' (case-insensitive) as None
    def norm(val):
        if val is None:
            return None
        if isinstance(val, str):
            v = val.strip()
            if not v or v.lower() == 'none' or 'none' in v.lower():
                return None
            return v
        return str(val)

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

        # Determine display name for receiver:
        if receiver:
            if getattr(receiver, 'telegram_username', None):
                recv_display = f"@{receiver.telegram_username}"
            else:
                recv_display = ' '.join(filter(None, [getattr(receiver, 'first_name', '') or None, getattr(receiver, 'last_name', '') or None])) or 'Получатель'
        else:
            recv_display = 'Получатель'

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

        delivery = norm(getattr(rentry, 'full_address', None)) or '' if rentry else ''
        if not delivery and rentry and norm(getattr(rentry, 'pickup_company', None)):
            delivery = f"Пункт выдачи: {norm(getattr(rentry, 'pickup_company', None))}, {norm(getattr(rentry, 'pickup_address', None)) or ''}"
        recipient_phone = ''
        if rentry:
            recipient_phone = norm(getattr(rentry, 'postal_recipient_phone', None)) or norm(getattr(rentry, 'pickup_recipient_phone', None)) or ''

        if a.route_type == 1:
            # Determine delivery method
            if rentry and getattr(rentry, 'pickup_type', None) == 'postal':
                # Build formatted postal info per requirements
                last = norm(getattr(rentry, 'postal_recipient_last_name', None))
                first = norm(getattr(rentry, 'postal_recipient_first_name', None))
                patr = norm(getattr(rentry, 'postal_recipient_patronymic', None))
                raw_fullname = norm(getattr(rentry, 'postal_recipient_fullname', None))
                if raw_fullname and raw_fullname.startswith('@'):
                    raw_fullname = None
                fullname = raw_fullname or ' '.join(filter(None, [last, first, patr]))
                # Determine address vs branch
                branch_num = norm(getattr(rentry, 'postal_branch_number', None))
                p_index = norm(getattr(rentry, 'postal_index', None))
                if branch_num:
                    address_line = f"Номер отделения/почтомата: {branch_num}"
                else:
                    # Build address only from non-empty parts
                    addr_components = [norm(getattr(rentry, 'postal_city', None)), norm(getattr(rentry, 'postal_street', None))]
                    house = norm(getattr(rentry, 'postal_building', None))
                    addr = ', '.join([p for p in addr_components if p])
                    if house:
                        if addr:
                            addr = f"{addr}, д. {house}"
                        else:
                            addr = f"д. {house}"
                    address_line = addr or norm(getattr(rentry, 'full_address', None)) or ''
                    # Extra safety: if address_line still contains the literal 'None' tokens, treat as empty
                    if isinstance(address_line, str) and 'none' in address_line.lower():
                        address_line = ''
                delivery_method = f"📮 Почта России"
            else:
                # Compose delivery method text for pickup (CDEK/Yandex/other)
                company = norm(getattr(rentry, 'pickup_company', None)) or 'Пункт выдачи'
                pickup_addr = norm(getattr(rentry, 'pickup_address', None)) or ''
                pickup_point_id = norm(getattr(rentry, 'pickup_point_id', None))
                if pickup_point_id:
                    delivery_method = f"🏢 {company}: {pickup_addr or pickup_point_id}"
                else:
                    delivery_method = f"🏢 {company}: {pickup_addr or ''}"
            # Build notification text that shows requested fields
            if rentry and getattr(rentry, 'pickup_type', None) == 'postal':
                # Postal: show full name, address/branch, index, phone and wishlist
                # Ensure postal index normalized and try to extract from full_address if not present
                p_index = norm(getattr(rentry, 'postal_index', None))
                if not p_index:
                    fa = norm(getattr(rentry, 'full_address', None))
                    if fa:
                        import re
                        m = re.match(r"^(\d{5})[\s,]+", fa)
                        if m:
                            p_index = m.group(1)
                # Use receiver display (telegram username) in the main line if available,
                # but show the postal recipient full name in the 'Фамилия, имя, отчество' field.
                receiver_fio = ' '.join(filter(None, [norm(getattr(receiver, 'first_name', None)), norm(getattr(receiver, 'last_name', None))])) or None
                display_name = recv_display or receiver_fio or 'Получатель'
                fio_field = fullname or receiver_fio or 'Не указан'
                # DEBUG
                # debug prints removed
                part_text = (
                    f"<b>Твой адресат выбран! ❄️</b>\n\n"
                    f"Ты — Тайный Санта для: {display_name} ⛄\n\n"
                    f"<b>Фамилия, имя, отчество (обязательно для получения):</b> {fio_field}\n"
                    f"<b>Точный адрес доставки или номер отделения/почтомата:</b> {address_line or 'Не указан'}\n"
                    f"<b>Почтовый индекс:</b> {p_index or 'Не указан'}\n"
                    f"<b>Номер телефона (для уведомлений):</b> {recipient_phone or 'Не указан'}\n\n"
                    f"<b>Пожелания:</b>\n{wishlist}\n\n"
                    f"Рекомендуемая сумма для подарка не более 1000 р. 💝\n\n"
                    f"Пусть твой подарок станет для кого-то маленьким, но очень важным зимним чудом. 🎄🍪"
                )
            else:
                # For pickup deliveries prefer pickup_index, then postal_index, then try to extract from full_address
                p_index = norm(getattr(rentry, 'pickup_index', None)) or norm(getattr(rentry, 'postal_index', None))
                if not p_index:
                    fa = norm(getattr(rentry, 'full_address', None))
                    if fa:
                        import re
                        m = re.match(r"^(\d{5})[\s,]+", fa)
                        if m:
                            p_index = m.group(1)

                # For pickup flows prefer to show pickup_recipient_fullname if present
                pickup_recipient_fullname = norm(getattr(rentry, 'pickup_recipient_fullname', None))
                fio_field = pickup_recipient_fullname or 'Не указан'
                part_text = (
                    f"<b>Твой адресат выбран! ❄️</b>\n\n"
                    f"Ты — Тайный Санта для: {recv_display} ⛄\n\n"
                    f"<b>Пожелания:</b>\n"
                    f"{wishlist}\n\n"
                    f"<b>Способ доставки:</b>\n"
                    f"{delivery_method}\n"
                    f"<b>Почтовый индекс:</b> {p_index or 'Не указан'}\n"
                    f"<b>Телефон:</b> {recipient_phone or 'Не указан'}\n\n"
                    f"Рекомендуемая сумма для подарка не более 1000 р. 💝\n\n"
                    f"Пусть твой подарок станет для кого-то маленьким, но очень важным зимним чудом. 🎄🍪"
                )
            buttons.append('Подарок отправлен')
        else:
            # Route2 / digital postcards: show email and display name
            email_addr = getattr(rentry, 'email', '') if rentry else ''
            receiver_fio = ' '.join(filter(None, [norm(getattr(receiver, 'first_name', None)), norm(getattr(receiver, 'last_name', None))])) or None
            fio_field = receiver_fio or 'Не указан'
            part_text = (
                f"<b>Твой адресат выбран! 🎁</b>\n\n"
                f"Тебе выпал участник, которому ты присылаешь открытку в рамках Диджитал Санты. ☃️\n"
                f"Вот его анкета и информация для отправки:\n\n"
                f"<b>Имя:</b> {recv_display}\n"
                f"<b>Почта:</b> {email_addr or 'Не указана'}\n\n"
                f"<b>Фамилия, имя, отчество (обязательно для получения):</b> {fio_field}\n\n"
                f"Пришли открытку до 30.12 на указанный email.\n\n"
                f"Пусть твои слова станут для кого-то маленьким, но очень важным зимним чудом. 🍪🎁"
            )
            buttons.append('Поздравление отправлено')

        parts.append('' if part_text is None else str(part_text))

    # Combine parts and add possible prefix/suffix
    send_text = "🎁 Розыгрыш завершён — у вас есть получатели!\n\n" + "\n---\n".join(parts)
    return send_text, buttons
