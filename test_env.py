import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 50)
print("🔍 Testing .env Loading")
print("=" * 50)
print(f"SUPABASE_URL: {os.getenv('SUPABASE_URL')}")
print(f"SUPABASE_KEY: {os.getenv('SUPABASE_KEY')[:30]}..." if os.getenv('SUPABASE_KEY') else "❌ Not set")
print(f"PAYSTACK_SECRET_KEY: {os.getenv('PAYSTACK_SECRET_KEY')[:20]}..." if os.getenv('PAYSTACK_SECRET_KEY') else "❌ Not set")
print(f"SECRET_KEY: {os.getenv('SECRET_KEY')[:20]}..." if os.getenv('SECRET_KEY') else "❌ Not set")
print(f"COMPANY_NAME: {os.getenv('COMPANY_NAME')}")
print("=" * 50)