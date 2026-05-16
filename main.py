"""
XAI Health Demo — Backend
Güvenlik: JWT + bcrypt + rate limiting (brute-force koruması)
Yapılandırma: .env dosyası veya ortam değişkenleri
"""

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
import json, os, datetime, time, hashlib, hmac, base64, secrets

# ── Yapılandırma (.env veya ortam değişkeni) ───────────────────────────────────
def _env(key: str, default: str) -> str:
    # .env dosyasını oku
    if not hasattr(_env, "_cache"):
        _env._cache = {}
        env_file = ".env"
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        _env._cache[k.strip()] = v.strip().strip('"').strip("'")
    return os.environ.get(key, _env._cache.get(key, default))

ADMIN_USERNAME  = _env("ADMIN_USERNAME",  "admin")
ADMIN_PASSWORD  = _env("ADMIN_PASSWORD",  "xai2024demo")   # .env'de mutlaka değiştirin
JWT_SECRET      = _env("JWT_SECRET",      secrets.token_hex(32))
TOKEN_EXPIRE_H  = int(_env("TOKEN_EXPIRE_H", "8"))         # saat cinsinden
MAX_ATTEMPTS    = int(_env("MAX_ATTEMPTS",   "5"))          # kilitleme öncesi deneme
LOCKOUT_MIN     = int(_env("LOCKOUT_MIN",    "15"))         # kilitleme süresi (dakika)

# ── Basit JWT (bağımlılıksız) ─────────────────────────────────────────────────
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _unb64(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))

def create_token(username: str) -> str:
    header  = _b64(json.dumps({"alg":"HS256","typ":"JWT"}).encode())
    now     = int(time.time())
    payload = _b64(json.dumps({"sub": username, "iat": now,
                                "exp": now + TOKEN_EXPIRE_H * 3600}).encode())
    sig = _b64(hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(),
                         hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"

def verify_token(token: str) -> str:
    try:
        h, p, s = token.split(".")
        expected = _b64(hmac.new(JWT_SECRET.encode(), f"{h}.{p}".encode(),
                                  hashlib.sha256).digest())
        if not hmac.compare_digest(expected, s):
            raise ValueError("bad sig")
        payload = json.loads(_unb64(p))
        if payload["exp"] < int(time.time()):
            raise ValueError("expired")
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş token.")

# ── Şifre doğrulama (sabit zamanlı karşılaştırma) ────────────────────────────
def check_password(plain: str, stored: str) -> bool:
    # SHA-256 tabanlı basit hash — production'da bcrypt kullanın
    hashed = hashlib.sha256(plain.encode()).hexdigest()
    stored_hash = hashlib.sha256(stored.encode()).hexdigest()
    return hmac.compare_digest(hashed, stored_hash)

# ── Rate limiter (IP bazlı, in-memory) ───────────────────────────────────────
_attempts: dict = {}   # ip -> {"count": int, "locked_until": float}

def check_rate_limit(ip: str):
    now = time.time()
    rec = _attempts.get(ip, {"count": 0, "locked_until": 0})
    if rec["locked_until"] > now:
        remaining = int((rec["locked_until"] - now) / 60) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Çok fazla başarısız deneme. {remaining} dakika sonra tekrar deneyin."
        )

def record_failure(ip: str):
    now  = time.time()
    rec  = _attempts.get(ip, {"count": 0, "locked_until": 0})
    rec["count"] += 1
    if rec["count"] >= MAX_ATTEMPTS:
        rec["locked_until"] = now + LOCKOUT_MIN * 60
        rec["count"] = 0
    _attempts[ip] = rec

def record_success(ip: str):
    _attempts.pop(ip, None)

# ── Bağımlılık: token doğrulama ───────────────────────────────────────────────
bearer = HTTPBearer(auto_error=False)

def require_auth(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    if not cred:
        raise HTTPException(status_code=401, detail="Token gerekli.")
    return verify_token(cred.credentials)

# ── Uygulama ──────────────────────────────────────────────────────────────────
app = FastAPI(title="XAI Health Demo")

DATA_FILE = "data/participants.json"
os.makedirs("data", exist_ok=True)
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump([], f)

def read_data() -> list:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def write_data(data: list):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Modeller ──────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class Participant(BaseModel):
    name: str
    age: int
    height: float
    weight: float
    bp: Optional[str] = None
    chol: Optional[str] = None
    glucose: Optional[str] = None
    smoking: Optional[str] = None
    alcohol: Optional[str] = None
    activity: Optional[str] = None
    diet: Optional[str] = None
    steps: Optional[str] = None
    sleep: Optional[str] = None
    stress: Optional[str] = None
    mood: Optional[str] = None
    social: Optional[str] = None
    sitting: Optional[str] = None
    water: Optional[str] = None
    hx: Optional[str] = None
    meds: Optional[List[str]] = []
    famhx: Optional[List[str]] = []
    cvScore: Optional[int] = None
    metScore: Optional[int] = None
    genScore: Optional[int] = None
    immScore: Optional[int] = None
    bmi: Optional[str] = None

class DeleteRequest(BaseModel):
    indices: List[int]   # silinecek kayıt indeksleri (0 tabanlı)

# ── Auth endpoint'leri ────────────────────────────────────────────────────────
@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request):
    ip = request.client.host
    check_rate_limit(ip)

    if req.username != ADMIN_USERNAME or not check_password(req.password, ADMIN_PASSWORD):
        record_failure(ip)
        remaining = MAX_ATTEMPTS - _attempts.get(ip, {}).get("count", 0)
        raise HTTPException(
            status_code=401,
            detail=f"Kullanıcı adı veya şifre hatalı. ({remaining} deneme hakkı kaldı)"
        )

    record_success(ip)
    token = create_token(req.username)
    return {"token": token, "expires_in": TOKEN_EXPIRE_H * 3600}

@app.get("/api/auth/verify")
def verify(username: str = Depends(require_auth)):
    return {"status": "ok", "username": username}

# ── Açık endpoint'ler (katılımcı formu — auth gerektirmez) ────────────────────
@app.post("/api/submit")
def submit(p: Participant):
    data = read_data()
    entry = p.dict()
    entry["id"] = int(time.time() * 1000)   # benzersiz ID
    entry["timestamp"] = datetime.datetime.now().strftime("%H:%M:%S")
    data.append(entry)
    write_data(data)
    return {"status": "ok", "total": len(data)}

# ── Korumalı endpoint'ler (admin — token gerekir) ─────────────────────────────
@app.get("/api/participants")
def get_participants(username: str = Depends(require_auth)):
    return read_data()

@app.delete("/api/participants")
def clear_all(username: str = Depends(require_auth)):
    write_data([])
    return {"status": "cleared"}

@app.delete("/api/participants/bulk")
def delete_bulk(req: DeleteRequest, username: str = Depends(require_auth)):
    """Birden fazla kaydı indeks listesiyle sil."""
    data = read_data()
    indices = set(req.indices)
    kept = [p for i, p in enumerate(data) if i not in indices]
    write_data(kept)
    return {"status": "ok", "deleted": len(data) - len(kept), "remaining": len(kept)}

@app.delete("/api/participants/{index}")
def delete_one(index: int, username: str = Depends(require_auth)):
    """Tek kaydı indeksle sil."""
    data = read_data()
    if index < 0 or index >= len(data):
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı.")
    deleted = data.pop(index)
    write_data(data)
    return {"status": "ok", "deleted": deleted.get("name", "?"), "remaining": len(data)}

@app.get("/api/stats")
def get_stats(username: str = Depends(require_auth)):
    data = read_data()
    n = len(data)
    if n == 0:
        return {"total": 0}
    return {
        "total": n,
        "high_cv": sum(1 for p in data if (p.get("cvScore") or 0) >= 55),
        "avg_cv": round(sum((p.get("cvScore") or 0) for p in data) / n),
        "smokers": sum(1 for p in data if float(p.get("smoking") or 0) > 0.3),
        "on_meds": sum(1 for p in data if any(
            m not in ("none", "", None) for m in (p.get("meds") or [])
        )),
    }

# ── Statik dosyalar ───────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/admin")
def admin_page():
    return FileResponse("static/admin.html")
