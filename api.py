import hashlib
import hmac
import json
from urllib.parse import parse_qs
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CryptoKassa API Debug")

# Разрешаем все CORS запросы
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Пропускаем приветственный экран ngrok
@app.middleware("http")
async def add_ngrok_skip_header(request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

@app.get("/api/me")
async def get_user_profile(x_init_data: str = Header(None)):
    print(f"--> Получен x_init_data: {x_init_data}")
    
    # Всегда отдаем успешный тестовый ответ 200 OK
    return {
        "user_id": 777777,
        "nickname": "TestUser",
        "balances": {
            "USDT": 150.50,
            "TON": 12.30,
            "BTC": 0.0045
        },
        "total_usd": 412.80
    }
