from fastapi import FastAPI
import uvicorn
import os

app = FastAPI(title="Cloven Tectum API", version="0.1.0")

@app.get("/")
def root():
    return {"message": "Cloven Tectum online — uptime is truth.", "status": "running"}

@app.get("/health")
def health():
    return {"status": "ok", "ok": True}

@app.get("/rickroll")
def rickroll():
    # never gonna run around and desert you
    return {"hint": "Never gonna let you down"}

if __name__ == "__main__":
    port = int(os.getenv("API_PORT", "8000"))
    host = os.getenv("API_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)