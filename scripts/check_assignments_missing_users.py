"""Скрипт: проверяет записи Assignment и сообщает о назначениях,
у которых отсутствует соответствующий User (giver или receiver).

Запуск:
  $ python scripts/check_assignments_missing_users.py

Не пытается ничего отправлять, только выводит информацию для диагностики.
"""
import asyncio
from bot.db.database import get_session, init_db
from bot.db.models import Assignment, User
from sqlalchemy import select


async def main():
    # Ensure DB and models are ready
    try:
        await init_db()
    except Exception:
        pass

    async_session = get_session()
    async with async_session as session:
        result = await session.execute(select(Assignment))
        assignments = result.scalars().all()

    if not assignments:
        print("No assignments found.")
        return

    missing = []
    async_session = get_session()
    async with async_session as session:
        for a in assignments:
            result = await session.execute(select(User).where(User.id == a.giver_user_id))
            giver = result.scalar_one_or_none()
            result = await session.execute(select(User).where(User.id == a.receiver_user_id))
            receiver = result.scalar_one_or_none()
            if not giver or not receiver:
                missing.append((a.id, a.giver_user_id, getattr(giver, 'telegram_id', None), a.receiver_user_id, getattr(receiver, 'telegram_id', None)))

    if not missing:
        print("All assignments have both giver and receiver users present.")
    else:
        print("Assignments with missing users (assignment_id, giver_user_id, giver.telegram_id, receiver_user_id, receiver.telegram_id):")
        for row in missing:
            print(row)

if __name__ == '__main__':
    asyncio.run(main())
