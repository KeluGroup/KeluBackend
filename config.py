import os
import json

ALLOWED_ORIGINS     = json.loads(os.getenv("ALLOWED_ORIGINS", '["*"]'))
API_SECRET          = os.getenv("FORM_API_SECRET")
ADMIN_PASSWORD      = os.getenv("ADMIN_PASSWORD", "")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "").encode("utf-8")
AIRTABLE_API_KEY    = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID    = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")