# Deployment and Local Testing

This guide covers the supported local Docker Compose demo and optional FRR lab. It does not describe a production deployment.

## Prerequisites

- Docker Engine with the Compose v2 plugin (`docker compose`)
- Git, if you need to clone the repository
- Python 3.11 or newer only if you want to run the test suite from the host

The optional network lab additionally requires Containerlab, Docker access sufficient to create lab containers and networks, and permission to use the management subnet configured in the topology.

## Start the application

Run these commands from the repository root:

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

If you already have a `.env`, review it rather than overwriting it. The example file contains development-only values; do not use them in a shared or production environment.

Compose starts the frontend, API, vendor API simulator, PostgreSQL, Redis, Vault, and Celery worker. The primary local endpoints are:

| Service | Address |
| --- | --- |
| Dashboard | <http://localhost:3000> |
| API and OpenAPI docs | <http://localhost:8000/docs> |
| API health | <http://localhost:8000/api/health> |
| Vendor simulator health | <http://localhost:8443/api/health> |
| Keycloak sign-in realm | <http://localhost:8080/realms/nact> |
| Prometheus metrics and alerts | <http://localhost:9090> |
| Alertmanager | <http://localhost:9093> |
| FRR exporter metrics | <http://localhost:9108/metrics> |
| Vault dev server | <http://localhost:8200> |

The dashboard's **Sign in** button uses Keycloak. The local realm is preloaded with these demo accounts:

| Username | Password | Role |
| --- | --- | --- |
| `nact-admin` | `admin-dev-password` | `net_admin` |
| `nact-noc` | `noc-dev-password` | `noc_operator` |
| `nact-security` | `security-dev-password` | `sec_engineer` |

These are public development credentials, not secrets. Do not use them outside a local demo.

The API and simulator endpoints can be checked from a terminal:

```bash
curl -fsS http://localhost:8000/api/health
curl -fsS http://localhost:8000/api/devices
curl -fsS http://localhost:8443/api/health
```

The dashboard should show the seeded inventory. After signing in as `nact-admin`, submit a change, approve its pending job, and watch the execution log. Jobs and audit events are persisted in PostgreSQL; execution runs through Celery over Redis. The worker currently demonstrates a simulated pre/post-check workflow and does not apply the requested change to an FRR router.

## Run the end-to-end tests

Keep the Compose stack running. Install the test-only packages in a suitable host Python environment, then run:

```bash
python3 -m pip install pytest httpx "websockets>=14"
python3 -m pytest -q tests/test_e2e.py
```

The tests call the API, Keycloak, and simulator on `localhost`. They exercise OIDC token validation and role checks, health and inventory, sample operations, simulator rollback, and the persisted approval/WebSocket workflow.

To build the frontend independently:

```bash
docker compose build frontend
```

## Optional: deploy the Containerlab topology

Start the Compose stack first; it creates the `nact-management` network shared with Containerlab. The lab contains two spines, four leaves, two border routers, two WAN routers, and two Alpine hosts. From the repository root:

```bash
cd lab-topology
./deploy_lab.sh
```

The script generates the FRR configuration files and a local SSH key under the ignored `.secrets/` directory, builds the lab image, deploys the topology, and records host keys. The SSH private key is not committed to Git. Review `enterprise-12node.clab.yml` and the generated configs before deploying, especially if `172.20.20.0/24` conflicts with an existing network.

To switch API operations and inventory checks from sample data to the live FRR lab, set this in the repository `.env`:

```dotenv
NACT_DEVICE_MODE=live
```

Then recreate the API container so it reads the setting:

```bash
docker compose up -d --force-recreate backend
```

The telemetry exporter polls the lab automatically and Prometheus evaluates the rules in `monitoring/alerts.yml`. Open Prometheus **Status → Targets** to confirm the exporter is being scraped, then check **Alerts** or Alertmanager for active conditions. The default Alertmanager receiver displays alerts locally but does not send external notifications.

To remove the lab after deployment:

```bash
cd lab-topology
containerlab destroy -t enterprise-12node.clab.yml
```

The API's live FRR adapter is read-only. The current change worker remains a demonstration workflow and does not push configuration to the lab.

## Logs and shutdown

View service logs:

```bash
docker compose logs -f backend frontend api-simulators celery-worker
```

Stop the Compose services while retaining the PostgreSQL data volume:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete the Compose data volume as well.

## Troubleshooting

- **Compose reports missing variables or `.env`:** create `.env` from `.env.example`, then retry.
- **A port is already in use:** stop the process using the port or adjust the published ports in `docker-compose.yml`.
- **A container exits or the dashboard cannot reach the API:** inspect `docker compose ps` and the relevant service logs.
- **OIDC sign-in fails:** check Keycloak logs and wait for the `nact` realm to import. If you changed the OIDC client secret, update both Compose configuration and `keycloak/nact-realm.json`.
- **The end-to-end tests cannot connect:** confirm the API, Keycloak, Celery worker, and simulator are running before running pytest.
- **Live device queries fail:** confirm the lab is deployed, the API has `NACT_DEVICE_MODE=live`, the SSH key and `known_hosts` exist in `lab-topology/.secrets/`, and Docker attached the lab to `nact-management`.
- **Containerlab deployment fails:** confirm Containerlab is installed, Docker is available to the invoking user, and the management subnet is available. The API demo, OIDC, and telemetry services can run without deploying the lab.
