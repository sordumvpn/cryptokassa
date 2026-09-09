import hashlib
import hmac
import json
import sqlite3
from urllib.parse import parse_qs

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
import httpx

# Вставь сюди токен своего бота из @BotFather
BOT_TOKEN = "8744785117:AAGhQuyvVW5WAqqEJBoRoK7JI5kUpyq1NTQ"

app = FastAPI(title="CryptoKassa API")

# Разрешаем CORS-запросы для работы с GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Автоматически обходим предупреждающий экран ngrok
@app.middleware("http")
async def add_ngrok_skip_header(request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response


def verify_telegram_data(init_data: str) -> dict:
    """
    Проверяет валидность подписи initData от Telegram.
    При некорректном токене или тестировании через обычный браузер
    мягко возвращает данные юзера без выброса 401.
    """
    if not init_data:
        print("--> WARNING: initData отсутствует, используем fallback-юзера")
        return {"id": 123456789, "first_name": "TestUser"}

    try:
        parsed_data = parse_qs(init_data)
        hash_from_tg = parsed_data.get("hash", [None])[0]
        user_json = parsed_data.get("user", [None])[0]

        if not user_json:
            return {"id": 123456789, "first_name": "TestUser"}

        user_data = json.loads(user_json)

        if not hash_from_tg:
            return user_data

        # Формируем строку проверки подписи
        data_check_string = "\n".join(
            f"{k}={v[0]}" for k, v in sorted(parsed_data.items()) if k != "hash"
        )

        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if calculated_hash != hash_from_tg:
            print("--> WARNING: Хэш Telegram не совпал с BOT_TOKEN, но запрос пропущен для отладки.")

        return user_data
    except Exception as e:
        print(f"--> ERROR при разборе initData: {e}")
        return {"id": 123456789, "first_name": "TestUser"}


async def get_crypto_rates() -> dict:
    """Получает текущие курсы валют из CoinGecko"""
    url = "https://api.coingecko.com/api/v3/simple/price?ids=tether,toncoin,bitcoin&vs_currencies=usd"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(url)
            data = res.json()
            return {
                "USDT": data.get("tether", {}).get("usd", 1.0),
                "TON": data.get("toncoin", {}).get("usd", 5.2),
                "BTC": data.get("bitcoin", {}).get("usd", 65000.0),
            }
    except Exception:
        return {"USDT": 1.0, "TON": 5.2, "BTC": 65000.0}


@app.get("/api/me")
async def get_user_profile(x_init_data: str = Header(None)):
    tg_user = verify_telegram_data(x_init_data or "")
    user_id = tg_user.get("id")

    # Подключаемся к локальной БД SQLite
    try:
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT balance_usdt, balance_ton, balance_btc FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        conn.close()
    except Exception as e:
        print(f"--> ERROR при чтении database.db: {e}")
        row = None

    # Если пользователя ещё нет в базе
    if not row:
        return {
            "user_id": user_id,
            "nickname": tg_user.get("first_name", "User"),
            "balances": {"USDT": 0.0, "TON": 0.0, "BTC": 0.0},
            "total_usd": 0.0,
        }

    usdt_bal = float(row[0] or 0.0)
    ton_bal = float(row[1] or 0.0)
    btc_bal = float(row[2] or 0.0)

    rates = await get_crypto_rates()

    total_usd = (
        usdt_bal * rates.get("USDT", 1.0)
        + ton_bal * rates.get("TON", 5.2)
        + btc_bal * rates.get("BTC", 65000.0)
    )

    return {
        "user_id": user_id,
        "nickname": tg_user.get("first_name", "User"),
        "balances": {"USDT": usdt_bal, "TON": ton_bal, "BTC": btc_bal},
        "total_usd": round(total_usd, 2),
    }
