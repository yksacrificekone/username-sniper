"""Kxne Sniper server: auth API + combo-run control + live stats + web UI."""
from __future__ import annotations

import asyncio
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from engine.auth import AuthManager
from engine.config import Config
from engine.github import GitHubEngine
from engine.license import LicenseManager
from engine.redeem import RedemptionManager

cfg = Config()
auth = AuthManager(
    users_file=cfg.get("auth", "users_file", "users.json"),
    session_file=cfg.get("auth", "session_file", "session.json"),
    trial_seconds=int(float(cfg.get("auth", "trial_minutes", 10)) * 60),
)
lic = LicenseManager(cfg)
redeem = RedemptionManager(cfg.get("auth", "redeemed_file", "redeemed.json"))

app = FastAPI(title="Kxne Sniper")
app.mount("/static", StaticFiles(directory="static"), name="static")

state = {"engine": None, "task": None}


def _license_provider(username: str, premium: bool):
    def provider():
        if premium:
            return True, None
        s = auth.session()
        if not s:
            return False, 0.0
        return False, lic.remaining_seconds(s.get("expires_ts"), False)
    return provider


async def _run_job(settings: dict):
    try:
        await state["engine"].run_sniper(settings)
    finally:
        state["task"] = None


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.post("/api/signup")
async def signup(req: dict):
    ok, msg = auth.signup(str(req.get("username", "")), str(req.get("password", "")))
    if ok:
        auth.login(str(req["username"]), str(req["password"]))
    return {"ok": ok, "msg": msg}


@app.post("/api/login")
async def login(req: dict):
    ok, msg, _user = auth.login(str(req.get("username", "")), str(req.get("password", "")))
    return {"ok": ok, "msg": msg}


@app.post("/api/logout")
async def logout():
    auth.logout()
    return {"ok": True}


@app.get("/api/status")
async def status():
    session = auth.session()
    if not session:
        return {"logged_in": False}
    username = session["username"]
    premium = auth.is_premium(username)
    remaining = lic.remaining_seconds(session.get("expires_ts"), premium)
    return {
        "logged_in": True,
        "username": username,
        "premium": premium,
        "time_left": remaining,
        "workers": lic.effective_threads(999999, premium),
        "max_workers": lic.premium_threads if premium else lic.trial_threads,
    }


@app.post("/api/redeem")
async def do_redeem(req: dict):
    session = auth.session()
    if not session:
        return {"ok": False, "msg": "not logged in"}
    ok, msg = redeem.redeem(session["username"], str(req.get("code", "")), str(req.get("type", "")))
    if ok:
        auth.grant_premium(session["username"], 30)
    return {"ok": ok, "msg": msg}


@app.post("/api/run")
async def run(req: dict):
    if state["task"] and not state["task"].done():
        return {"ok": False, "msg": "already running"}
    session = auth.session()
    if not session:
        return {"ok": False, "msg": "not logged in"}

    username = session["username"]
    premium = auth.is_premium(username)
    effective = lic.effective_threads(999999, premium)
    cfg.data["network"]["connections"] = effective

    old = state["engine"]
    if old:
        await old.close()

    engine = GitHubEngine(cfg, license_provider=_license_provider(username, premium))
    engine.stats.license = "PREMIUM" if premium else "TRIAL"
    engine.stats.time_left = lic.remaining_seconds(session.get("expires_ts"), premium) or 0.0
    engine.stats.add_event(f"license: {engine.stats.license} · workers: {effective}", "info")
    await engine.start()
    state["engine"] = engine

    settings = {
        "min_len": int(req.get("min_len", 3)),
        "max_len": int(req.get("max_len", 5)),
        "charset": str(req.get("charset", "letters_and_numbers")),
        "auto_claim": bool(req.get("auto_claim", False)),
    }
    state["task"] = asyncio.create_task(_run_job(settings))
    return {"ok": True}


@app.post("/api/stop")
async def stop():
    if state["engine"]:
        state["engine"].stop()
    return {"ok": True}


@app.get("/api/stats")
async def stats():
    engine = state["engine"]
    if not engine:
        return {"running": False, "stats": None}
    if engine.sem is not None:
        engine.stats.busy = engine.stats.workers - engine.sem._value
    running = bool(state["task"] and not state["task"].done())
    return {"running": running, "stats": engine.stats.snapshot()}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
