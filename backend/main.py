from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from datetime import datetime
from jose import JWTError, jwt
from starlette.middleware.sessions import SessionMiddleware
from typing import Literal
from uuid import uuid4
import asyncio
import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
import subprocess

from kombu.exceptions import OperationalError
import httpx
import redis
from sqlalchemy import select

from database import AuditEvent, DeploymentJob, JobEvent, SessionLocal, initialize_database
from device_client import DeviceConnectionError, run_frr_command, run_frr_operation
from workers.tasks import execute_deployment

APP = FastAPI(title="NACT Network & Security Operations", version="1.0.0")
APP.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)
APP.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "local-development-session-secret"),
    same_site="lax",
    https_only=os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true",
    max_age=8 * 60 * 60,
)
app = APP


@APP.on_event("startup")
def startup():
    initialize_database()


OIDC_PUBLIC_ISSUER = os.getenv("OIDC_PUBLIC_ISSUER", "http://localhost:8080/realms/nact")
OIDC_INTERNAL_ISSUER = os.getenv("OIDC_INTERNAL_ISSUER", "http://keycloak:8080/realms/nact")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "nact-api")
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "nact-api-dev-secret")
OIDC_REDIRECT_URI = os.getenv(
    "OIDC_REDIRECT_URI", "http://localhost:8000/api/auth/oidc/callback"
)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
DEVICE_MODE = os.getenv("NACT_DEVICE_MODE", "simulated")
OIDC_STATE_STORE = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True,
)


def decode_oidc_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as error:
        raise HTTPException(401, "Invalid identity token") from error
    response = httpx.get(
        f"{OIDC_INTERNAL_ISSUER}/protocol/openid-connect/certs",
        timeout=5,
    )
    response.raise_for_status()
    key = next(
        (
            candidate
            for candidate in response.json().get("keys", [])
            if candidate.get("kid") == header.get("kid")
        ),
        None,
    )
    if key is None:
        raise HTTPException(401, "Identity token signing key was not found")
    try:
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=OIDC_CLIENT_ID,
            issuer=OIDC_PUBLIC_ISSUER,
        )
    except JWTError as error:
        raise HTTPException(401, "Invalid identity token") from error


def user_from_claims(claims: dict) -> dict:
    realm_access = claims.get("realm_access", {})
    return {
        "username": claims.get("preferred_username") or claims.get("sub", ""),
        "roles": realm_access.get("roles", []),
    }


def get_current_user(request: Request) -> dict:
    authorization = request.headers.get("authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Bearer token required")
        return user_from_claims(decode_oidc_token(token))
    user = request.session.get("user")
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


def require_role(user: dict, *roles: str) -> None:
    if not set(user.get("roles", [])).intersection(roles):
        raise HTTPException(403, "Insufficient role")


@APP.get("/api/auth/oidc/login")
def oidc_login():
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    OIDC_STATE_STORE.setex(
        f"oidc:{state}",
        300,
        f"{nonce}\n{verifier}",
    )
    query = urlencode({
        "client_id": OIDC_CLIENT_ID,
        "redirect_uri": OIDC_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return RedirectResponse(
        f"{OIDC_PUBLIC_ISSUER}/protocol/openid-connect/auth?{query}"
    )


@APP.get("/api/auth/oidc/callback")
async def oidc_callback(request: Request, code: str, state: str):
    transaction = OIDC_STATE_STORE.getdel(f"oidc:{state}")
    if not transaction:
        raise HTTPException(400, "OIDC state is invalid or expired")
    nonce, verifier = transaction.split("\n", maxsplit=1)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{OIDC_INTERNAL_ISSUER}/protocol/openid-connect/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": OIDC_CLIENT_ID,
                    "client_secret": OIDC_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": OIDC_REDIRECT_URI,
                    "code_verifier": verifier,
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise HTTPException(401, "OIDC authorization code was rejected") from error
    except httpx.RequestError as error:
        raise HTTPException(503, "Identity provider is unavailable") from error

    token_response = response.json()
    claims = decode_oidc_token(token_response.get("id_token", ""))
    if claims.get("nonce") != nonce:
        raise HTTPException(401, "OIDC nonce validation failed")
    request.session.clear()
    request.session["user"] = user_from_claims(claims)
    return RedirectResponse(FRONTEND_URL)


@APP.get("/api/auth/me")
def auth_me(user: dict = Depends(get_current_user)):
    return user


@APP.post("/api/auth/logout")
def auth_logout(request: Request):
    request.session.clear()
    return {"status": "logged_out"}

DEVICES = [
    {"name": "spine-01", "vendor": "FRR", "role": "spine", "site": "DC1", "mgmt_ip": "172.20.20.11", "status": "simulated"},
    {"name": "spine-02", "vendor": "FRR", "role": "spine", "site": "DC1", "mgmt_ip": "172.20.20.12", "status": "simulated"},
]
for i in range(1,5):
    DEVICES.append({"name": f"leaf-{i:02}", "vendor": "FRR", "role": "leaf", "site": "DC1", "mgmt_ip": f"172.20.20.{i+12}", "status": "simulated"})
for i in range(1,3):
    DEVICES += [
        {"name": f"border-{i:02}", "vendor": "FRR", "role": "border", "site": "DC1", "mgmt_ip": f"172.20.20.{i+16}", "status": "simulated"},
        {"name": f"wan-rtr-{i:02}", "vendor": "FRR", "role": "wan", "site": "WAN", "mgmt_ip": f"172.20.20.{i+18}", "status": "simulated"},
    ]
for i in range(1,3):
    DEVICES.append({"name": f"host-{i:02}", "vendor": "Alpine", "role": "host", "site": "DC1", "mgmt_ip": f"172.20.20.{i+20}", "status": "simulated"})


def device_status(device: dict) -> dict:
    result = device.copy()
    if DEVICE_MODE != "live":
        return result
    if device["role"] == "host":
        try:
            probe = subprocess.run(
                ["ping", "-c", "1", "-W", "1", device["mgmt_ip"]],
                capture_output=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            result["status"] = "unreachable"
        else:
            result["status"] = "reachable" if probe.returncode == 0 else "unreachable"
        return result
    try:
        run_frr_command(device["mgmt_ip"], "vtysh -c 'show version'")
    except DeviceConnectionError:
        result["status"] = "unreachable"
    else:
        result["status"] = "reachable"
    return result

@APP.get("/api/health")
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@APP.get("/api/devices")
def devices():
    if DEVICE_MODE != "live":
        return DEVICES
    with ThreadPoolExecutor(max_workers=12) as executor:
        return list(executor.map(device_status, DEVICES))

@APP.get("/api/devices/{name}")
def device(name: str):
    found = next((d for d in DEVICES if d["name"] == name), None)
    if not found: raise HTTPException(404, "Device not found")
    return device_status(found)

@APP.get("/api/operations/{name}/{kind}")
def operation(name: str, kind: Literal["ospf","bgp","vxlan","diagnostics"]):
    found = next((d for d in DEVICES if d["name"] == name), None)
    if found is None:
        raise HTTPException(404, "Device not found")
    if DEVICE_MODE == "live":
        try:
            result = run_frr_operation(found["mgmt_ip"], kind)
        except DeviceConnectionError as error:
            raise HTTPException(502, str(error)) from error
        return {
            "device": name,
            "operation": kind,
            "data": result["data"],
            "command": result["command"],
            "mode": "live",
        }
    if kind == "ospf":
        data = {"neighbors": [{"neighbor": "spine-01", "state": "FULL"}]}
    elif kind == "bgp":
        data = {"neighbors": [{"peer": "EVPN-RR", "state": "Established", "afi": "l2vpn evpn"}]}
    elif kind == "vxlan":
        data = {"interface": "vxlan1", "status": "UP", "vnis": [10010,10020]}
    else:
        data = {"reachable": True, "latency_ms": 1.2}
    return {"device": name, "operation": kind, "data": data, "mode": "simulated"}

class Deployment(BaseModel):
    type: Literal["vlan_vni","bgp","ospf","firewall","lb"]
    name: str
    payload: dict

@APP.post("/api/deployments")
def create_deployment(body: Deployment, user: dict = Depends(get_current_user)):
    if body.type == "firewall" and not set(user["roles"]).intersection(("sec_engineer", "net_admin")):
        raise HTTPException(403, "Firewall deployment requires sec_engineer or net_admin")
    if body.type in ("bgp", "ospf") and "net_admin" not in user["roles"]:
        raise HTTPException(403, "Routing deployment requires net_admin")
    if body.type in ("vlan_vni", "lb") and "net_admin" not in user["roles"]:
        raise HTTPException(403, "Deployment requires net_admin")
    job_id = str(uuid4())
    with SessionLocal.begin() as session:
        job = DeploymentJob(
            id=job_id,
            status="pending_approval",
            deployment=body.model_dump(),
        )
        session.add(job)
        session.add(AuditEvent(job_id=job_id, action="submitted", actor=user["username"]))
    return {"id": job_id, "status": "pending_approval", "deployment": body.model_dump()}

@APP.get("/api/deployments")
def deployments(user: dict = Depends(get_current_user)):
    with SessionLocal() as session:
        jobs = session.scalars(select(DeploymentJob).order_by(DeploymentJob.created_at.desc())).all()
        return [
            {"id": job.id, "status": job.status, "deployment": job.deployment}
            for job in jobs
        ]

@APP.get("/api/deployments/{job_id}")
def deployment(job_id: str, user: dict = Depends(get_current_user)):
    with SessionLocal() as session:
        job = session.get(DeploymentJob, job_id)
        if job is None:
            raise HTTPException(404, "Job not found")
        return {"id": job.id, "status": job.status, "deployment": job.deployment}

@APP.post("/api/deployments/{job_id}/approve")
def approve(job_id: str, user: dict = Depends(get_current_user)):
    require_role(user, "net_admin")
    with SessionLocal.begin() as session:
        job = session.scalar(
            select(DeploymentJob).where(DeploymentJob.id == job_id).with_for_update()
        )
        if job is None:
            raise HTTPException(404, "Job not found")
        if job.status != "pending_approval":
            raise HTTPException(409, "Job is not pending approval")
        job.status = "executing"
        session.add(AuditEvent(job_id=job_id, action="approved", actor=user["username"]))

    try:
        execute_deployment.delay(job_id)
    except OperationalError as error:
        with SessionLocal.begin() as session:
            job = session.get(DeploymentJob, job_id)
            if job is not None:
                job.status = "failed"
                session.add(JobEvent(
                    job_id=job_id,
                    level="error",
                    message="Could not enqueue deployment execution",
                    status="failed",
                ))
                session.add(AuditEvent(job_id=job_id, action="failed", actor="system"))
        raise HTTPException(503, "Deployment queue is unavailable") from error
    return {"id": job_id, "status": "executing", "deployment": job.deployment}

@APP.get("/api/audit")
def audit(user: dict = Depends(get_current_user)):
    require_role(user, "net_admin", "sec_engineer")
    with SessionLocal() as session:
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
        return [
            {
                "job_id": event.job_id,
                "action": event.action,
                "actor": event.actor,
                "at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ]

@APP.websocket("/ws/jobs/{job_id}")
async def websocket_job(websocket: WebSocket, job_id: str):
    user = websocket.session.get("user")
    if not user:
        authorization = websocket.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                user = user_from_claims(decode_oidc_token(token))
            except HTTPException:
                user = None
    if not user:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    with SessionLocal() as session:
        job = session.get(DeploymentJob, job_id)
    if job is None:
        await websocket.send_json({"job_id": job_id, "level": "error", "message": "Job not found"})
        await websocket.close(code=1008)
        return

    last_event_id = 0
    try:
        with SessionLocal() as session:
            has_events = session.scalar(
                select(JobEvent.id).where(JobEvent.job_id == job_id).limit(1)
            ) is not None
        if job.status == "pending_approval" and not has_events:
            await websocket.send_json({
                "job_id": job_id,
                "level": "info",
                "status": "pending_approval",
                "message": "Waiting for approval",
            })
        while True:
            with SessionLocal() as session:
                events = session.scalars(
                    select(JobEvent)
                    .where(JobEvent.job_id == job_id, JobEvent.id > last_event_id)
                    .order_by(JobEvent.id)
                ).all()
                job = session.get(DeploymentJob, job_id)
            for event in events:
                await websocket.send_json({
                    "job_id": job_id,
                    "level": event.level,
                    "message": event.message,
                    **({"status": event.status} if event.status else {}),
                })
                last_event_id = event.id
            if job is None or (job.status in {"completed", "failed"} and not events):
                await websocket.close()
                return
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass
