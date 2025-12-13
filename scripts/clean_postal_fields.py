"""Simple script to clean 'None' strings from postal fields in route1_entries.

Usage:
  docker compose exec -T bot python scripts/clean_postal_fields.py
  or run locally with proper DB env configured.
"""
import asyncio
from bot.db.database import init_db, get_session
from bot.db.models import Route1Entry
from sqlalchemy import select


def norm(val):
    if val is None:
        return None
    if isinstance(val, str):
        v = val.strip()
        if not v:
            return None
        lowered = v.lower()
        if lowered == 'none' or 'none' in lowered:
            return None
        return v
    return str(val)


async def clean_all(dry_run: bool = True):
    await init_db()
    async_session = get_session()
    updated = 0
    async with async_session as s:
        res = await s.execute(select(Route1Entry))
        rows = res.scalars().all()
        for r in rows:
            changed = False
            # Clean scalar postal fields
            fields = [
                'postal_city', 'postal_street', 'postal_building', 'postal_index',
                'postal_branch_number', 'postal_recipient_last_name', 'postal_recipient_first_name',
                'postal_recipient_patronymic', 'postal_recipient_fullname', 'postal_recipient_phone',
            ]
            for f in fields:
                v = getattr(r, f, None)
                nv = norm(v)
                if (v is None and nv is not None) or (v is not None and nv != v):
                    # Only mark change; don't commit yet
                    changed = True
                    if not dry_run:
                        setattr(r, f, nv)
                        print(f"Row {r.id}: set {f} from {v!r} -> {nv!r}")

            # Clean full_address separately: if full_address contains any None tokens or 'None' strings, recompute
            fa = getattr(r, 'full_address', None)
            nfa = norm(fa) if fa else None
            if nfa is None and fa:
                # try to reconstruct from normalized pieces
                city = norm(getattr(r, 'postal_city', None))
                street = norm(getattr(r, 'postal_street', None))
                house = norm(getattr(r, 'postal_building', None))
                p_index = norm(getattr(r, 'postal_index', None))
                parts = []
                if p_index:
                    parts.append(p_index)
                if city:
                    parts.append(city)
                if street:
                    parts.append(street)
                addr = ', '.join(parts)
                if house:
                    if addr:
                        addr = f"{addr} д.{house}"
                    else:
                        addr = f"д.{house}"
                if addr:
                    changed = True
                    nfa = addr
                    if not dry_run:
                        setattr(r, 'full_address', nfa)
                        print(f"Row {r.id}: set full_address from {fa!r} -> {nfa!r}")
                else:
                    if not dry_run and fa:
                        # full_address column is NOT NULL at DB level; use empty string instead of None
                        setattr(r, 'full_address', '')
                        print(f"Row {r.id}: set full_address from {fa!r} -> ''")
                        changed = True

            if changed:
                updated += 1
                if not dry_run:
                    s.add(r)
                    try:
                        # Ensure we don't attempt to set NOT NULL DB fields to None
                        if getattr(r, 'full_address', None) is None:
                            setattr(r, 'full_address', '')
                        # Print field reprs and types to debug why None is passed to SQL UPDATE
                        fa_val = getattr(r, 'full_address', None)
                        pr_full = getattr(r, 'postal_recipient_fullname', None)
                        import sys
                        print(f"Flushing changes for row {r.id} (before commit): full_address={fa_val!r} (type={type(fa_val)}), postal_recipient_fullname={pr_full!r} (type={type(pr_full)})")
                        sys.stdout.flush()
                        await s.flush()
                        print(f"Flushed row {r.id}, now committing")
                        await s.commit()
                        print(f"Committed row {r.id}")
                    except Exception as ex:
                        print(f"Failed to commit row {r.id}: {ex}")
                        # rollback this transaction so next rows can be processed
                        await s.rollback()
                        raise
        # no global batch commit is needed as we commit per updated row
    print(f"Processed {len(rows)} entries, to-be-updated: {updated}, dry_run={dry_run}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Clean postal None values in DB')
    parser.add_argument('--apply', action='store_true', help='Apply changes to DB (default is dry-run)')
    args = parser.parse_args()
    asyncio.run(clean_all(dry_run=not args.apply))
