import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".ENV")

supabase_url = os.getenv("SUPABASE_URL") or os.getenv("SUPERBASE_URL")
supabase_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPERNASE_ANON_KEY")

if not supabase_url or not supabase_key:
    raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set.")


def create_supabase_client() -> Client:
    return create_client(supabase_url, supabase_key)


supabase: Client = create_supabase_client()
