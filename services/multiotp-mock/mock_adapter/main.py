from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


app = FastAPI(title="Development multiOTP Mock")
users: dict[str, dict] = {}


class UserCreate(BaseModel):
    username: str


class Verify(BaseModel):
    otp: str


class Resync(BaseModel):
    otp1: str
    otp2: str


def auth(authorization: str | None) -> None:
    if authorization != "Bearer local-adapter-token":
        raise HTTPException(status_code=401, detail="Unauthorized")


def result(ok: bool) -> dict:
    return {"ok": ok, "returncode": 0 if ok else 1}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "development_only": True}


@app.post("/v1/users")
def create_user(payload: UserCreate, authorization: str | None = Header(default=None)) -> dict:
    auth(authorization)
    if payload.username in users:
        return result(False)
    users[payload.username] = {"enabled": True, "token": True}
    return result(True)


@app.get("/v1/users/{username}/provisioning")
def provisioning(username: str, authorization: str | None = Header(default=None)) -> dict:
    auth(authorization)
    if username not in users:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "provisioning_uri": (
            f"otpauth://totp/BlissSecureMFA:{username}"
            "?secret=JBSWY3DPEHPK3PXP&issuer=BlissSecureMFA"
        )
    }


@app.post("/v1/users/{username}/verify")
def verify(username: str, payload: Verify, authorization: str | None = Header(default=None)) -> dict:
    auth(authorization)
    user = users.get(username)
    return result(bool(user and user["enabled"] and user["token"] and payload.otp == "000000"))


@app.post("/v1/users/{username}/disable")
def disable(username: str, authorization: str | None = Header(default=None)) -> dict:
    auth(authorization)
    if username not in users:
        return result(False)
    users[username]["enabled"] = False
    return result(True)


@app.post("/v1/users/{username}/enable")
def enable(username: str, authorization: str | None = Header(default=None)) -> dict:
    auth(authorization)
    if username not in users:
        return result(False)
    users[username]["enabled"] = True
    return result(True)


@app.post("/v1/users/{username}/unlock")
def unlock(username: str, authorization: str | None = Header(default=None)) -> dict:
    auth(authorization)
    return result(username in users)


@app.post("/v1/users/{username}/revoke")
def revoke(username: str, authorization: str | None = Header(default=None)) -> dict:
    auth(authorization)
    if username not in users:
        return result(False)
    users[username]["token"] = False
    return result(True)


@app.post("/v1/users/{username}/resync")
def resync(
    username: str,
    payload: Resync,
    authorization: str | None = Header(default=None),
) -> dict:
    auth(authorization)
    return result(username in users and payload.otp1.isdigit() and payload.otp2.isdigit())


@app.delete("/v1/users/{username}")
def delete_user(username: str, authorization: str | None = Header(default=None)) -> dict:
    auth(authorization)
    return result(users.pop(username, None) is not None)
