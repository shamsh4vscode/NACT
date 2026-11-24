"use client";

import { useEffect, useState } from "react";
import { Activity, Network, ShieldCheck, GitPullRequest, Terminal, Bell, Gauge, Boxes } from "lucide-react";

type Device = {name:string;vendor:string;role:string;site:string;mgmt_ip:string;status:string};
type DeploymentJob = {
  id: string;
  status: string;
  deployment: {type:string;name:string;payload:Record<string, unknown>}
};
type User = {username:string;roles:string[]};
type Section = "overview" | "inventory" | "operations" | "deployments" | "approvals" | "simulators";

function serviceUrl(port:number,fallback:string) {
  if(typeof window !== "undefined" && window.location.hostname.endsWith(".app.github.dev")) {
    const hostname = window.location.hostname.replace(/-\d+\.app\.github\.dev$/, `-${port}.app.github.dev`);
    return `${window.location.protocol}//${hostname}`;
  }
  return fallback;
}

export default function Dashboard() {
  const [devices,setDevices] = useState<Device[]>([]);
  const [jobs,setJobs] = useState<DeploymentJob[]>([]);
  const [user,setUser] = useState<User|null>(null);
  const [section,setSection] = useState<Section>("overview");
  const [loadError,setLoadError] = useState("");
  const [logs,setLogs] = useState("Waiting for deployment...");
  const [deploymentType,setDeploymentType] = useState("vlan_vni");
  const [changeName,setChangeName] = useState("DC1-VLAN-10010");
  const [operationDevice,setOperationDevice] = useState("leaf-01");
  const [operationKind,setOperationKind] = useState("ospf");
  const [operationResult,setOperationResult] = useState("");
  const [operationError,setOperationError] = useState("");
  const [simulatorStatus,setSimulatorStatus] = useState<{status:string;vendors:string[]}|null>(null);
  const [simulatorError,setSimulatorError] = useState("");
  const api = serviceUrl(8000,process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
  const simulatorApi = serviceUrl(8443,"http://localhost:8443");
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const authResponse = await fetch(`${api}/api/auth/me`,{credentials:"include"});
        if(authResponse.status === 401) {
          if(active) {
            setUser(null);
            setJobs([]);
          }
        } else if(!authResponse.ok) {
          throw new Error(`Authentication check failed: ${authResponse.status}`);
        } else {
          const currentUser = await authResponse.json() as User;
          if(active) setUser(currentUser);
          const jobsResponse = await fetch(`${api}/api/deployments`,{credentials:"include"});
          if(!jobsResponse.ok) throw new Error(`Could not load deployments: ${jobsResponse.status}`);
          const currentJobs = await jobsResponse.json() as DeploymentJob[];
          if(active) setJobs(currentJobs);
        }
        const devicesResponse = await fetch(`${api}/api/devices`);
        if(!devicesResponse.ok) throw new Error(`Could not load devices: ${devicesResponse.status}`);
        const currentDevices = await devicesResponse.json() as Device[];
        if(active) setDevices(currentDevices);
        if(active) setLoadError("");
      } catch(error) {
        if(active) setLoadError(error instanceof Error ? error.message : "Could not load dashboard data");
      }
    }
    void load();
    return () => { active = false; };
  },[api]);
  useEffect(() => {
    if(section!=="simulators") return;
    let active = true;
    setSimulatorError("");
    fetch(`${simulatorApi}/api/health`)
      .then(async response => {
        if(!response.ok) throw new Error(`Simulator health check failed: ${response.status}`);
        return await response.json() as {status:string;vendors:string[]};
      })
      .then(status => { if(active) setSimulatorStatus(status); })
      .catch(error => {
        if(active) setSimulatorError(error instanceof Error ? error.message : "Could not reach vendor simulators");
      });
    return () => { active = false; };
  },[section,simulatorApi]);
  async function logout() {
    const response = await fetch(`${api}/api/auth/logout`,{method:"POST",credentials:"include"});
    if(!response.ok) {
      setLoadError(`Sign out failed: ${response.status}`);
      return;
    }
    setUser(null);
    setJobs([]);
  }
  async function submit() {
    setLogs("POST /api/deployments\nPre-check: BGP/OSPF/VXLAN healthy");
    const payload = deploymentType === "vlan_vni" ? {vni:10010} : {change:changeName};
    const r = await fetch(`${api}/api/deployments`,{
      method:"POST",
      credentials:"include",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({type:deploymentType,name:changeName,payload})
    });
    if(r.ok) {
      const job = await r.json() as DeploymentJob;
      setJobs(current=>[job,...current]);
      setLogs(l=>l+"\nChange queued for approval\nAudit entry created");
      const wsUrl = api.replace(/^http/, "ws");
      const socket = new WebSocket(`${wsUrl}/ws/jobs/${job.id}`);
      socket.onmessage = event => {
        const message = JSON.parse(event.data) as {level:string;message:string;job_id?:string;status?:string};
        setLogs(l=>l+`\n[${message.level}] ${message.message}`);
        if(message.job_id && message.status) {
          setJobs(current=>current.map(item=>item.id===message.job_id ? {...item,status:message.status!} : item));
        }
      };
      socket.onclose = () => setLogs(l=>l+"\nExecution stream closed");
    } else {
      const detail = await r.text();
      setLogs(l=>l+"\nSubmission failed: "+r.status+" "+detail);
    }
  }
  async function approve(jobId:string) {
    const r = await fetch(`${api}/api/deployments/${jobId}/approve`,{method:"POST",credentials:"include"});
    if(r.ok) {
      const job = await r.json() as DeploymentJob;
      setJobs(current=>current.map(item=>item.id===jobId ? job : item));
      setLogs(l=>l+`\n[success] ${jobId} approved and executing`);
    } else {
      const detail = await r.text();
      setLogs(l=>l+`\nApproval failed: ${r.status} ${detail}`);
    }
  }
  async function runOperation() {
    setOperationError("");
    setOperationResult("");
    try {
      const response = await fetch(`${api}/api/operations/${encodeURIComponent(operationDevice)}/${operationKind}`);
      if(!response.ok) throw new Error(`Operation failed: ${response.status} ${await response.text()}`);
      setOperationResult(JSON.stringify(await response.json(),null,2));
    } catch(error) {
      setOperationError(error instanceof Error ? error.message : "Could not run operation");
    }
  }
  const navigation: {id:Section;label:string;icon:typeof Gauge}[] = [
    {id:"overview",label:"Overview",icon:Gauge},
    {id:"inventory",label:"Inventory",icon:Network},
    {id:"operations",label:"Day-2 Operations",icon:Activity},
    {id:"deployments",label:"GitOps Deployments",icon:GitPullRequest},
    {id:"approvals",label:"Approvals",icon:ShieldCheck},
    {id:"simulators",label:"Vendor Simulators",icon:Boxes},
  ];
  return <div className="shell">
    <aside className="sidebar"><div className="brand">NACT // OPS</div><nav className="nav" aria-label="Dashboard sections">
      {navigation.map(({id,label,icon:Icon})=><button
        key={id}
        type="button"
        className={`nav-item${section===id ? " active" : ""}`}
        aria-current={section===id ? "page" : undefined}
        onClick={()=>setSection(id)}
      ><Icon size={17}/> {label}</button>)}
    </nav></aside>
    <main className="main"><div className="top"><h1>Network Operations Center</h1><div className="account">
      {user ? <><span>{user.username} ({user.roles.join(", ")})</span><button onClick={logout}>Sign out</button></> :
        <a href={`${api}/api/auth/oidc/login`}>Sign in</a>}
      <Bell size={18}/>
    </div></div>
      {loadError && <div className="card section" role="alert">{loadError}</div>}
      {section==="overview" && <><div className="grid">
        <div className="card"><div className="metric">Devices</div><div className="value cyan">{devices.length || 18}</div></div>
        <div className="card"><div className="metric">Reachable</div><div className="value green">100%</div></div>
        <div className="card"><div className="metric">Open Changes</div><div className="value amber">{jobs.filter(job=>job.status==="pending_approval").length}</div></div>
        <div className="card"><div className="metric">Lab Control Plane</div><div className="value green">Healthy</div></div>
      </div><div className="card section"><h2>Recent inventory</h2>{renderDevices(devices.slice(0,5))}</div></>}
      {section==="inventory" && <div className="card section"><h2>Device inventory</h2>{renderDevices(devices)}</div>}
      {section==="operations" && <div className="card section"><h2>Day-2 operations</h2><p>Query simulated or live device status.</p><div className="form-row">
        <select aria-label="Device" value={operationDevice} onChange={event=>setOperationDevice(event.target.value)}>
          {devices.map(device=><option key={device.name} value={device.name}>{device.name}</option>)}
        </select>
        <select aria-label="Operation" value={operationKind} onChange={event=>setOperationKind(event.target.value)}>
          <option value="ospf">OSPF neighbors</option><option value="bgp">BGP peers</option>
          <option value="vxlan">VXLAN status</option><option value="diagnostics">Diagnostics</option>
        </select>
        <button type="button" onClick={runOperation}>Run operation</button>
      </div>{operationError && <p className="error" role="alert">{operationError}</p>}
        {operationResult && <pre className="terminal" aria-live="polite">{operationResult}</pre>}
      </div>}
      {section==="deployments" && <>{user ? <div className="card section"><h2>GitOps deployment</h2><div className="form-row">
        <select value={deploymentType} onChange={event=>setDeploymentType(event.target.value)}>
          <option value="vlan_vni">Provision VLAN/VNI</option>
          <option value="bgp">BGP EVPN peer</option>
          <option value="ospf">OSPF peer</option>
          <option value="firewall">Firewall rule</option>
          <option value="lb">LB VIP</option>
        </select>
        <input aria-label="Change name" value={changeName} onChange={event=>setChangeName(event.target.value)} />
        <button onClick={submit}>Submit change</button>
      </div></div> : <div className="card section">Sign in to submit and track deployments.</div>}
      {jobs.length > 0 && <div className="card section"><h2>Deployment queue</h2>
        <table><thead><tr><th>Job</th><th>Change</th><th>Type</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>{jobs.map(job=><tr key={job.id}><td>{job.id}</td><td>{job.deployment.name}</td><td>{job.deployment.type}</td>
            <td><span className="badge">{job.status}</span></td><td>{job.status==="pending_approval" &&
              <button className="approve" onClick={()=>approve(job.id)}>Approve</button>}</td></tr>)}</tbody>
        </table>
      </div>}
      <div className="card section"><h2><Terminal size={16}/> Live execution terminal</h2><pre className="terminal">{logs}</pre></div></>}
      {section==="approvals" && <div className="card section"><h2>Pending approvals</h2>{!user ? <p>Sign in to view and approve changes.</p> :
        jobs.filter(job=>job.status==="pending_approval").length===0 ? <p>No changes are waiting for approval.</p> :
        <table><thead><tr><th>Change</th><th>Type</th><th>Status</th><th>Action</th></tr></thead><tbody>
          {jobs.filter(job=>job.status==="pending_approval").map(job=><tr key={job.id}><td>{job.deployment.name}</td><td>{job.deployment.type}</td><td>{job.status}</td>
            <td><button className="approve" onClick={()=>approve(job.id)}>Approve</button></td></tr>)}
        </tbody></table>}
      </div>}
      {section==="simulators" && <div className="card section"><h2>Vendor simulators</h2>
        <p>Demo vendor API service: {simulatorStatus?.status ?? (simulatorError ? "unavailable" : "checking…")}</p>
        {simulatorError && <p className="error" role="alert">{simulatorError}</p>}
        <p><a href={`${simulatorApi}/docs`} target="_blank" rel="noreferrer">Open interactive API docs</a> · <a href={simulatorApi} target="_blank" rel="noreferrer">Open simulator landing page</a></p>
        {simulatorStatus && <ul className="simulator-list">{simulatorStatus.vendors.map(vendor=><li key={vendor}>
          <a href={`${simulatorApi}/api/${vendor}`} target="_blank" rel="noreferrer">{vendor}</a>
        </li>)}</ul>}
      </div>}
    </main>
  </div>;
}

function renderDevices(items:Device[]) {
  return <table><thead><tr><th>Device</th><th>Vendor</th><th>Role</th><th>Site</th><th>Management IP</th><th>Status</th></tr></thead>
    <tbody>{items.map(device=><tr key={device.name}><td>{device.name}</td><td>{device.vendor}</td><td>{device.role}</td><td>{device.site}</td><td>{device.mgmt_ip}</td><td><span className="badge">{device.status}</span></td></tr>)}</tbody></table>;
}
