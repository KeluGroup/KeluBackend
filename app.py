from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def health():
    return {"ok": True}

@app.get("/api/health")
def api_health():
    return {"status": "healthy"}