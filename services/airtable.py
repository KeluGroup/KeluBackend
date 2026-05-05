from pyairtable import Api
from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME


def get_airtable_table():
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not AIRTABLE_TABLE_NAME:
        raise RuntimeError("Airtable configuration is missing")
    return Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)


def create_lead(data: dict) -> dict:
    table  = get_airtable_table()
    record = table.create({
        "Name":    data.get("name"),
        "Email":   data.get("email"),
        "Company": data.get("company"),
        "Message": data.get("message"),
        "Service": data.get("service")
    })
    return {"id": record.get("id"), "status": "created", "received": record.get("fields", {})}



def fetch_all_leads() -> list:
    records = get_airtable_table().all()
    leads   = [
        {
            "id":        r["id"],
            "name":      r["fields"].get("Name", ""),
            "email":     r["fields"].get("Email", ""),
            "company":   r["fields"].get("Company", ""),
            "message":   r["fields"].get("Message", ""),
            "status":    r["fields"].get("Status", "Nuevo"),
            "createdAt": r.get("createdTime", ""),
        }
        for r in records
    ]
    return sorted(leads, key=lambda x: x["createdAt"], reverse=True)


def update_lead(record_id: str, status: str) -> None:
    get_airtable_table().update(record_id, {"Status": status})