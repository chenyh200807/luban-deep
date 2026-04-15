import sqlite3, json
TURN_ID='turn_1776229636605_6f317e2abe'
SESSION_ID='tb_b2502e79ffce4014950e2ae3'
con=sqlite3.connect('/app/data/user/chat_history.db')
con.row_factory=sqlite3.Row
cur=con.cursor()
print('--- SESSION ---')
row=cur.execute("SELECT id,title,source,preferences_json,created_at,updated_at FROM sessions WHERE id=?", (SESSION_ID,)).fetchone()
print(dict(row) if row else None)
print('--- TURN ---')
row=cur.execute("SELECT * FROM turns WHERE id=?", (TURN_ID,)).fetchone()
print(dict(row) if row else None)
print('--- EVENTS ---')
rows=cur.execute("SELECT seq,type,source,stage,substr(content,1,300) as content,metadata_json FROM turn_events WHERE turn_id=? ORDER BY seq ASC", (TURN_ID,)).fetchall()
for r in rows:
    d=dict(r)
    meta=d.get('metadata_json')
    if meta and len(meta)>500:
        d['metadata_json']=meta[:500]+'...'
    print(d)
print('--- MESSAGES ---')
rows=cur.execute("SELECT id,role,substr(content,1,800) as content,capability,created_at FROM messages WHERE session_id=? ORDER BY created_at ASC", (SESSION_ID,)).fetchall()
for r in rows:
    print(dict(r))
con.close()
