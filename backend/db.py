"""
db.py - Supabase Client Setup
==============================
Creates and exports a single Supabase client instance using the
Service Role Key. This client bypasses Row-Level Security (RLS),
which is required because the backend performs operations on behalf
of tenants (e.g., inserting chunks, reading messages).

Why Service Role Key?
- The backend is a trusted server - it verifies JWTs itself.
- RLS policies are still useful for direct Supabase client access
  from the frontend, but the backend needs unrestricted access.
"""

from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# Create a single Supabase client instance (reused across all requests).
# Using the Service Role Key gives full database access.
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
