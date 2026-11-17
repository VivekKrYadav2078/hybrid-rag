"""
config.py - Centralized Configuration
======================================
Loads all environment variables from .env file and exposes them
as simple Python constants. Every other module imports from here.
"""

import os
from dotenv import load_dotenv

# Load .env file from the backend directory
load_dotenv()

# --- Supabase Configuration ---
# SUPABASE_URL: The base URL of your Supabase project (e.g., https://xyz.supabase.co)
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")

# SUPABASE_SERVICE_ROLE_KEY: Full-access key that bypasses Row-Level Security.
# Used server-side only - NEVER expose this to the frontend.
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# SUPABASE_JWT_SECRET: Used to verify JWTs from Supabase Auth.
# Found in Supabase Dashboard > Settings > API > JWT Settings.
SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")

# --- Groq Configuration ---
# GROQ_API_KEY: API key for ultra-fast LLM inference via Groq.
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# --- CORS ---
# FRONTEND_URL: The Next.js frontend origin, used for CORS allow-list.
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://unseconded-mirna-demiurgically.ngrok-free.dev")
