import sys, os, asyncio, asyncpg
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv(r'c:\Users\Agustin\Desktop\Suplai sales\suplai-platform\.env')

async def main():
    db_url = os.getenv('SUPABASE_DB_URL')
    conn = await asyncpg.connect(db_url)
    rows = await conn.fetch(
        "SELECT table_name, column_name, data_type, is_nullable "
        "FROM information_schema.columns "
        "WHERE table_schema = 'mayorius' AND table_name IN ('clients', 'puntos_venta') "
        "ORDER BY table_name, ordinal_position"
    )
    from collections import defaultdict
    tables = defaultdict(list)
    for r in rows:
        tables[r['table_name']].append(r)
    for t, cols in tables.items():
        print('--- ' + t + ' ---')
        for c in cols:
            print('  ' + c['column_name'] + ' | ' + c['data_type'] + ' | nullable=' + c['is_nullable'])
        print()
    await conn.close()

asyncio.run(main())
