import os
import sys
import json
import asyncio
import asyncpg
from dotenv import load_dotenv

# Load env
dotenv_path = r"c:\Users\marti\suplai-platform\.env"
load_dotenv(dotenv_path)

# Reconfigure stdout to use UTF-8 on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL not found in .env")
        sys.exit(1)
        
    schema = "distribuidora_lyl"
    proposal_path = rf"c:\Users\marti\suplai-platform\implementacion\{schema}\outputs\phase-01-1-propuesta-tags.json"
    
    if not os.path.exists(proposal_path):
        print(f"[FAIL] Proposal file not found at: {proposal_path}")
        sys.exit(1)
        
    with open(proposal_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    products = data.get("products", [])
    if not products:
        print("[FAIL] No products found in the proposal JSON.")
        sys.exit(1)
        
    print(f"[*] Processing tags for {len(products)} products...")
    
    conn = await asyncpg.connect(db_url)
    try:
        # Disable statement timeout
        await conn.execute("SET statement_timeout = 0;")
        
        # 1. We will load existing tags to build our cache
        print("[*] Loading existing tags from DB...")
        existing_rows = await conn.fetch(f"SELECT id, name, parent_id FROM {schema}.tags;")
        
        # cache key: name.lower().strip() -> (id, parent_id)
        tag_cache = {}
        for r in existing_rows:
            key = r["name"].lower().strip()
            tag_cache[key] = (r["id"], r["parent_id"])
            
        print(f"Loaded {len(tag_cache)} tags in cache.")
        
        # Helper to get or create a tag
        async def get_or_create_tag(name, parent_id):
            name_clean = name.strip()
            name_lower = name_clean.lower()
            
            if name_lower in tag_cache:
                tag_id, existing_parent_id = tag_cache[name_lower]
                if existing_parent_id != parent_id:
                    # Update parent_id in DB
                    await conn.execute(
                        f"UPDATE {schema}.tags SET parent_id = $1, updated_at = now() WHERE id = $2;",
                        parent_id,
                        tag_id
                    )
                    tag_cache[name_lower] = (tag_id, parent_id)
                return tag_id
                
            # Create tag in DB
            row = await conn.fetchrow(
                f"""
                INSERT INTO {schema}.tags (name, parent_id, created_at, updated_at)
                VALUES ($1, $2, now(), now())
                RETURNING id;
                """,
                name_clean,
                parent_id
            )
            tag_id = row["id"]
            tag_cache[name_lower] = (tag_id, parent_id)
            return tag_id

        # 2. Process hierarchical tags for each product
        print("[*] Creating tags hierarchy and mapping relationships...")
        mappings = [] # list of tuples: (product_code, tag_id)
        
        for p in products:
            code = p["product_code"]
            tags_dict = p.get("tags", {})
            if not tags_dict:
                continue
                
            # Sort levels alphabetically by key (usually "1", "2", "3", "4")
            levels = sorted(tags_dict.keys(), key=lambda x: int(x))
            
            parent_id = None
            for lvl in levels:
                tag_name = tags_dict[lvl].strip()
                if not tag_name:
                    continue
                    
                # get or create tag at this level
                tag_id = await get_or_create_tag(tag_name, parent_id)
                mappings.append((code, tag_id))
                parent_id = tag_id
                
        print(f"Tags processed. Cache size is now: {len(tag_cache)}")
        print(f"Total product-tag associations to process: {len(mappings)}")
        
        # 3. Batch insert mappings in product_tags
        # Deduplicate mappings to avoid database primary key collisions
        unique_mappings = list(set(mappings))
        print(f"Unique product-tag associations: {len(unique_mappings)}")
        
        # Delete existing associations first to prevent leftovers and ensure fresh copy
        print("[*] Cleaning previous product-tag mappings...")
        await conn.execute(f"DELETE FROM {schema}.product_tags;")
        
        print("[*] Inserting mappings into product_tags...")
        await conn.executemany(
            f"""
            INSERT INTO {schema}.product_tags (product_code, tag_id)
            VALUES ($1, $2)
            ON CONFLICT (product_code, tag_id) DO NOTHING;
            """,
            unique_mappings
        )
        print(f"✅ Successfuly mapped {len(unique_mappings)} product-tag relationships.")
        
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        sys.exit(1)
    finally:
        await conn.close()
        
    print("\n==============================================")
    print("PROCESO DE TAXONOMÍA COMPLETADO LOCALMENTE")
    print("==============================================")

if __name__ == '__main__':
    asyncio.run(main())
