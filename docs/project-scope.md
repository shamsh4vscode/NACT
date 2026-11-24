# NACT Project Scope

## Purpose

NACT is a prototype for exploring network operations workflows: viewing a sample device inventory, querying network-operation status, submitting and approving changes, and inspecting simulated execution events. It also collects example infrastructure-as-code and lab-topology assets.

## Included in this repository

| Area | Current scope |
| --- | --- |
| Operations dashboard | Next.js page showing inventory, a deployment form and queue, approvals, and a live execution log. |
| Control-plane API | FastAPI endpoints for health, inventory, device operations, deployments, approvals, audit events, and job WebSockets. Interactive API docs are available at `/docs`. |
| Change workflow | Jobs, execution events, and audit events are stored in PostgreSQL. Approval queues execution through Redis/Celery and clients can observe persisted events over WebSockets. |
| Identity and authorization | OIDC authorization-code sign-in with PKCE is wired to Keycloak. The API validates Keycloak-signed tokens, maintains a short-lived signed session cookie for the dashboard, and checks realm roles for protected change and audit routes. |
| Vendor simulators | A separate FastAPI service exposes sample APIs for Palo Alto, Fortinet, Cisco ASA/FTD, F5, Citrix, and HAProxy. The F5 simulator includes a failure/rollback example. |
| GitOps examples | `gitops-infra/` contains sample Ansible, Terraform, validation, and CI/CD files. These are example assets and are not currently invoked by the dashboard's simulated deployment flow. |
| Live device access | In `NACT_DEVICE_MODE=live`, the API connects to the lab's FRR routers over SSH using a locally generated key and strict known-host checking. It can retrieve OSPF, BGP, EVPN/VXLAN, route, and version data. Host status is checked by ICMP. |
| Telemetry and alerting | A Prometheus exporter polls FRR over SSH for device availability, OSPF neighbor counts, and established BGP peer counts. Prometheus evaluates alert rules and Alertmanager displays grouped alerts. |
| Network lab | `lab-topology/` defines a 12-node Containerlab topology using FRR and Alpine, with generated FRR configurations and key-only SSH access for the FRR nodes. It is deployed separately from the Compose application. |
| Local supporting services | Docker Compose starts PostgreSQL, Redis, Vault (development mode), Keycloak, Celery, Prometheus, Alertmanager, the API, frontend, exporter, and vendor simulators. |

## Important implementation boundaries

- Live network access currently targets FRR in the included lab; the other vendor APIs remain simulators. Additional real vendor adapters are not yet implemented.
- The default `NACT_DEVICE_MODE=simulated` uses seeded operation responses. Set it to `live` and deploy the lab to use the FRR SSH integration and live inventory reachability checks.
- Change workflow persistence and queueing are real, but the Celery worker currently runs a demonstration pre/post-check sequence; it does not apply configuration changes to devices or invoke the sample Ansible/Terraform pipeline.
- Prometheus collection is live for FRR devices when the lab is deployed. Alertmanager is configured with a local receiver for viewing alerts; no email, chat, or external notification receiver is configured.
- The database schema is created automatically on API startup for local use. A versioned schema migration and backup/restore procedure are not yet provided.
- Keycloak's bundled realm, demo users, development secrets, and dev-mode database are for local testing only. Configure a managed OIDC provider and secret store before any shared deployment. Vault currently runs in dev mode and is not wired into device credential lookup.
- The dashboard is a prototype, not a fully implemented NOC. Some metric values and workflow details are presentation/demo values rather than measured production telemetry.
- The optional FRR lab uses a dedicated Docker management network (`172.20.20.0/24`). Ensure that subnet is available before starting it.
- The local Compose stack uses HTTP and is not hardened for production. Production use still needs TLS, managed secrets, key rotation, migrations, backup/restore, operational recovery, production identity configuration, and broader vendor-specific validation.

## Out of scope

This repository is not a production-ready network automation platform. It currently provides an end-to-end FRR lab integration and local OIDC/persistence/telemetry foundations, but not live multi-vendor write automation or production operations hardening.
