import asyncio
import json
from datetime import datetime
from aiogram import Bot
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
            db_assignment = result.scalar_one_or_none()

            result = await session.execute(select(User).where(User.id == db_assignment.giver_user_id))
            giver = result.scalar_one_or_none()
            result = await session.execute(select(User).where(User.id == db_assignment.receiver_user_id))
            receiver = result.scalar_one_or_none()
            result = await session.execute(
                select(Route1Entry).where(Route1Entry.user_id == db_assignment.receiver_user_id).where(Route1Entry.status == 'completed')
            )
            rentry = result.scalar_one_or_none()

            if not giver:
                logger.warning(f"No giver user found for assignment {assignment.id}")
                continue

            recv_name = receiver.telegram_username or f"{receiver.first_name or ''} {receiver.last_name or ''}" if receiver else 'Получатель'
            if rentry and rentry.survey:
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
                wishlist = (rentry.wishlist if rentry and rentry.wishlist else 'Пожелания отсутствуют')
            delivery = rentry.full_address if (rentry and rentry.full_address) else ''
            if not delivery and rentry and rentry.pickup_company:
                delivery = f"Пункт выдачи: {rentry.pickup_company}, {rentry.pickup_address or ''}"
            recipient_phone = ''
            if rentry:
                recipient_phone = rentry.postal_recipient_phone or rentry.pickup_recipient_phone or ''

            text = (
                f"🎁 Розыгрыш завершён — у вас есть получатель!\n\n"
                f"Вы — Тайный Санта для: {recv_name}\n\n"
                f"Пожелания:\n{wishlist}\n\n"
                f"Адрес / пункт выдачи:\n{delivery}\n"
                f"Телефон получателя: {recipient_phone}\n\n"
                f"Рекомендуемая сумма для подарка не более 1000 р.\n"
            )

            nlog = NotificationLog(
                user_id=giver.id if giver else None,
                channel='telegram',
                notif_type='assignment',
                payload=text,
                status='pending'
            )
            session.add(nlog)
            await session.commit()

            if giver.telegram_id not in ADMIN_IDS:
                logger.info(f"Skipping send to {giver.telegram_id} (not in ADMIN_IDS) — logged only")
                skipped_count += 1
                continue

            try:
                await bot.send_message(chat_id=giver.telegram_id, text=text)
                nlog.status = 'sent'
                nlog.sent_at = datetime.utcnow()
                db_assignment.sent_status = 'sent'
                sent_count += 1
            except Exception as exc:
                logger.exception(f"Failed to send notification for assignment {assignment.id}: {exc}")
                nlog.status = 'failed'
                db_assignment.sent_status = 'failed'
                failed_count += 1

            session.add(nlog)
            session.add(db_assignment)
            await session.commit()

    await bot.close()
    print(f"Done. sent={sent_count}, skipped={skipped_count}, failed={failed_count}")

if __name__ == '__main__':
    asyncio.run(main())
