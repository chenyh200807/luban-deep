import sqlite3
from pathlib import Path
p=Path('/app/data/user/chat_history.db')
print('DB', p, p.exists())
con=sqlite3.connect(p)
con.row_factory=sqlite3.Row
cur=con.cursor()
for name in ['sessions','turns','turn_events','messages']:
    try:
        cols=cur.execute(f'PRAGMA table_info({name})').fetchall()
        print('TABLE', name, [c[1] for c in cols])
    except Exception as e:
        print('ERR', name, e)
print('--- FIND_HELLO ---')
for name, sql, args in [
    ('turn_events', "SELECT turn_id,type,seq,substr(content,1,120) as content,created_at FROM turn_events WHERE content LIKE ? ORDER BY created_at DESC LIMIT 20", ('%你好%',)),
    ('messages', "SELECT id,session_id,role,substr(content,1,120) as content,created_at FROM messages WHERE content LIKE ? ORDER BY created_at DESC LIMIT 20", ('%你好%',)),
]:
    try:
        rows=cur.execute(sql, args).fetchall()
        print('ROWS', name, len(rows))
        for r in rows:
            print(dict(r))
    except Exception as e:
        print('ERRQ', name, e)
print('--- RECENT USER MSGS ---')
rows=cur.execute("SELECT id,session_id,role,substr(content,1,80) as content,created_at FROM messages WHERE role='user' ORDER BY created_at DESC LIMIT 30").fetchall()
for r in rows:
    print(dict(r))
print('--- RECENT TURNS ---')
rows=cur.execute("SELECT id,session_id,status,capability,created_at FROM turns ORDER BY created_at DESC LIMIT 20").fetchall()
for r in rows:
    print(dict(r))
con.close()
