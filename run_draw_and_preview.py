"""Smoke script: perform draw for route1 and print notification previews (no sending).

Usage: .venv/bin/python scripts/run_draw_and_preview.py
"""
import asyncio
from bot.db.database import init_db, get_session
from bot.randomizer import perform_draw
from bot.db.models import User, Route1Entry, Assignment
from sqlalchemy import select
import json
from bot.logger import get_logger

logger = get_logger("smoke")


async def ensure_sample_entries():
    async_session = get_session()
    async with async_session as session:
        # count completed route1 entries
        result = await session.execute(select(Route1Entry).where(Route1Entry.status == 'completed'))
        entries = result.scalars().all()
        if len(entries) >= 2:
            logger.info(f"Found {len(entries)} existing completed Route1 entries, OK")
            return False

        # create two sample users and entries
        u1 = User(telegram_id=999001, telegram_username='test_user1', first_name='Test1')
        u2 = User(telegram_id=999002, telegram_username='test_user2', first_name='Test2')
        session.add_all([u1, u2])
        await session.commit()
        await session.refresh(u1)
        await session.refresh(u2)

        e1 = Route1Entry(user_id=u1.id, email='t1@example.com', wishlist='Люблю книги', status='completed', pickup_type='postal', postal_city='CityA', postal_street='Main', postal_building='1')
        e2 = Route1Entry(user_id=u2.id, email='t2@example.com', wishlist='Люблю чай', status='completed', pickup_type='postal', postal_city='CityB', postal_street='Side', postal_building='2')
        session.add_all([e1, e2])
        await session.commit()
        logger.info('Created 2 sample users and route1 entries')
        return True


async def preview_notifications(route=1):
    # Perform draw
    success, msg, count = await perform_draw(route)
    logger.info(f"perform_draw -> success={success}, msg={msg}, count={count}")

    # Query assignments
    async_session = get_session()
    async with async_session as session:
        result = await session.execute(select(Assignment).where(Assignment.route_type == route))
        assignments = result.scalars().all()

    previews = []
    async_session = get_session()
    async with async_session as session:
        for a in assignments:
            res = await session.execute(select(User).where(User.id == a.giver_user_id))
            giver = res.scalar_one_or_none()
            res = await session.execute(select(User).where(User.id == a.receiver_user_id))
            receiver = res.scalar_one_or_none()
            res = await session.execute(select(Route1Entry).where(Route1Entry.user_id == a.receiver_user_id).where(Route1Entry.status == 'completed'))
            rentry = res.scalar_one_or_none()

            recv_name = receiver.telegram_username or f"{receiver.first_name or ''} {receiver.last_name or ''}" if receiver else 'Получатель'
            # choose survey if present
            wishlist = 'Пожелания отсутствуют'
            if rentry:
                if rentry.survey:
                    if isinstance(rentry.survey, (dict, list)):
                        wishlist = 'Анкета:\n' + '\n'.join([f"{k}: {v}" for k, v in rentry.survey.items()])
                    else:
                        try:
                            obj = json.loads(rentry.survey)
                            wishlist = 'Анкета:\n' + '\n'.join([f"{k}: {v}" for k, v in obj.items()])
                        except Exception:
                            wishlist = rentry.survey
                elif rentry.wishlist:
                    wishlist = rentry.wishlist

            delivery = rentry.full_address if (rentry and rentry.full_address) else ''
            if not delivery and rentry and rentry.pickup_company:
                delivery = f"Пункт выдачи: {rentry.pickup_company}, {rentry.pickup_address or ''}"
            recipient_phone = ''
            if rentry:
                recipient_phone = rentry.postal_recipient_phone or rentry.pickup_recipient_phone or ''

            # Determine delivery method for display
            if rentry and rentry.pickup_type == 'postal':
                delivery_method = f"📮 Почта: {rentry.postal_city or ''}, {rentry.postal_street or ''}, д. {rentry.postal_building or ''}"
            else:
                delivery_method = f"🏢 {rentry.pickup_company or 'Пункт выдачи'}: {rentry.pickup_address or ''}"

            text = (
                f"<b>Твой адресат выбран! ❄️</b>\n\n"
                f"Ты — Тайный Санта для: {recv_name} ⛄\n\n"
                f"<b>Пожелания:</b>\n"
                f"{wishlist}\n\n"
                f"<b>Способ доставки:</b>\n"
                f"{delivery_method}\n"
                f"<b>Телефон:</b> {recipient_phone or 'Не указан'}\n\n"
                f"Рекомендуемая сумма для подарка не более 1000 р. 💝\n\n"
                f"Пусть твой подарок станет для кого-то маленьким, но очень важным зимним чудом. 🎄🍪"
            )
            previews.append({'assignment_id': a.id, 'giver_telegram_id': giver.telegram_id if giver else None, 'text': text})

    # Print previews
    for p in previews:
        print('---')
        print(f"Assignment {p['assignment_id']} -> giver @{p['giver_telegram_id']}")
        print(p['text'])

    print(f"Total previews: {len(previews)}")


async def main():
    await init_db()
    created = await ensure_sample_entries()
    await preview_notifications(route=1)


if __name__ == '__main__':
    asyncio.run(main())
