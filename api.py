import hmac
import hashlib
import json
from urllib.parse import parse_qs
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, desc

from config import BOT_TOKEN, DB_URL
from database.models import User, Check, Transaction
from utils.rates import get_crypto_rates

app = FastAPI(title="CryptoKassa API")

# Разрешаем запросы с любых источников (для работы WebApp)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = create_async_engine(DB_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        yield session

# Проверка подлинности данных от Telegram (initData)
def verify_telegram_data(init_data: str) -> dict:
    try:
        parsed_data = parse_qs(init_data)
        hash_from_tg = parsed_data.get("hash", [None])[0]
        if not hash_from_tg:
            raise ValueError()

        data_check_string = "\n".join(
            f"{k}={v[0]}" for k, v in sorted(parsed_data.items()) if k != "hash"
        )

        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if calculated_hash != hash_from_tg:
            raise HTTPException(status_code=401, detail="Недействительная подпись Telegram")

        user_json = parsed_data.get("user", [None])[0]
        return json.loads(user_json)
    except Exception:
        raise HTTPException(status_code=401, detail="Ошибка авторизации Telegram")


@app.get("/api/me")
async def get_user_profile(x_init_data: str = Header(...), db: AsyncSession = Depends(get_db)):
    tg_user = verify_telegram_data(x_init_data)
    user_id = tg_user["id"]

    stmt = select(User).where(User.user_id == user_id)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    rates = await get_crypto_rates()
    
    total_usd = (
        user.balance_usdt * rates.get("USDT", 1.0) +
        user.balance_ton * rates.get("TON", 0.0) +
        user.balance_btc * rates.get("BTC", 0.0)
    )

    return {
        "user_id": user.user_id,
        "nickname": user.custom_nickname,
        "balances": {
            "USDT": user.balance_usdt,
            "TON": user.balance_ton,
            "BTC": user.balance_btc
        },
        "total_usd": round(total_usd, 2),
        "addresses": {
            "TON": user.address_ton,
            "USDT": user.address_usdt,
            "BTC": user.address_btc
        }
    }


@app.get("/api/history")
async def get_history(x_init_data: str = Header(...), db: AsyncSession = Depends(get_db)):
    tg_user = verify_telegram_data(x_init_data)
    user_id = tg_user["id"]

    stmt = select(Transaction).where(Transaction.user_id == user_id).order_by(desc(Transaction.created_at)).limit(15)
    res = await db.execute(stmt)
    txs = res.scalars().all()

    return [
        {
            "id": tx.id,
            "type": tx.tx_type,
            "currency": tx.currency,
            "amount": tx.amount,
            "description": tx.description,
            "date": tx.created_at.strftime("%d.%m %H:%M")
        }
        for tx in txs
    ]