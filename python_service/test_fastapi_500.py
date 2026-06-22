from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/")
def read_root():
    raise TypeError("This is a type error")

client = TestClient(app)
res = client.get("/")
print("Status:", res.status_code)
print("Content-Type:", res.headers.get("Content-Type"))
print("Text:", res.text)
