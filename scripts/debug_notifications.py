#!/usr/bin/env python3
"""Debug helper: inspect notification fields for entries and users."""
import asyncio
from sqlalchemy import select
from bot.db.database import init_db, get_session
from bot.db.models import User, Route1Entry
from bot.notifications import norm


async def run():
    await init_db()
    s = get_session()
    async with s as sess:
        res = await sess.execute(select(User).where(User.telegram_username == 'mrshifty'))
        u = res.scalar_one_or_none()
        print('User', u and u.id, u and u.telegram_username)
        if u:
            res2 = await sess.execute(select(Route1Entry).where(Route1Entry.user_id == u.id))
            r = res2.scalars().first()
            print('entry id', r.id)
            print('postal_fullname', repr(r.postal_recipient_fullname))
            raw_fullname = norm(r.postal_recipient_fullname)
            if raw_fullname and raw_fullname.startswith('@'):
                raw_fullname = None
            print('raw_fullname', repr(raw_fullname))
            last = norm(r.postal_recipient_last_name)
            first = norm(r.postal_recipient_first_name)
            patr = norm(r.postal_recipient_patronymic)
            fullname = raw_fullname or ' '.join(filter(None, [last, first, patr]))
            print('fullname', repr(fullname))
            receiver_fio = ' '.join(filter(None, [norm(u.first_name), norm(u.last_name)])) or None
            print('receiver_fio', repr(receiver_fio))
            recv_display = f"@{u.telegram_username}" if u.telegram_username else (receiver_fio or 'Получатель')
            print('recv_display', recv_display)
            fio_field = fullname or receiver_fio or 'Не указан'
            print('fio_field', repr(fio_field))
            p_index = norm(r.postal_index)
            print('postal_index', repr(p_index))
            fa = norm(r.full_address)
            print('full_address', repr(fa))
            if not p_index and fa:
                import re
                m = re.match(r"^(\d{5})[\s,]+", fa)
                if m:
                    p_index = m.group(1)
            print('final_p_index', repr(p_index))


if __name__ == '__main__':
    asyncio.run(run())
