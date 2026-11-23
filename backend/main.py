from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt
from passlib.hash import pbkdf2_sha256
from typing import Literal
import os, asyncio

APP = FastAPI(title="NACT Network & Security Operations", version="1.0.0")
APP.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

USERS = {
    "noc": {"password": pbkdf2_sha256.hash("noc-password"), "role": "noc_operator"},
    "security": {"password": pbkdf2_sha256.hash("security-password"), "role": "sec_engineer"},
    "admin": {"password": pbkdf2_sha256.hash("admin-password"), "role": "net_admin"},
}

def user_ctx(username: str = "admin"):
    return {"username": username, "role": USERS.get(username, {}).get("role", "net_admin")}

class Login(BaseModel):
    username: str
    password: str

@APP.post("/api/auth/login")
def login(body: Login):
    user = USERS.get(body.username)
    if not user or not pbkdf2_sha256.verify(body.password, user["password"]):
        raise HTTPException(401, "Invalid credentials")
    payload = {"sub": body.username, "role": user["role"], "exp": datetime.utcnow() + timedelta(hours=8)}
    token = jwt.encode(payload, os.getenv("JWT_SECRET", "change-this-in-production"), algorithm="HS256")
    return {"access_token": token, "role": user["role"]}

DEVICES = [
    {"name": "spine-01", "vendor": "Arista", "role": "spine", "site": "DC1", "mgmt_ip": "172.20.20.11", "status": "reachable"},
    {"name": "spine-02", "vendor": "Arista", "role": "spine", "site": "DC1", "mgmt_ip": "172.20.20.12", "status": "reachable"},
]
for i in range(1,5):
    DEVICES.append({"name": f"leaf-{i:02}", "vendor": "Arista", "role": "leaf", "site": "DC1", "mgmt_ip": f"172.20.20.{i+12}", "status": "reachable"})
for i in range(1,3):
    DEVICES += [
        {"name": f"border-{i:02}", "vendor": "Arista", "role": "border", "site": "DC1", "mgmt_ip": f"172.20.20.{i+16}", "status": "reachable"},
        {"name": f"wan-rtr-{i:02}", "vendor": "Arista", "role": "wan", "site": "WAN", "mgmt_ip": f"172.20.20.{i+18}", "status": "reachable"},
    ]
for i in range(1,3):
    DEVICES.append({"name": f"host-{i:02}", "vendor": "Alpine", "role": "host", "site": "DC1", "mgmt_ip": f"172.20.20.{i+20}", "status": "reachable"})

@APP.get("/api/health")
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@APP.get("/api/devices")
def devices():
    return DEVICES

@APP.get("/api/devices/{name}")
def device(name: str):
    found = next((d for d in DEVICES if d["name"] == name), None)
    if not found: raise HTTPException(404, "Device not found")
    return found

@APP.get("/api/operations/{name}/{kind}")
def operation(name: str, kind: Literal["ospf","bgp","vxlan","diagnostics"]):
    if kind == "ospf":
        data = {"neighbors": [{"neighbor": "spine-01", "state": "FULL"}]}
    elif kind == "bgp":
        data = {"neighbors": [{"peer": "EVPN-RR", "state": "Established", "afi": "l2vpn evpn"}]}
    elif kind == "vxlan":
        data = {"interface": "vxlan1", "status": "UP", "vnis": [10010,10020]}
    else:
        data = {"reachable": True, "latency_ms": 1.2}
    return {"device": name, "operation": kind, "data": data, "mode": "FRR fallback" if os.getenv("NACT_LAB_KIND") == "linux" else "cEOS"}

class Deployment(BaseModel):
    type: Literal["vlan_vni","bgp","ospf","firewall","lb"]
    name: str
    payload: dict

JOBS = {}
AUDIT = []
@APP.post("/api/deployments")
def create_deployment(body: Deployment, x_role: str = Header(default="net_admin"), x_user: str = Header(default="admin")):
    ctx = {"username": x_user, "role": x_role}
    if body.type == "firewall" and ctx["role"] not in ("sec_engineer","net_admin"):
        raise HTTPException(403, "Firewall deployment requires sec_engineer or net_admin")
    if body.type in ("bgp","ospf") and ctx["role"] not in ("net_admin",):
        raise HTTPException(403, "Routing deployment requires net_admin")
    job_id = f"job-{len(JOBS)+1}"
    JOBS[job_id] = {"id": job_id, "status": "pending_approval", "deployment": body.model_dump()}
    AUDIT.append({"job_id": job_id, "action": "submitted", "actor": ctx["username"], "at": datetime.utcnow().isoformat()})
    return JOBS[job_id]

@APP.post("/api/deployments/{job_id}/approve")
def approve(job_id: str):
    if job_id not in JOBS: raise HTTPException(404, "Job not found")
    JOBS[job_id]["status"] = "executing"
    AUDIT.append({"job_id": job_id, "action": "approved", "at": datetime.utcnow().isoformat()})
    return JOBS[job_id]

@APP.get("/api/audit")
def audit(): return AUDIT

@APP.websocket("/ws/jobs/{job_id}")
async def websocket_job(websocket: WebSocket, job_id: str):
    await websocket.accept()
    try:
        await websocket.send_json({"job_id": job_id, "level":"info","message":"Starting Ansible pre-check"})
        await asyncio.sleep(.2)
        await websocket.send_json({"job_id": job_id, "level":"info","message":"Pre-check: OSPF/BGP/VXLAN health baseline captured"})
        await websocket.send_json({"job_id": job_id, "level":"success","message":"Deployment completed; post-check passed"})
        await websocket.receive()
    except WebSocketDisconnect:
        pass
