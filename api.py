import hmac
import hashlib
import json
from urllib.parse import parse_qs
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx

# Импорты ваших моделей и подключения к БД
from config import BOT_TOKEN
from database import get_db
from models import User

app = FastAPI(title="CryptoKassa API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_ngrok_skip_header(request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

def verify_telegram_data(init_data: str) -> dict:
    if not init_data:
        raise HTTPException(status_code=401, detail="Отсутствуют данные Telegram")

    try:
        parsed_data = parse_qs(init_data)
        hash_from_tg = parsed_data.get("hash", [None])[0]
        user_json = parsed_data.get("user", [None])[0]

        if not hash_from_tg or not user_json:
            raise HTTPException(status_code=401, detail="Неверная структура initData")

        data_check_string = "\n".join(
            f"{k}={v[0]}" for k, v in sorted(parsed_data.items()) if k != "hash"
        )

        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if calculated_hash != hash_from_tg:
            raise HTTPException(status_code=401, detail="Ошибка авторизации HMAC")

        return json.loads(user_json)
    except Exception:
        raise HTTPException(status_code=401, detail="Ошибка обработки данных авторизации")

async def get_crypto_rates() -> dict:
    url = "https://api.coingecko.com/api/v3/simple/price?ids=tether,toncoin,bitcoin&vs_currencies=usd"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(url)
            data = res.json()
            return {
                "USDT": data.get("tether", {}).get("usd", 1.0),
                "TON": data.get("toncoin", {}).get("usd", 5.2),
                "BTC": data.get("bitcoin", {}).get("usd", 65000.0)
            }
    except Exception:
        return {"USDT": 1.0, "TON": 5.2, "BTC": 65000.0}

@app.get("/api/me")
async def get_user_profile(x_init_data: str = Header(None), db: AsyncSession = Depends(get_db)):
    tg_user = verify_telegram_data(x_init_data or "")
    user_id = tg_user.get("id")

    stmt = select(User).where(User.user_id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        return {
            "user_id": user_id,
            "nickname": tg_user.get("first_name", "User"),
            "balances": {"USDT": 0.0, "TON": 0.0, "BTC": 0.0},
            "total_usd": 0.0
        }

    rates = await get_crypto_rates()

    usdt_bal = float(user.balance_usdt or 0.0)
    ton_bal = float(user.balance_ton or 0.0)
    btc_bal = float(user.balance_btc or 0.0)

    total_usd = (
        usdt_bal * rates.get("USDT", 1.0) +
        ton_bal * rates.get("TON", 5.2) +
        btc_bal * rates.get("BTC", 65000.0)
    )

    return {
        "user_id": user.user_id,
        "nickname": getattr(user, "custom_nickname", None) or tg_user.get("first_name"),
        "balances": {
            "USDT": usdt_bal,
            "TON": ton_bal,
            "BTC": btc_bal
        },
        "total_usd": round(total_usd, 2)
    }
