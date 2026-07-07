import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("UPDATE users SET plano='pro' WHERE email=%s RETURNING id, email, empresa_nome, plano", ('luis@nucleopro.com.br',))
row = cur.fetchone()
conn.commit()
print('Atualizado:', row)
