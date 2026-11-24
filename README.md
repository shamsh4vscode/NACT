# NACT

NACT is a network and security operations prototype with a web dashboard, a FastAPI control-plane API, OIDC sign-in, persistent change jobs, Prometheus telemetry, simulated vendor APIs, sample GitOps assets, and an optional FRR Containerlab topology.

## Documentation

- [Current project scope](docs/project-scope.md)
- [Deployment and local testing guide](docs/deployment.md)

## Quick start

With Docker Compose installed and Docker running:

```bash
cp .env.example .env
docker compose up --build -d
```

Open the dashboard at <http://localhost:3000>, the API documentation at <http://localhost:8000/docs>, Prometheus at <http://localhost:9090>, or check API health at <http://localhost:8000/api/health>. See the [deployment guide](docs/deployment.md) for sign-in, tests, live lab setup, and current limitations.
