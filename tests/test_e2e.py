import os
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
API = os.getenv("NACT_API_URL", "http://localhost:8000")

def get(path: str):
    r = httpx.get(API + path, timeout=3)
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
    denied = httpx.post(API+"/api/deployments", json=body,
                        headers={"x-role":"noc_operator","x-user":"noc"}, timeout=3)
    assert denied.status_code == 403
    allowed = httpx.post(API+"/api/deployments", json=body,
                         headers={"x-role":"net_admin","x-user":"admin"}, timeout=3)
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
    submitted = httpx.post(API+"/api/deployments", json=body,
                           headers={"x-role":"net_admin","x-user":"admin"}, timeout=3)
    assert submitted.status_code == 200
    job_id = submitted.json()["id"]
    approved = httpx.post(API+f"/api/deployments/{job_id}/approve", timeout=3)
    assert approved.status_code == 200
    assert approved.json()["status"] == "executing"
    audit = get("/api/audit")
    assert any(x["job_id"] == job_id for x in audit)
