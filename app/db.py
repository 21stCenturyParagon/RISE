from supabase import create_client, Client
from app.config import get_settings

settings = get_settings()


def get_supabase() -> Client:
    """Get Supabase client instance."""
    supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return supabase


async def get_supabase_admin() -> Client:
    """Get Supabase client instance with admin privileges."""
    supabase: Client = create_client(
        settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
    )
    try:
        yield supabase
    finally:
        # Cleanup if needed
        pass
