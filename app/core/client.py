
from supabase import create_client, Client
import os
from app.core.config import settings

# Create Supabase client
supabase_client: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_KEY  # Use service role key for admin access
)