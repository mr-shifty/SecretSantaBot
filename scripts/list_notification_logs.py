"""List recent NotificationLog entries for debugging.
Run:
  python3 scripts/list_notification_logs.py
"""
import asyncio
from bot.db.database import get_session, init_db
from bot.db.models import NotificationLog, User
from sqlalchemy import select

async def main():
    try:
        await init_db()
    except Exception:
        pass

    async_session = get_session()
    async with async_session as session:
        result = await session.execute(select(NotificationLog).order_by(NotificationLog.id.desc()).limit(100))
        logs = result.scalars().all()

    if not logs:
        print("No notification logs found.")
        return

    print(f"Showing {len(logs)} most recent NotificationLog entries:")
    for l in logs:
        # try to get telegram id for the user if available
        tg = ''
        async_session = get_session()
        async with async_session as session:
            if l.user_id:
                r = await session.execute(select(User).where(User.id == l.user_id))
                u = r.scalar_one_or_none()
                if u:
                    tg = getattr(u, 'telegram_id', '')
        print(f"id={l.id} user_id={l.user_id} telegram_id={tg} channel={l.channel} type={l.notif_type} status={l.status} sent_at={l.sent_at}")
        print(f"  payload: {str(l.payload)[:200]}")

if __name__ == '__main__':
    asyncio.run(main())
