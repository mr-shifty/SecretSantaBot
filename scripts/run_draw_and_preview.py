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

    # Build combined previews per giver using the shared helper
    previews = []
    async_session = get_session()
    async with async_session as session:
        givers_map: dict[int, list] = {}
        for a in assignments:
            givers_map.setdefault(a.giver_user_id, []).append(a)
        for giver_id, giver_assignments in givers_map.items():
            res = await session.execute(select(User).where(User.id == giver_id))
            giver = res.scalar_one_or_none()
            send_text, buttons = await build_assignment_notification(session, giver_assignments)
            previews.append({'giver_telegram_id': giver.telegram_id if giver else None, 'text': send_text})

    # Print previews
    for p in previews:
        print('---')
        print(f"Preview for giver @{p['giver_telegram_id']}")
        print(p['text'])

    print(f"Total previews: {len(previews)}")


async def main():
    await init_db()
    created = await ensure_sample_entries()
    await preview_notifications(route=1)


if __name__ == '__main__':
    asyncio.run(main())
