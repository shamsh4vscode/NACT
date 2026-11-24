from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import random

app = FastAPI(title="NACT Multi-Vendor API/CLI Simulator")

devices = {
    "pan-os": {"type":"Palo Alto","health":"healthy","rules":[]},
    "fortios": {"type":"Fortinet","health":"healthy","rules":[]},
    "asa": {"type":"Cisco ASA","health":"healthy","rules":[]},
    "ftd": {"type":"Cisco FTD","health":"healthy","rules":[]},
    "f5": {"type":"F5 BIG-IP","health":"healthy","pools":[{"name":"web-pool","members":[{"address":"10.10.10.21","state":"up"},{"address":"10.10.10.22","state":"up"}]}]},
    "citrix": {"type":"Citrix ADC","health":"healthy","services":[{"name":"web-vip","state":"up"}]},
    "haproxy": {"type":"HAProxy","health":"healthy","backends":[{"name":"web","servers":[{"name":"srv1","state":"up"},{"name":"srv2","state":"up"}]}]},
}

class Change(BaseModel):
    name: str
    payload: dict = {}
    fail: bool = False

@app.get("/api/health")
def health(): return {"status":"healthy","vendors":list(devices)}

@app.get("/", response_class=HTMLResponse)
def simulator_dashboard():
    vendor_links = "".join(
        f'<li><a href="/api/{vendor}">{details["type"]} ({vendor})</a></li>'
        for vendor, details in devices.items()
    )
    return f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>NACT Vendor Simulators</title>
    <style>
      body {{ max-width: 760px; margin: 3rem auto; padding: 0 1rem; background: #070b14; color: #dbe7f5; font: 16px system-ui, sans-serif; }}
      a {{ color: #67e8f9; }} li {{ margin: .8rem 0; }} .status {{ color: #34d399; }}
    </style>
  </head>
  <body>
    <h1>NACT Vendor Simulators</h1>
    <p class="status">Service healthy</p>
    <p>These are demo APIs, not vendor production systems.</p>
    <ul>{vendor_links}</ul>
    <p><a href="/docs">Interactive API documentation</a> · <a href="/api/health">Health JSON</a></p>
  </body>
</html>"""

@app.get("/api/{vendor}")
def get_vendor(vendor: str):
    if vendor not in devices: raise HTTPException(404,"Unknown vendor")
    return devices[vendor]

@app.post("/api/{vendor}/changes")
def change(vendor: str, body: Change):
    if vendor not in devices: raise HTTPException(404,"Unknown vendor")
    if body.fail:
        if vendor == "f5": devices[vendor]["pools"][0]["members"][1]["state"]="down"
        raise HTTPException(409,"Injected failure: post-check health degraded")
    if vendor in ("pan-os","fortios","asa","ftd"):
        devices[vendor]["rules"].append({"name":body.name, **body.payload})
    elif vendor == "f5":
        devices[vendor]["pools"][0]["members"][1]["state"]="up"
    elif vendor == "citrix":
        devices[vendor]["services"].append({"name":body.name,"state":"up"})
    elif vendor == "haproxy":
        devices[vendor]["backends"][0]["servers"].append({"name":body.name,"state":"up"})
    return {"status":"accepted","vendor":vendor,"change":body.name}

@app.post("/api/{vendor}/rollback")
def rollback(vendor: str):
    if vendor not in devices: raise HTTPException(404,"Unknown vendor")
    if vendor == "f5":
        for member in devices[vendor]["pools"][0]["members"]: member["state"]="up"
    return {"status":"rolled_back","vendor":vendor}
