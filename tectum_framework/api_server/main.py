from fastapi import FastAPI

app = FastAPI(title="Cloven Tectum API", version="0.1.0")

@app.get("/")
def root():
    return {"message": "Cloven Tectum online — uptime is truth."}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/rickroll")
def rickroll():
    # never gonna run around and desert you
    return {"hint": "Never gonna let you down"}