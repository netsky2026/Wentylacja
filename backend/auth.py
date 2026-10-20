import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import jwt
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

JWT_ALGORITHM = "HS256"
ACCESS_MIN = 15
REFRESH_DAYS = 30
ROLES = {"viewer": 0, "operator": 1, "admin": 2}
MAX_ATTEMPTS = 5
LOCK_MIN = 15

db = None  # set by server.init_auth


def init(database):
    global db
    db = database


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def _token(u: dict, kind: str, delta: timedelta) -> str:
    return jwt.encode({"sub": str(u["_id"]), "tv": u.get("tv", 0), "type": kind,
                       "exp": datetime.now(timezone.utc) + delta}, _secret(), JWT_ALGORITHM)


def _set_cookies(resp: Response, u: dict):
    opts = dict(httponly=True, secure=True, samesite="lax", path="/")
    resp.set_cookie("access_token", _token(u, "access", timedelta(minutes=ACCESS_MIN)), max_age=ACCESS_MIN * 60, **opts)
    resp.set_cookie("refresh_token", _token(u, "refresh", timedelta(days=REFRESH_DAYS)), max_age=REFRESH_DAYS * 86400, **opts)


def public_user(u: dict) -> dict:
    return {"id": str(u["_id"]), "email": u["email"], "name": u.get("name", ""), "role": u["role"]}


async def user_from_token(token: Optional[str], kind: str = "access") -> Optional[dict]:
    if not token:
        return None
    try:
        p = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if p.get("type") != kind or not ObjectId.is_valid(p.get("sub", "")):
        return None
    u = await db.users.find_one({"_id": ObjectId(p["sub"])})
    if not u or u.get("tv", 0) != p.get("tv", 0):
        return None
    return u


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    if not token and auth.startswith("Bearer "):
        token = auth[7:]
    u = await user_from_token(token)
    if not u:
        raise HTTPException(401, "Not authenticated")
    return u


def require(role: str):
    async def dep(user: dict = Depends(get_current_user)) -> dict:
        if ROLES.get(user.get("role"), -1) < ROLES[role]:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return dep


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(default="", max_length=80)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(pattern=r"^(viewer|operator|admin)$")


router = APIRouter(prefix="/api")


@router.post("/auth/login")
async def login(body: LoginIn, response: Response):
    email = body.email.strip().lower()
    ident = email  # per-account lockout; client IP headers are spoofable
    att = await db.login_attempts.find_one({"identifier": ident})
    now = datetime.now(timezone.utc)
    if att and att.get("count", 0) >= MAX_ATTEMPTS and att["last"].replace(tzinfo=timezone.utc) > now - timedelta(minutes=LOCK_MIN):
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    u = await db.users.find_one({"email": email})
    if not u or not verify_password(body.password, u["password_hash"]):
        if att and att["last"].replace(tzinfo=timezone.utc) <= now - timedelta(minutes=LOCK_MIN):
            await db.login_attempts.update_one({"identifier": ident}, {"$set": {"count": 1, "last": now}})
        else:
            await db.login_attempts.update_one({"identifier": ident}, {"$inc": {"count": 1}, "$set": {"last": now}}, upsert=True)
        raise HTTPException(401, "Invalid email or password")
    await db.login_attempts.delete_one({"identifier": ident})
    _set_cookies(response, u)
    return public_user(u)


@router.post("/auth/logout")
async def logout(response: Response):
    for k in ("access_token", "refresh_token"):
        response.delete_cookie(k, path="/", secure=True, httponly=True, samesite="lax")
    return {"ok": True}


@router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    u = await user_from_token(request.cookies.get("refresh_token"), "refresh")
    if not u:
        raise HTTPException(401, "Not authenticated")
    _set_cookies(response, u)
    return public_user(u)


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@router.put("/auth/password")
async def change_password(body: PasswordIn, response: Response, user: dict = Depends(get_current_user)):
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(400, "Current password is incorrect")
    user["tv"] = user.get("tv", 0) + 1  # revokes all other sessions
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"password_hash": hash_password(body.new_password), "tv": user["tv"]}})
    _set_cookies(response, user)
    return {"ok": True}


@router.get("/users")
async def list_users(_: dict = Depends(require("admin"))):
    return {"users": [public_user(u) async for u in db.users.find({}).sort("email", 1)]}


@router.post("/users")
async def create_user(body: UserIn, _: dict = Depends(require("admin"))):
    email = body.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "User already exists")
    doc = {"email": email, "name": body.name.strip(), "role": body.role,
           "password_hash": hash_password(body.password), "created_at": datetime.now(timezone.utc)}
    res = await db.users.insert_one(doc)
    doc["_id"] = res.inserted_id
    return public_user(doc)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require("admin"))):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(404, "User not found")
    if ObjectId(user_id) == admin["_id"]:
        raise HTTPException(400, "Cannot delete yourself")
    res = await db.users.delete_one({"_id": ObjectId(user_id)})
    if not res.deleted_count:
        raise HTTPException(404, "User not found")
    return {"ok": True}


async def setup():
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier")
    email = os.environ["ADMIN_EMAIL"].strip().lower()
    pw = os.environ["ADMIN_PASSWORD"]
    u = await db.users.find_one({"email": email})
    if not u:
        await db.users.insert_one({"email": email, "name": "Admin", "role": "admin",
                                   "password_hash": hash_password(pw), "created_at": datetime.now(timezone.utc)})
    elif not verify_password(pw, u["password_hash"]):
        await db.users.update_one({"_id": u["_id"]}, {"$set": {"password_hash": hash_password(pw), "role": "admin"},
                                                    "$inc": {"tv": 1}})

