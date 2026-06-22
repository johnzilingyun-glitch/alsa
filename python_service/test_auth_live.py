import requests

try:
    res = requests.post("http://127.0.0.1:8001/api/auth/token", data={
        "username": "zily",
        "password": "wrong_password"
    })
    print("Port 8001:")
    print(res.status_code, res.text)
except Exception as e:
    print("Port 8001 failed:", e)

try:
    res = requests.post("http://127.0.0.1:8000/api/auth/token", data={
        "username": "zily",
        "password": "wrong_password"
    })
    print("Port 8000:")
    print(res.status_code, res.text)
except Exception as e:
    print("Port 8000 failed:", e)
