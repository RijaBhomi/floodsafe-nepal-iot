"""Small MQTT client for publishing FloodSafe Nepal telemetry to ThingsBoard.

This module only knows about networking. It does not generate readings and it
does not touch the database. Credentials come from environment variables (or an
optional local .env file); they are never hardcoded or printed.

Paho MQTT is the only third-party library used by this module.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
from pathlib import Path
from typing import Any, Mapping

import paho.mqtt as paho  # MQTTException lives here in Paho 2.x
import paho.mqtt.client as mqtt

try:
    from .simulator import REQUIRED_FIELDS
except ImportError:  # pragma: no cover - only used when run as a plain script
    from simulator import REQUIRED_FIELDS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

TELEMETRY_TOPIC = "v1/devices/me/telemetry"
PLACEHOLDER_PREFIX = "replace-with-"  # .env.example values are not real tokens
DEFAULT_PORT = 8883
KEEPALIVE_SECONDS = 60
CONNECT_TIMEOUT_NOTE = "check THINGSBOARD_HOST and network access"
PUBLISH_TIMEOUT_SECONDS = 10
CLIENT_ID = "floodsafe-nepal-python"

# Each virtual node maps to one ThingsBoard device token. Keeping the mapping
# here means the CLI and sync manager never have to guess environment names.
NODE_TOKEN_VARS = {
    "FSN-01": "FSN_01_TOKEN",
    "FSN-02": "FSN_02_TOKEN",
    "FSN-03": "FSN_03_TOKEN",
}

# Group the exceptions so every network call handles the same set. Note:
# Paho 2.x puts MQTTException in paho.mqtt, NOT in paho.mqtt.client.
NETWORK_ERRORS = (OSError, ValueError, paho.MQTTException)
CLIENT_ERRORS = NETWORK_ERRORS + (RuntimeError,)


class MQTTConfigError(Exception):
    """Raised when required environment variables are missing."""


class MQTTError(Exception):
    """Raised when connecting to the broker fails."""


def _log(message: str) -> None:
    """Print a status message without ever showing the access token."""
    print(f"[MQTT] {message}", file=sys.stderr)


def load_local_env(path: Path | None = None) -> None:
    """Copy KEY=VALUE lines from .env into os.environ if not already set.

    This is a tiny standard-library replacement for python-dotenv. Real
    environment variables always win, which is useful on a shared machine.
    """
    if path is None:
        path = ENV_FILE
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_settings() -> tuple[str, str]:
    """Return (host, token) from the environment. Never log the token."""
    load_local_env()
    host = os.environ.get("THINGSBOARD_HOST", "").strip()
    token = os.environ.get("THINGSBOARD_TOKEN", "").strip()
    if not host:
        raise MQTTConfigError("THINGSBOARD_HOST is not set. " + CONNECT_TIMEOUT_NOTE)
    if not token:
        raise MQTTConfigError(
            "THINGSBOARD_TOKEN is not set. Add the device access token privately."
        )
    return host, token


def _is_usable_token(value: str) -> bool:
    """Treat empty values and .env.example placeholders as 'not set'."""
    value = value.strip()
    return bool(value) and not value.startswith(PLACEHOLDER_PREFIX)


def has_node_tokens() -> bool:
    """Return True when at least one per-node device token is configured."""
    load_local_env()
    return any(
        _is_usable_token(os.environ.get(env_name, ""))
        for env_name in NODE_TOKEN_VARS.values()
    )


def read_node_settings() -> tuple[str, dict[str, str]]:
    """Return (host, {node_id: token}) for the configured node devices.

    A missing token is not an error here: that node's rows simply stay pending.
    If no node token is set at all, raise a clear configuration error.
    """
    load_local_env()
    host = os.environ.get("THINGSBOARD_HOST", "").strip()
    if not host:
        raise MQTTConfigError("THINGSBOARD_HOST is not set. " + CONNECT_TIMEOUT_NOTE)

    tokens: dict[str, str] = {}
    for node_id, env_name in NODE_TOKEN_VARS.items():
        token = os.environ.get(env_name, "").strip()
        if _is_usable_token(token):
            tokens[node_id] = token

    if not tokens:
        names = ", ".join(NODE_TOKEN_VARS.values())
        raise MQTTConfigError(
            f"No per-node tokens are set. Set at least one of: {names}. "
            "Never put real tokens in source code."
        )
    return host, tokens


def build_client(token: str, client_id: str = CLIENT_ID) -> mqtt.Client:
    """Create a TLS-enabled Paho client with the device token as username.

    MQTT client IDs must be unique per connection. The per-node sync passes a
    different ID for each device; the default keeps the Stage 3 path unchanged.
    """
    # Paho 2.x wants a callback API version; Paho 1.x does not have it.
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
    else:  # pragma: no cover - only for older Paho installations
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

    # ThingsBoard uses the device access token as the MQTT username and an
    # empty password. Nothing is stored in source code.
    client.username_pw_set(token, None)

    # create_default_context() verifies the server certificate AND hostname.
    # We never call tls_insecure_set(), so TLS verification stays enabled.
    client.tls_set_context(ssl.create_default_context())
    return client


def connect(client: mqtt.Client, host: str, port: int = DEFAULT_PORT) -> None:
    """Connect with TLS and start Paho's network loop. Raise on failure."""
    try:
        result = client.connect(host, port, KEEPALIVE_SECONDS)
    except NETWORK_ERRORS as exc:
        raise MQTTError(
            f"Could not connect to ThingsBoard at {host}:{port}: {exc}"
        ) from exc
    if result != mqtt.MQTT_ERR_SUCCESS:
        raise MQTTError(f"Broker {host}:{port} refused the connection (code {result}).")

    client.loop_start()
    _log(f"Connected to broker {host}:{port} over TLS (QoS 1).")


def disconnect(client: mqtt.Client) -> None:
    """Stop the network loop and disconnect. Safe to call after a failure."""
    try:
        client.loop_stop()
        client.disconnect()
        _log("MQTT client cleanup finished.")
    except CLIENT_ERRORS as exc:
        _log(f"Disconnect warning: {exc}")


def telemetry_payload(reading: Mapping[str, Any]) -> dict[str, Any]:
    """Return ONLY the 11 telemetry fields, never database-only fields."""
    return {field: reading[field] for field in REQUIRED_FIELDS}


def _reading_label(reading: Mapping[str, Any]) -> str:
    """A short, safe description for log lines."""
    try:
        return f"ts={reading['ts']} node_id={reading['node_id']}"
    except (KeyError, TypeError):  # a malformed reading should not break logging
        return "unknown reading"


def publish_reading(
    client: mqtt.Client,
    reading: Mapping[str, Any],
    timeout: int = PUBLISH_TIMEOUT_SECONDS,
) -> bool:
    """Publish one reading and return True only after QoS 1 confirmation.

    ``wait_for_publish()`` waits for the broker's PUBACK. Calling publish()
    alone is NOT enough to know the message arrived.
    """
    label = _reading_label(reading)
    payload = json.dumps(telemetry_payload(reading))

    try:
        info = client.publish(TELEMETRY_TOPIC, payload, qos=1)
    except CLIENT_ERRORS as exc:
        _log(f"Publish failed for {label}: {exc}")
        return False

    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        _log(f"Publish rejected locally for {label} (code {info.rc}).")
        return False

    try:
        info.wait_for_publish(timeout=timeout)
    except CLIENT_ERRORS as exc:
        _log(f"No delivery confirmation for {label}: {exc}")
        return False

    delivered = bool(info.is_published())
    if delivered:
        _log(f"Delivered {label} to {TELEMETRY_TOPIC} (QoS 1 confirmed).")
    else:
        _log(f"Delivery not confirmed for {label}; keep it pending.")
    return delivered
