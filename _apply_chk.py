import psycopg2, re
PARTS = {'do','da','de','dos','das','du','e','di','del','la','von','van'}
def fmt(s):
    ws = [w for w in re.split(r'\s+', (s or '').strip()) if w]
    if len(ws) < 2:
        ws = ws + ['Silva'] if ws else ['Usuario','Sistema']
    out = []
    for i,w in enumerate(ws):
        b = w.lower()
        out.append(b if i>0 and b in PARTS else b[:1].upper()+b[1:])
    return ' '.join(out)
c = psycopg2.connect(host='dpg-d7l67l9j2pic73cl15m0-a.oregon-postgres.render.com', port=5432, user='sra', password='5snFWwPqRTF6Ky9JbjMXOvXZFObvByfl', dbname='sra_93i5', sslmode='require', connect_timeout=15)
cur = c.cursor()
cur.execute('SELECT id, nome FROM users')
rows = cur.fetchall()
print('users antes:', rows)
for uid, nm in rows:
    novo = fmt(nm)
    if novo != nm:
        cur.execute('UPDATE users SET nome=%s WHERE id=%s', (novo, uid))
        print('fix', uid, repr(nm), '->', repr(novo))
c.commit()
ddl = r"""
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_nome_format_chk;
ALTER TABLE users ADD CONSTRAINT users_nome_format_chk CHECK (nome ~ '^[A-ZAAAAAEEEEIIIIOOOOOUUUUCN][a-zaaaaaeeeeiiiiooooouuuucn]+(\s(do|da|de|dos|das|du|e|di|del|la|von|van)|\s[A-ZAAAAAEEEEIIIIOOOOOUUUUCN][a-zaaaaaeeeeiiiiooooouuuucn]+)+$');
"""
cur.execute(ddl)
c.commit()
cur.execute('SELECT conname FROM pg_constraint WHERE conname=%s', ('users_nome_format_chk',))
print('constraint:', cur.fetchone())
cur.execute('SELECT id, nome FROM users')
print('users depois:', cur.fetchall())
c.close()
print('OK')