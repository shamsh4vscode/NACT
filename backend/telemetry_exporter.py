import json
import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread

from scrapli.exceptions import ScrapliException

from device_client import DEVICE_COMMANDS, run_frr_command


LOGGER = logging.getLogger("nact.telemetry")
METRIC_HELP = {
    "nact_device_up": "Whether a configured FRR device is reachable over SSH.",
    "nact_device_cli_command_success": "Whether an FRR operational command returned successfully.",
    "nact_ospf_neighbors": "OSPF neighbors reported by an FRR device.",
    "nact_bgp_sessions_established": "Established BGP peers reported by an FRR device.",
}
METRICS: dict[tuple[str, tuple[str, ...]], float] = {}
METRICS_LOCK = Lock()

DEVICES = {
    "spine-01": "172.20.20.11",
    "spine-02": "172.20.20.12",
    "leaf-01": "172.20.20.13",
    "leaf-02": "172.20.20.14",
    "leaf-03": "172.20.20.15",
    "leaf-04": "172.20.20.16",
    "border-01": "172.20.20.17",
    "border-02": "172.20.20.18",
    "wan-rtr-01": "172.20.20.19",
    "wan-rtr-02": "172.20.20.20",
}


def set_metric(name: str, value: float, *labels: str) -> None:
    with METRICS_LOCK:
        METRICS[(name, labels)] = value


def render_metrics() -> bytes:
    lines = []
    with METRICS_LOCK:
        metrics = list(METRICS.items())
    for name, description in METRIC_HELP.items():
        lines.append(f"# HELP {name} {description}")
        lines.append(f"# TYPE {name} gauge")
        for (metric_name, labels), value in metrics:
            if metric_name != name:
                continue
            rendered_labels = ",".join(
                f'{key}="{label}"'
                for key, label in zip(
                    ("device", "operation"),
                    labels,
                    strict=True,
                )
            )
            suffix = f"{{{rendered_labels}}}" if rendered_labels else ""
            lines.append(f"{name}{suffix} {value}")
    return ("\n".join(lines) + "\n").encode()


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/metrics":
            self.send_error(404)
            return
        body = render_metrics()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        LOGGER.debug(format, *args)


def count_items(value: object, predicate) -> int:
    if isinstance(value, dict):
        total = int(predicate(value))
        return total + sum(count_items(child, predicate) for child in value.values())
    if isinstance(value, list):
        return sum(count_items(child, predicate) for child in value)
    return 0


def collect_device(device: str, host: str) -> None:
    try:
        ospf_output = run_frr_command(host, DEVICE_COMMANDS["ospf"])
        bgp_output = run_frr_command(host, DEVICE_COMMANDS["bgp"])
    except (OSError, ScrapliException, RuntimeError) as error:
        set_metric("nact_device_up", 0, device)
        LOGGER.warning("Telemetry collection failed for %s: %s", device, error)
        return

    set_metric("nact_device_up", 1, device)
    for operation, output in (("ospf", ospf_output), ("bgp", bgp_output)):
        set_metric("nact_device_cli_command_success", 1, device, operation)
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            set_metric("nact_device_cli_command_success", 0, device, operation)
            LOGGER.warning("%s returned non-JSON %s output", device, operation)
            continue
        if operation == "ospf":
            neighbors = count_items(
                data,
                lambda item: "neighborId" in item or "neighbor" in item,
            )
            set_metric("nact_ospf_neighbors", neighbors, device)
        else:
            established = count_items(
                data,
                lambda item: str(item.get("state", "")).lower() == "established",
            )
            set_metric("nact_bgp_sessions_established", established, device)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    server = ThreadingHTTPServer(("0.0.0.0", 9108), MetricsHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    while True:
        for device, host in DEVICES.items():
            collect_device(device, host)
        time.sleep(15)


if __name__ == "__main__":
    main()
