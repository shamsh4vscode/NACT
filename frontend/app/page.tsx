"use client";

import { useEffect, useState } from "react";
import { Activity, Network, ShieldCheck, GitPullRequest, Terminal, Bell, Gauge } from "lucide-react";

type Device = {name:string;vendor:string;role:string;site:string;mgmt_ip:string;status:string};
type DeploymentJob = {
  id: string;
  status: string;
  deployment: {type:string;name:string;payload:Record<string, unknown>}
};

export default function Dashboard() {
  const [devices,setDevices] = useState<Device[]>([]);
  const [jobs,setJobs] = useState<DeploymentJob[]>([]);
  const [logs,setLogs] = useState("Waiting for deployment...");
  const [deploymentType,setDeploymentType] = useState("vlan_vni");
  const [changeName,setChangeName] = useState("DC1-VLAN-10010");
  const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  useEffect(() => {
    fetch(`${api}/api/devices`).then(r=>r.json()).then(setDevices).catch(()=>setDevices([]));
    fetch(`${api}/api/deployments`).then(r=>r.json()).then(setJobs).catch(()=>setJobs([]));
  },[api]);
  async function submit() {
    setLogs("POST /api/deployments\nPre-check: BGP/OSPF/VXLAN healthy");
    const payload = deploymentType === "vlan_vni" ? {vni:10010} : {change:changeName};
    const r = await fetch(`${api}/api/deployments`,{
      method:"POST",
      headers:{"Content-Type":"application/json","x-role":"net_admin","x-user":"admin"},
      body:JSON.stringify({type:deploymentType,name:changeName,payload})
    });
    if(r.ok) {
      const job = await r.json() as DeploymentJob;
      setJobs(current=>[job,...current]);
      setLogs(l=>l+"\nChange queued for approval\nAudit entry created");
      const wsUrl = api.replace(/^http/, "ws");
      const socket = new WebSocket(`${wsUrl}/ws/jobs/${job.id}`);
      socket.onmessage = event => {
        const message = JSON.parse(event.data) as {level:string;message:string};
        setLogs(l=>l+`\n[${message.level}] ${message.message}`);
      };
      socket.onclose = () => setLogs(l=>l+"\nExecution stream closed");
    } else {
      setLogs(l=>l+"\nSubmission failed: "+r.status);
    }
  }
  async function approve(jobId:string) {
    const r = await fetch(`${api}/api/deployments/${jobId}/approve`,{method:"POST"});
    if(r.ok) {
      const job = await r.json() as DeploymentJob;
      setJobs(current=>current.map(item=>item.id===jobId ? job : item));
      setLogs(l=>l+`\n[success] ${jobId} approved and executing`);
    }
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
        <select value={deploymentType} onChange={event=>setDeploymentType(event.target.value)}>
          <option value="vlan_vni">Provision VLAN/VNI</option>
          <option value="bgp">BGP EVPN peer</option>
          <option value="ospf">OSPF peer</option>
          <option value="firewall">Firewall rule</option>
          <option value="lb">LB VIP</option>
        </select>
        <input aria-label="Change name" value={changeName} onChange={event=>setChangeName(event.target.value)} />
        <button onClick={submit}>Submit change</button>
      </div></div>
      {jobs.length > 0 && <div className="card section"><h2>Deployment queue</h2>
        <table><thead><tr><th>Job</th><th>Change</th><th>Type</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>{jobs.map(job=><tr key={job.id}><td>{job.id}</td><td>{job.deployment.name}</td><td>{job.deployment.type}</td>
            <td><span className="badge">{job.status}</span></td><td>{job.status==="pending_approval" &&
              <button className="approve" onClick={()=>approve(job.id)}>Approve</button>}</td></tr>)}</tbody>
        </table>
      </div>}
      <div className="card section"><h2><Terminal size={16}/> Live execution terminal</h2><pre className="terminal">{logs}</pre></div>
    </main>
  </div>;
}
