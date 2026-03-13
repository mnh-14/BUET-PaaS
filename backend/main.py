from fastapi import FastAPI
from contextlib import asynccontextmanager
from db import ping, init_indexes   

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ping()           
        init_indexes()  
        print("MongoDB connected and indexes ready.")
    except Exception as e:
        print("MongoDB connection failed:", e)
        raise
    yield
    print("Shutting down FastAPI")


app = FastAPI(title="BUET-PaaS", version="0.1.0", lifespan=lifespan)


@app.get("/")
def root():
    return {"message": "BUET-PaaS backend is running"}


@app.get("/health")
def health():
    try:
        ping()
        return {"status": "ok", "db": "connected"}
    except Exception:
        return {"status": "error", "db": "disconnected"}