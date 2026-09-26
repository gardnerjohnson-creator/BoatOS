"""
Local development mode for BoatOS.

Configured via environment variables (see .env.example):

  BOATOS_DEV_MODE      "1"/"true"/"yes" enables dev mode (default: off)
  BOATOS_SIGNALK_URL   SignalK base URL (default: http://localhost:3000,
                       empty string disables SignalK polling entirely)
  BOATOS_MQTT_HOST     MQTT broker host (default: localhost)
  BOATOS_MQTT_PORT     MQTT broker port (default: 1883)

In dev mode, Pi/systemd-only system commands (systemctl, sudo, nmcli,
pinctrl, shutdown, ...) are not executed. The wrappers below log the
command and return a successful, empty result so API endpoints answer
"ok" instead of failing on a laptop.

With BOATOS_DEV_MODE unset, all wrappers are transparent pass-throughs to
subprocess, so production behaviour on the Pi is unchanged.
"""
import asyncio
import os
import subprocess
from typing import Optional

_TRUE = {"1", "true", "yes", "on"}


def is_dev_mode() -> bool:
    return os.getenv("BOATOS_DEV_MODE", "").strip().lower() in _TRUE


def signalk_url() -> Optional[str]:
    """SignalK base URL, or None when disabled (BOATOS_SIGNALK_URL='')."""
    if "BOATOS_SIGNALK_URL" not in os.environ:
        return "http://localhost:3000"
    url = os.environ["BOATOS_SIGNALK_URL"].strip()
    return url.rstrip("/") or None


def signalk_ws_url() -> Optional[str]:
    url = signalk_url()
    if not url:
        return None
    return url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)


def mqtt_host() -> str:
    return os.getenv("BOATOS_MQTT_HOST", "").strip() or "localhost"


def mqtt_port() -> int:
    try:
        return int(os.getenv("BOATOS_MQTT_PORT", "") or 1883)
    except ValueError:
        return 1883


def _fake_result(cmd) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(list(cmd), 0, "", "")


def _log_skip(cmd) -> None:
    print(f"🧪 [dev-mode] skipped system command: {' '.join(str(c) for c in cmd)}")


def run_system(cmd, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run for Pi-only commands; no-op success in dev mode."""
    if is_dev_mode():
        _log_skip(cmd)
        return _fake_result(cmd)
    return subprocess.run(cmd, **kwargs)


def popen_system(cmd, **kwargs) -> Optional[subprocess.Popen]:
    """subprocess.Popen for Pi-only commands; returns None in dev mode."""
    if is_dev_mode():
        _log_skip(cmd)
        return None
    return subprocess.Popen(cmd, **kwargs)


def check_output_system(cmd, **kwargs) -> bytes:
    """subprocess.check_output for Pi-only commands; b'' in dev mode."""
    if is_dev_mode():
        _log_skip(cmd)
        return b""
    return subprocess.check_output(cmd, **kwargs)


class _FakeAsyncStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def read(self, n=-1):
        return b""

    async def readline(self):
        return b""


class _FakeAsyncProcess:
    returncode = 0
    stdout = _FakeAsyncStream()
    stderr = _FakeAsyncStream()

    async def communicate(self, input=None):
        return b"", b""

    async def wait(self):
        return 0


async def run_system_async(*cmd, **kwargs):
    """asyncio.create_subprocess_exec for Pi-only commands; fake success in dev mode."""
    if is_dev_mode():
        _log_skip(cmd)
        return _FakeAsyncProcess()
    return await asyncio.create_subprocess_exec(*cmd, **kwargs)


def describe() -> dict:
    return {
        "dev_mode": is_dev_mode(),
        "signalk_url": signalk_url(),
        "mqtt_host": mqtt_host(),
        "mqtt_port": mqtt_port(),
    }
