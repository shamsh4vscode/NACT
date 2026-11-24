import asyncio
import json
import os
from pathlib import Path
import time

import httpx
import pytest
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
API = os.getenv("NACT_API_URL", "http://localhost:8000")
KEYCLOAK = os.getenv("NACT_KEYCLOAK_URL", "http://localhost:8080")

@pytest.fixture(scope="session", autouse=True)
def wait_for_keycloak():
    discovery = KEYCLOAK + "/realms/nact/.well-known/openid-configuration"
    for _ in range(60):
        try:
            response = httpx.get(discovery, timeout=1)
            if response.status_code == 200:
                return
        except (httpx.ConnectError, httpx.ConnectTimeout):
            pass
        time.sleep(1)
    pytest.fail("Keycloak did not become ready within 60 seconds")

def auth_headers(username: str, password: str) -> dict[str, str]:
    response = httpx.post(
        KEYCLOAK + "/realms/nact/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "nact-api",
            "client_secret": "nact-api-dev-secret",
            "username": username,
            "password": password,
        },
        timeout=10,
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

def get(path: str, headers: dict[str, str] | None = None):
    r = httpx.get(API + path, headers=headers, timeout=3)
    r.raise_for_status()
    return r.json()

def test_project_contract():
    assert (ROOT / "docker-compose.yml").exists()
    assert (ROOT / "lab-topology/enterprise-12node.clab.yml").exists()
    assert len([p for p in (ROOT / "lab-topology/configs").glob("*/frr.conf")]) == 10

def test_backend_health_and_inventory():
    health = get("/api/health")
    assert health["status"] == "healthy"
    devices = get("/api/devices")
    assert len(devices) >= 12

@pytest.mark.parametrize("kind,expected", [
    ("ospf", "FULL"),
    ("bgp", "Established"),
    ("vxlan", "UP"),
])
def test_lab_control_plane(kind, expected):
    result = get(f"/api/operations/leaf-01/{kind}")
    serialized = str(result)
    assert expected in serialized

def test_host_overlay_contract():
    assert "host-01" in [d["name"] for d in get("/api/devices")]
    assert "host-02" in [d["name"] for d in get("/api/devices")]

def test_rbac_routes():
    body = {"type":"bgp","name":"EVPN peer","payload":{"as":65099}}
    denied = httpx.post(
        API+"/api/deployments",
        json=body,
        headers=auth_headers("nact-noc", "noc-dev-password"),
        timeout=3,
    )
    assert denied.status_code == 403
    allowed = httpx.post(
        API+"/api/deployments",
        json=body,
        headers=auth_headers("nact-admin", "admin-dev-password"),
        timeout=3,
    )
    assert allowed.status_code == 200

def test_simulator_rollback_and_health():
    r = httpx.post("http://localhost:8443/api/f5/changes",
                   json={"name":"faulty-member","fail":True}, timeout=3)
    assert r.status_code == 409
    rolled = httpx.post("http://localhost:8443/api/f5/rollback", timeout=3)
    assert rolled.status_code == 200
    assert rolled.json()["status"] == "rolled_back"
    state = httpx.get("http://localhost:8443/api/f5", timeout=3).json()
    assert all(m["state"] == "up" for m in state["pools"][0]["members"])

def test_gitops_workflow():
    body = {"type":"vlan_vni","name":"VLAN10010","payload":{"vni":10010}}
    headers = auth_headers("nact-admin", "admin-dev-password")
    submitted = httpx.post(API+"/api/deployments", json=body,
                           headers=headers, timeout=3)
    assert submitted.status_code == 200
    job_id = submitted.json()["id"]

    async def approve_from_stream():
        async with connect(
            API.replace("http://", "ws://")+f"/ws/jobs/{job_id}",
            additional_headers=headers,
        ) as socket:
            waiting = json.loads(await asyncio.wait_for(socket.recv(), timeout=3))
            assert waiting["status"] == "pending_approval"
            assert waiting["message"] == "Waiting for approval"
            async with httpx.AsyncClient(timeout=3) as client:
                approved = await client.post(
                    API+f"/api/deployments/{job_id}/approve",
                    headers=headers,
                )
                assert approved.status_code == 200
                assert approved.json()["status"] == "executing"
            events = []
            while True:
                event = json.loads(await asyncio.wait_for(socket.recv(), timeout=3))
                events.append(event)
                if event.get("status") == "completed":
                    break
            return events

    events = asyncio.run(approve_from_stream())
    assert [event["message"] for event in events] == [
        "Starting Ansible pre-check",
        "Pre-check: OSPF/BGP/VXLAN health baseline captured",
        "Deployment completed; post-check passed",
    ]
    assert events[-1]["status"] == "completed"
    assert get(f"/api/deployments/{job_id}", headers=headers)["status"] == "completed"
    assert httpx.post(
        API+f"/api/deployments/{job_id}/approve",
        headers=headers,
        timeout=3,
    ).status_code == 409
    audit = get("/api/audit", headers=headers)
    assert {event["action"] for event in audit if event["job_id"] == job_id} == {
        "submitted", "approved", "completed"
    }
