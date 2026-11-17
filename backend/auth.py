"""
auth.py - Authentication Dependency
=====================================
Provides a FastAPI dependency `get_current_tenant` that:
1. Extracts the JWT from the Authorization header
2. Verifies it using the Supabase JWT secret
3. Looks up the user's tenant_id from the tenants table
"""

import jwt  # PyJWT library for decoding JWTs
from fastapi import HTTPException, Header
from config import SUPABASE_JWT_SECRET
from db import supabase


async def get_current_tenant(authorization: str = Header(...)) -> str:
    """
    FastAPI dependency that extracts and verifies the Supabase JWT,
    then resolves the authenticated user to their tenant_id.
    """
    # --- Step 1: Extract the token from "Bearer <token>" ---
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = authorization.split(" ", 1)[1]

    # --- Step 2: Decode and verify the JWT ---
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},  # Disabled strict audience check to prevent 401 mismatches
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        print(f"JWT Decode Error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

    # The 'sub' claim contains the Supabase auth user ID
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")

    # --- Step 3: Look up the tenant for this user ---
    try:
        result = (
            supabase.table("tenants")
            .select("id")
            .eq("owner_id", user_id)
            .single()
            .execute()
        )
    except Exception as e:
        print(f"Database lookup error for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error during tenant lookup")

    if not result.data:
        raise HTTPException(status_code=404, detail="No tenant found for this user")

    return result.data["id"]