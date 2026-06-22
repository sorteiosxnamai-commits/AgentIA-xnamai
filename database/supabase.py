from supabase import create_client
from dotenv import load_dotenv
import os

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print("================================")
print("SUPABASE_URL:", SUPABASE_URL)
print("SUPABASE_KEY:", SUPABASE_KEY[:20] if SUPABASE_KEY else "NÃO ENCONTRADA")
print("================================")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)