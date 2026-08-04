import os
import sys
import json
import asyncio
import asyncpg
import requests
from dotenv import load_dotenv

# Load workspace env
dotenv_path = r"c:\Users\marti\suplai-platform\.env"
load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = "text-embedding-3-small"

# Reconfigure stdout to use UTF-8 on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Helper to generate embeddings from OpenAI
async def generate_embedding(text: str) -> list[float]:
    url = f"{OPENAI_BASE_URL}/embeddings"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENAI_MODEL,
        "input": text
    }
    
    for attempt in range(3):
        try:
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(
                None,
                lambda: requests.post(url, headers=headers, json=payload, timeout=20)
            )
            if res.status_code == 200:
                data = res.json()
                return data["data"][0]["embedding"]
            else:
                print(f"[WARN] OpenAI error (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            print(f"[WARN] Embedding attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1)
    return []

# Helper to convert list to pgvector literal format
def to_pgvector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"

async def vectorize_category_row(pool, schema, cat, sem):
    async with sem:
        cat_id = cat["id"]
        name = (cat["name"] or "").strip()
        description = (cat["description"] or "").strip()
        parent_id = cat["parent_id"]
        
        # Build text content to embed
        parts = [name]
        if description:
            parts.append(description)
        if parent_id is not None:
            parts.append(f"parent_id:{int(parent_id)}")
        content = ". ".join(parts)
        
        # Generate embedding
        emb = await generate_embedding(content)
        if not emb:
            print(f"[WARN] No se pudo obtener embedding para categoría ID {cat_id} ({name})")
            return
            
        emb_literal = to_pgvector_literal(emb)
        metadata = {
            "tag_id": cat_id,
            "categoria_id": cat_id, # SPEC-060 compatibility
            "name": name,
            "parent_id": parent_id
        }
        metadata_json = json.dumps(metadata, ensure_ascii=False)
        
        async with pool.acquire() as conn:
            # Check if already exists in category_documents
            doc_rows = await conn.fetch(
                f"SELECT id FROM {schema}.category_documents WHERE metadata->>'categoria_id' = $1 LIMIT 1",
                str(cat_id)
            )
            if doc_rows:
                doc_id = doc_rows[0]["id"]
                await conn.execute(
                    f"UPDATE {schema}.category_documents SET content = $2, embedding = $3::vector, metadata = $4::jsonb WHERE id = $1",
                    doc_id, content, emb_literal, metadata_json
                )
            else:
                await conn.execute(
                    f"INSERT INTO {schema}.category_documents (content, metadata, embedding) VALUES ($1, $2::jsonb, $3::vector)",
                    content, metadata_json, emb_literal
                )

async def main():
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("[FAIL] SUPABASE_DB_URL no configurada en .env.")
        sys.exit(1)
        
    schema = "demo_jorge"
    
    print(f"[*] Iniciando vectorización de categorías para el esquema: {schema}")
    
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=2)
    try:
        # Fetch all categories
        async with pool.acquire() as conn:
            categories = await conn.fetch(f"SELECT id, name, description, parent_id FROM {schema}.categorias")
            print(f"[*] Total categorías a vectorizar: {len(categories)}")
            
            if not categories:
                print("[INFO] No hay categorías para vectorizar.")
                return
                
            # Clean existing category_documents table first for a fresh RAG index
            print("[*] Limpiando category_documents previo para evitar duplicados...")
            await conn.execute(f"DELETE FROM {schema}.category_documents;")
        
        # Concurrency semaphore
        sem = asyncio.Semaphore(2)
        
        tasks = [vectorize_category_row(pool, schema, cat, sem) for cat in categories]
        await asyncio.gather(*tasks)
        
        print("✅ Vectorización de categorías finalizada exitosamente.")
        
    except Exception as e:
        import traceback
        print(f"[FAIL] Error: {e}")
        traceback.print_exc()
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
