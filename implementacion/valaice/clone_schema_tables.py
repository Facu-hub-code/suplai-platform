import asyncio
import sys
from pathlib import Path

# Importar sync_schema desde scripts/
sys.path.append(str(Path(__file__).resolve().parents[2] / "scripts"))
# pyrefly: ignore [missing-import]
from sync_tenant_schema_objects import sync_schema

if __name__ == "__main__":
    asyncio.run(sync_schema(source="gonzales", target="valaice"))

