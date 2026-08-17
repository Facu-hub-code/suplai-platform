import os
import sys
import csv
import json
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv()

TENANT_ID = "5b1f1487-0eb1-472e-bb89-2ca40a5b89f8"
CROSS_CSV = "implementacion/valaice/outputs/phase-03-cross-sell.csv"
UP_CSV = "implementacion/valaice/outputs/phase-03-up-sell.csv"

async def create_cross_up():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL not found.")
        sys.exit(1)
        
    os.makedirs("implementacion/valaice/outputs", exist_ok=True)
    
    cross_sell = [
        {"base_product_code": "421", "related_product_code": "429", "priority": 1, "active": True, "is_mock": True},
        {"base_product_code": "421", "related_product_code": "422-MIX", "priority": 2, "active": True, "is_mock": True},
        {"base_product_code": "426", "related_product_code": "423", "priority": 1, "active": True, "is_mock": True},
        {"base_product_code": "440", "related_product_code": "435", "priority": 1, "active": True, "is_mock": True},
        {"base_product_code": "428", "related_product_code": "415", "priority": 1, "active": True, "is_mock": True}
    ]
    
    up_sell = [
        {"base_product_code": "422", "related_product_code": "421", "priority": 1, "active": True, "is_mock": True},
        {"base_product_code": "422-MIX", "related_product_code": "426", "priority": 1, "active": True, "is_mock": True},
        {"base_product_code": "441", "related_product_code": "443", "priority": 1, "active": True, "is_mock": True}
    ]
    
    with open(CROSS_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(cross_sell[0].keys()))
        writer.writeheader()
        writer.writerows(cross_sell)
        
    with open(UP_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(up_sell[0].keys()))
        writer.writeheader()
        writer.writerows(up_sell)
        
    print(f"✅ Generated {CROSS_CSV} and {UP_CSV}.")
    
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        await conn.execute("DELETE FROM public.tenant_cross_sell_mappings WHERE tenant_id = $1;", TENANT_ID)
        await conn.execute("DELETE FROM public.tenant_up_sell_mappings WHERE tenant_id = $1;", TENANT_ID)
        
        for c in cross_sell:
            await conn.execute("""
                INSERT INTO public.tenant_cross_sell_mappings (
                    tenant_id, base_product_code, related_product_code, priority, active, is_mock, created_at, updated_at
                ) VALUES ($1::uuid, $2, $3, $4, $5, $6, now(), now());
            """, TENANT_ID, c['base_product_code'], c['related_product_code'], c['priority'], c['active'], c['is_mock'])
            
        for u in up_sell:
            await conn.execute("""
                INSERT INTO public.tenant_up_sell_mappings (
                    tenant_id, base_product_code, related_product_code, priority, active, is_mock, created_at, updated_at
                ) VALUES ($1::uuid, $2, $3, $4, $5, $6, now(), now());
            """, TENANT_ID, u['base_product_code'], u['related_product_code'], u['priority'], u['active'], u['is_mock'])
            
        print("✅ Successfully inserted cross-sell and up-sell mappings into public tables!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(create_cross_up())
