from fastapi import FastAPI

app = FastAPI(title="BUET-PaaS", version="0.1.0")

@app.get("/")
def root():
    return {"message": "BUET-PaaS backend is running"}

@app.get("/health")
def health():
    return {"status": "ok"}