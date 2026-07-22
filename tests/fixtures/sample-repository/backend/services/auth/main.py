from fastapi import FastAPI
import jwt
import psycopg

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}
