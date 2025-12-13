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
from bot.notifications import build_assignment_notification

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

                    # Use shared helper to build send_text and button labels
                    send_text, buttons = await build_assignment_notification(session, giver_assignments)
                    nlogs_created = []
                    for a in giver_assignments:
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
                        await bot.send_message(chat_id=giver.telegram_id, text=send_text, reply_markup=ikb, parse_mode="HTML")
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
