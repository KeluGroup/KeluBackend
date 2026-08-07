import os
import json

ALLOWED_ORIGINS     = json.loads(os.getenv("ALLOWED_ORIGINS", '["*"]'))
API_SECRET          = os.getenv("FORM_API_SECRET")
ADMIN_PASSWORD      = os.getenv("ADMIN_PASSWORD", "")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "").encode("utf-8")
AIRTABLE_API_KEY    = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID    = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")

# ── Recetas Kelu (Instagram / Facebook autopost) ──────
AIRTABLE_SOCIALPOSTS_TABLE_NAME = os.getenv("AIRTABLE_SOCIALPOSTS_TABLE_NAME", "SocialPosts")
AIRTABLE_RECIPES_TABLE_NAME     = os.getenv("AIRTABLE_RECIPES_TABLE_NAME", "Recipes")

OPENAI_API_KEY       = os.getenv("OPENAI_API_KEY")
GNEWS_API_KEY        = os.getenv("GNEWS_API_KEY")  # opcional — sin esto, las tendencias usan el fallback curado

KELU_IG_ACCESS_TOKEN = os.getenv("KELU_IG_ACCESS_TOKEN")
KELU_IG_ACCOUNT_ID   = os.getenv("KELU_IG_ACCOUNT_ID")
KELU_FB_PAGE_ID      = os.getenv("KELU_FB_PAGE_ID")
KELU_FB_PAGE_TOKEN   = os.getenv("KELU_FB_PAGE_TOKEN")

CRON_SECRET          = os.getenv("CRON_SECRET")