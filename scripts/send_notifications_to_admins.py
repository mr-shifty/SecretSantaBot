import asyncio
import json
from datetime import datetime
from aiogram import Bot
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import BOT_TOKEN, ADMIN_IDS
from bot.db.database import get_session, init_db
from bot.db.models import Assignment, User, Route1Entry, NotificationLog
from sqlalchemy import select
from bot.logger import get_logger

logger = get_logger("send_notifications")

async def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN is not set in environment. Aborting.")
        return
    # Initialize DB (creates tables if needed when using sqlite dev)
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    sent_count = 0
    skipped_count = 0
    failed_count = 0

    async_session = get_session()
    async with async_session as session:
        result = await session.execute(select(Assignment).where(Assignment.route_type == 1).where(Assignment.sent_status != 'sent'))
        assignments = result.scalars().all()

    if not assignments:
        print("No pending/failed assignments to notify for route 1.")
        await bot.close()
        return

    for assignment in assignments:
        async_session = get_session()
        async with async_session as session:
            result = await session.execute(select(Assignment).where(Assignment.id == assignment.id))
            # Group assignments by giver so we can send combined previews
            givers_map: dict[int, list[Assignment]] = {}
            for a in assignments:
                givers_map.setdefault(a.giver_user_id, []).append(a)

            for giver_id, giver_assignments in givers_map.items():
                async_session = get_session()
                async with async_session as session:
                    result = await session.execute(select(User).where(User.id == giver_id))
                    giver = result.scalar_one_or_none()
                    if not giver:
                        logger.warning(f"No giver user found for giver_id {giver_id}")
                        continue

                    parts = []
                    buttons = []
                    nlogs_created = []
                    for a in giver_assignments:
                        result = await session.execute(select(User).where(User.id == a.receiver_user_id))
                        receiver = result.scalar_one_or_none()
                        result = await session.execute(
                            select(Route1Entry).where(Route1Entry.user_id == a.receiver_user_id).where(Route1Entry.status == 'completed')
                        ) if a.route_type == 1 else await session.execute(
                            select(Route2Entry).where(Route2Entry.user_id == a.receiver_user_id).where(Route2Entry.status == 'completed')
                        )
                        rentry = result.scalar_one_or_none()

                        recv_name = receiver.telegram_username or f"{receiver.first_name or ''} {receiver.last_name or ''}" if receiver else 'Получатель'
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
                                try:
                                    wishlist = "Анкета:\n" + "\n".join([f"{k}: {v}" for k, v in survey_obj.items()])
                                except Exception:
                                    wishlist = str(survey_obj)
                            else:
                                wishlist = rentry.survey
                        else:
                            wishlist = (rentry.wishlist if rentry and getattr(rentry, 'wishlist', None) else 'Пожелания отсутствуют')

                        delivery = rentry.full_address if (rentry and getattr(rentry, 'full_address', None)) else ''
                        if not delivery and rentry and getattr(rentry, 'pickup_company', None):
                            delivery = f"Пункт выдачи: {rentry.pickup_company}, {getattr(rentry, 'pickup_address', '') or ''}"
                        recipient_phone = ''
                        if rentry:
                            recipient_phone = getattr(rentry, 'postal_recipient_phone', None) or getattr(rentry, 'pickup_recipient_phone', None) or ''

                        # Build part text with requested headers
                        if a.route_type == 1:
                            header = f"Ваш тайный санта найден: {('@' + receiver.telegram_username) if receiver and receiver.telegram_username else recv_name}\n"
                            part_text = (
                                header +
                                f"Пожелания:\n{wishlist}\n"
                                f"Адрес / пункт выдачи:\n{delivery}\n"
                                f"Телефон: {recipient_phone or 'Не указан'}\n"
                            )
                        else:
                            header = f"Ваш диджитал санта найден: {('@' + receiver.telegram_username) if receiver and receiver.telegram_username else recv_name}\n"
                            part_text = (
                                header +
                                f"Email для поздравления: {getattr(rentry, 'email', '') or 'Не указан'}\n"
                                f"Телефон: {recipient_phone or 'Не указан'}\n"
                            )
                        parts.append(part_text)

                        if a.route_type == 2:
                            buttons.append('Поздравление отправлено')
                        else:
                            buttons.append('Подарок отправлен')

                        nlog = NotificationLog(
                            user_id=giver.id if giver else None,
                            channel='telegram',
                            notif_type='assignment',
                            payload=None,
                            status='pending'
                        )
                        session.add(nlog)
                        await session.commit()
                        nlogs_created.append(nlog)

                    send_text = "🎁 Розыгрыш завершён — у вас есть получатели!\n\n" + "\n---\n".join(parts)
                    for nl in nlogs_created:
                        nl.payload = send_text
                        session.add(nl)

                    if giver.telegram_id not in ADMIN_IDS:
                        logger.info(f"Skipping send to {giver.telegram_id} (not in ADMIN_IDS) — logged only")
                        skipped_count += 1
                        await session.commit()
                        continue

                    # Build inline keyboard with one button per assignment
                    ikb = InlineKeyboardMarkup(inline_keyboard=[])
                    for a in giver_assignments:
                        if a.route_type == 2:
                            btn_text = 'Поздравление отправлено'
                        else:
                            btn_text = 'Подарок отправлен'
                        ikb.inline_keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"mark_sent:{a.id}")])

                    try:
                        await bot.send_message(chat_id=giver.telegram_id, text=send_text, reply_markup=ikb)
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
            await session.commit()

    await bot.close()
    print(f"Done. sent={sent_count}, skipped={skipped_count}, failed={failed_count}")

if __name__ == '__main__':
    asyncio.run(main())
