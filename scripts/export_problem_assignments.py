"""Экспорт назначений (Assignment), где отсутствует giver или receiver в таблице users.
Записывает CSV `artifacts/problem_assignments.csv` с подробной информацией по каждой проблемной записи.

Запуск:
  python3 scripts/export_problem_assignments.py
"""
import asyncio
import csv
import os
from bot.db.database import get_session, init_db
from bot.db.models import Assignment, User, Route1Entry, Route2Entry
from sqlalchemy import select

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'artifacts')
OUT_FILE = os.path.join(OUT_DIR, 'problem_assignments.csv')

async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        await init_db()
    except Exception:
        pass

    async_session = get_session()
    async with async_session as session:
        result = await session.execute(select(Assignment))
        assignments = result.scalars().all()

    if not assignments:
        print('No assignments found.')
        return

    rows = []
    async_session = get_session()
    async with async_session as session:
        for a in assignments:
            result = await session.execute(select(User).where(User.id == a.giver_user_id))
            giver = result.scalar_one_or_none()
            result = await session.execute(select(User).where(User.id == a.receiver_user_id))
            receiver = result.scalar_one_or_none()

            if giver and receiver:
                continue

            # try to fetch route entries for additional context
            result = await session.execute(select(Route1Entry).where(Route1Entry.user_id == a.giver_user_id))
            giver_r1 = result.scalar_one_or_none()
            result = await session.execute(select(Route2Entry).where(Route2Entry.user_id == a.giver_user_id))
            giver_r2 = result.scalar_one_or_none()

            result = await session.execute(select(Route1Entry).where(Route1Entry.user_id == a.receiver_user_id))
            receiver_r1 = result.scalar_one_or_none()
            result = await session.execute(select(Route2Entry).where(Route2Entry.user_id == a.receiver_user_id))
            receiver_r2 = result.scalar_one_or_none()

            rows.append({
                'assignment_id': a.id,
                'route_type': a.route_type,
                'giver_user_id': a.giver_user_id,
                'giver_telegram_id': getattr(giver, 'telegram_id', ''),
                'giver_email': getattr(giver_r1, 'email', '') if giver_r1 else (getattr(giver_r2, 'email', '') if giver_r2 else ''),
                'giver_wishlist': getattr(giver_r1, 'wishlist', '') if giver_r1 else '',
                'receiver_user_id': a.receiver_user_id,
                'receiver_telegram_id': getattr(receiver, 'telegram_id', ''),
                'receiver_email': getattr(receiver_r1, 'email', '') if receiver_r1 else (getattr(receiver_r2, 'email', '') if receiver_r2 else ''),
                'receiver_wishlist': getattr(receiver_r1, 'wishlist', '') if receiver_r1 else '',
                'assigned_at': getattr(a, 'assigned_at', ''),
                'sent_status': getattr(a, 'sent_status', ''),
            })

    if not rows:
        print('No problematic assignments found (all have users).')
        return

    with open(OUT_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f'Wrote {len(rows)} problematic assignments to {OUT_FILE}')

if __name__ == '__main__':
    asyncio.run(main())
