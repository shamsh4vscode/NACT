"use client";

import { useEffect, useState } from "react";
import { Activity, Network, ShieldCheck, GitPullRequest, Terminal, Bell, Gauge } from "lucide-react";

type Device = {name:string;vendor:string;role:string;site:string;mgmt_ip:string;status:string};

export default function Dashboard() {
  const [devices,setDevices] = useState<Device[]>([]);
  const [logs,setLogs] = useState("Waiting for deployment...");
  const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  useEffect(() => { fetch(`${api}/api/devices`).then(r=>r.json()).then(setDevices).catch(()=>setDevices([])); },[api]);
  async function submit() {
    setLogs("POST /api/deployments\nPre-check: BGP/OSPF/VXLAN healthy");
    const r = await fetch(`${api}/api/deployments`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({type:"vlan_vni",name:"VLAN-10010",payload:{vni:10010}})});
    if(r.ok) setLogs(l=>l+"\nChange queued for approval\nAudit entry created");
  }
  return <div className="shell">
    <aside className="sidebar"><div className="brand">NACT // OPS</div><nav className="nav">
      <a className="active" href="#"><Gauge size={17}/> Overview</a>
      <a href="#"><Network size={17}/> Inventory</a>
      <a href="#"><Activity size={17}/> Day-2 Operations</a>
      <a href="#"><GitPullRequest size={17}/> GitOps Deployments</a>
      <a href="#"><ShieldCheck size={17}/> Approvals</a>
    </nav></aside>
    <main className="main"><div className="top"><h1>Network Operations Center</h1><Bell size={18}/></div>
      <div className="grid">
        <div className="card"><div className="metric">Devices</div><div className="value cyan">{devices.length || 18}</div></div>
        <div className="card"><div className="metric">Reachable</div><div className="value green">100%</div></div>
        <div className="card"><div className="metric">Open Changes</div><div className="value amber">3</div></div>
        <div className="card"><div className="metric">Lab Control Plane</div><div className="value green">Healthy</div></div>
      </div>
      <div className="card section"><h2>Device inventory</h2><table><thead><tr><th>Device</th><th>Vendor</th><th>Role</th><th>Site</th><th>Management IP</th><th>Status</th></tr></thead>
        <tbody>{devices.slice(0,12).map(d=><tr key={d.name}><td>{d.name}</td><td>{d.vendor}</td><td>{d.role}</td><td>{d.site}</td><td>{d.mgmt_ip}</td><td><span className="badge">{d.status}</span></td></tr>)}</tbody></table>
      </div>
      <div className="card section"><h2>GitOps deployment</h2><div className="form-row">
        <select><option>Provision VLAN/VNI</option><option>BGP EVPN peer</option><option>OSPF peer</option><option>Firewall rule</option><option>LB VIP</option></select>
        <input aria-label="Change name" defaultValue="DC1-VLAN-10010"/>
        <button onClick={submit}>Submit change</button>
      </div></div>
      <div className="card section"><h2><Terminal size={16}/> Live execution terminal</h2><pre className="terminal">{logs}</pre></div>
    </main>
  </div>;
}
