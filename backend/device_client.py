import json
import os
from pathlib import Path

from scrapli import Scrapli
from scrapli.exceptions import ScrapliException


DEVICE_SSH_KEY = os.getenv(
    "NACT_DEVICE_SSH_KEY_PATH",
    "/run/nact/secrets/id_ed25519",
)
DEVICE_KNOWN_HOSTS = os.getenv(
    "NACT_DEVICE_KNOWN_HOSTS_PATH",
    "/run/nact/secrets/known_hosts",
)
DEVICE_COMMANDS = {
    "ospf": "vtysh -c 'show ip ospf neighbor json'",
    "bgp": "vtysh -c 'show bgp l2vpn evpn summary json'",
    "vxlan": "vtysh -c 'show evpn vni json'",
    "diagnostics": "vtysh -c 'show ip route json'",
}


class DeviceConnectionError(RuntimeError):
    pass


def run_frr_command(host: str, command: str) -> str:
    if not Path(DEVICE_SSH_KEY).is_file():
        raise DeviceConnectionError("Lab SSH private key is unavailable")
    if not Path(DEVICE_KNOWN_HOSTS).is_file():
        raise DeviceConnectionError("Lab SSH known-hosts file is unavailable")

    connection = Scrapli(
        host=host,
        port=22,
        auth_username="root",
        auth_private_key=DEVICE_SSH_KEY,
        auth_strict_key=True,
        ssh_known_hosts_file=DEVICE_KNOWN_HOSTS,
        transport="system",
        platform="generic",
        timeout_socket=4,
        timeout_transport=8,
    )
    opened = False
    try:
        connection.open()
        opened = True
        response = connection.send_command(command)
        if response.failed:
            raise DeviceConnectionError(f"Device command failed on {host}")
        return response.result.strip()
    except ScrapliException as error:
        raise DeviceConnectionError(f"Could not connect to FRR device {host}") from error
    finally:
        if opened:
            connection.close()


def run_frr_operation(host: str, operation: str) -> dict:
    command = DEVICE_COMMANDS[operation]
    output = run_frr_command(host, command)
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        data = {"output": output}
    return {"operation": operation, "command": command, "data": data}
