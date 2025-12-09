"""Fix assignments where giver_user_id/receiver_user_id contains telegram_id instead of internal users.id
This script attempts to map assignment.*_user_id to users.id by matching existing users.telegram_id.
It requires the DB path to be /app/data.db inside the container (project default).
"""
import sqlite3
import sys

DB = '/app/data.db'

sqls = [
    ("Update giver_user_id from users.telegram_id",
     "UPDATE assignments\nSET giver_user_id = (SELECT id FROM users WHERE users.telegram_id = assignments.giver_user_id)\nWHERE giver_user_id NOT IN (SELECT id FROM users) AND EXISTS (SELECT 1 FROM users WHERE users.telegram_id = assignments.giver_user_id);"),
    ("Update receiver_user_id from users.telegram_id",
     "UPDATE assignments\nSET receiver_user_id = (SELECT id FROM users WHERE users.telegram_id = assignments.receiver_user_id)\nWHERE receiver_user_id NOT IN (SELECT id FROM users) AND EXISTS (SELECT 1 FROM users WHERE users.telegram_id = assignments.receiver_user_id);"),
]

if __name__ == '__main__':
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    try:
        conn.execute('PRAGMA foreign_keys = OFF')
        conn.execute('BEGIN')
        for desc, s in sqls:
            cur.execute('SELECT COUNT(*) FROM assignments')
            before = cur.fetchone()[0]
            cur.execute(s)
            changed = cur.rowcount
            print(f"{desc}: rows changed={changed}")
        conn.commit()
    except Exception as e:
        print('Error:', e)
        conn.rollback()
        sys.exit(1)
    finally:
        conn.execute('PRAGMA foreign_keys = ON')
        conn.close()
    print('Done')
