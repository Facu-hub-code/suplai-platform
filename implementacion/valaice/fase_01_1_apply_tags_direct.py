import os
import sys
import json
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def apply_tags():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL not found.")
        sys.exit(1)
        
    json_path = "implementacion/valaice/outputs/phase-01-1-propuesta-tags.json"
    if not os.path.exists(json_path):
        print(f"[FAIL] {json_path} not found.")
        sys.exit(1)
        
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    products_list = data.get("products", [])
    print(f"[*] Processing {len(products_list)} product tags...")
    
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        # Clean existing
        await conn.execute("DELETE FROM valaice.product_tags;")
        await conn.execute("DELETE FROM valaice.tags;")
        
        tag_cache = {}  # (name, parent_id) -> id
        
        for item in products_list:
            code = item["product_code"]
            tags = item.get("tags", {})
            
            parent_id = None
            for level in ["1", "2", "3", "4"]:
                t_name = tags.get(level)
                if not t_name:
                    continue
                t_name = t_name.strip()
                
                key = (t_name, parent_id)
                if key in tag_cache:
                    tag_id = tag_cache[key]
                else:
                    tag_id = await conn.fetchval("""
                        INSERT INTO valaice.tags (name, parent_id, created_at, updated_at)
                        VALUES ($1, $2, now(), now())
                        RETURNING id;
                    """, t_name, parent_id)
                    tag_cache[key] = tag_id
                    
                parent_id = tag_id
                
                # Map product to tag
                await conn.execute("""
                    INSERT INTO valaice.product_tags (product_code, tag_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING;
                """, code, tag_id)
                
        print(f"✅ Successfully inserted {len(tag_cache)} unique taxonomy tags and mapped {len(products_list)} products!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(apply_tags())
