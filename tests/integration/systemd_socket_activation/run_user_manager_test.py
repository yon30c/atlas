"""Opt-in integration probe for a private systemd --user SOCK_SEQPACKET socket.

Run manually; this is intentionally not part of the default unit-test suite.
It creates uniquely named transient user unit files and a private runtime dir,
then removes only those resources.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[3]
HELPER = Path(__file__).with_name("activated_service.py")
PYTHON = Path(sys.executable)


def run_systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["systemctl", "--user", *args]
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )
    if check and result.returncode:
        rendered = " ".join(command)
        diagnostics = ""
        if len(args) >= 2 and args[0] == "start" and args[1].endswith(".socket"):
            unit = args[1]
            status = subprocess.run(
                ["systemctl", "--user", "status", unit, "--no-pager", "--full"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
            journal = subprocess.run(
                ["journalctl", "--user", "-b", "-u", unit, "--no-pager", "-n", "60"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
            service_unit = unit.removesuffix(".socket") + ".service"
            service_status = subprocess.run(
                ["systemctl", "--user", "status", service_unit, "--no-pager", "--full"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
            service_properties = subprocess.run(
                ["systemctl", "--user", "show", service_unit,
                 "--property=LoadState,FragmentPath,UnitFileState", "--no-pager"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
            service_cat = subprocess.run(
                ["systemctl", "--user", "cat", service_unit],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=False,
            )
            diagnostics = (
                f"\nunit status:\n{status.stdout or status.stderr or '(empty)'}"
                f"\nuser journal:\n{journal.stdout or journal.stderr or '(empty)'}"
                f"\nassociated service properties:\n{service_properties.stdout or service_properties.stderr or '(empty)'}"
                f"\nassociated service status:\n{service_status.stdout or service_status.stderr or '(empty)'}"
                f"\nassociated service definition:\n{service_cat.stdout or service_cat.stderr or '(empty)'}"
            )
        raise RuntimeError(
            f"{rendered} failed with exit code {result.returncode}.\n"
            f"stdout:\n{result.stdout or '(empty)'}\n"
            f"stderr:\n{result.stderr or '(empty)'}{diagnostics}"
        )
    return result


def quote_unit(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def wait_for(predicate, description: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for {description}")


def active_state(unit: str) -> str:
    result = run_systemctl("show", "--property=ActiveState", "--value", unit, check=False)
    return result.stdout.strip()


def send_ping(path: str) -> dict:
    request_id = str(uuid.uuid4())
    packet = json.dumps(
        {
            "version": 1,
            "request_id": request_id,
            "operation": "authority.ping",
            "payload": {},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    client.settimeout(5.0)
    try:
        client.connect(path)
        client.sendall(packet)
        response = json.loads(client.recv(4096).decode("utf-8"))
    finally:
        client.close()
    if response.get("request_id") != request_id or response.get("status") != "ok":
        raise AssertionError(f"unexpected activation response: {response!r}")
    return response


def main() -> int:
    if sys.platform != "linux":
        raise SystemExit("This probe requires Linux.")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime or not Path(runtime).is_dir():
        raise SystemExit("XDG_RUNTIME_DIR is unavailable; no files were created.")
    manager = run_systemctl("show-environment", check=False)
    if manager.returncode:
        raise SystemExit(
            "The systemd user manager is unavailable. Start no system services; "
            "run this probe from a session with a working systemctl --user bus."
        )

    token = f"{os.getpid()}-{secrets.token_hex(4)}"
    socket_unit = f"atlas-admin-ipc-probe-{token}.socket"
    service_unit = f"atlas-admin-ipc-probe-{token}.service"
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    missing_unit_dirs = []
    cursor = unit_dir
    while not cursor.exists():
        missing_unit_dirs.append(cursor)
        cursor = cursor.parent
    unit_dir.mkdir(parents=True, exist_ok=True)
    socket_unit_path = unit_dir / socket_unit
    service_unit_path = unit_dir / service_unit
    if socket_unit_path.exists() or service_unit_path.exists():
        raise SystemExit("Unique unit-name collision; refusing to overwrite existing files.")

    private_dir = Path(tempfile.mkdtemp(prefix="atlas-admin-ipc-probe-", dir=runtime))
    os.chmod(private_dir, 0o700)
    socket_path = private_dir / "admin.sock"
    uid = os.getuid()
    created_units = False
    daemon_reloaded = False

    socket_contents = f"""[Unit]
Description=Temporary Atlas authority IPC activation probe {token}

[Socket]
ListenSequentialPacket={socket_path}
Service={service_unit}
Accept=no
SocketMode=0600
DirectoryMode=0700
RemoveOnStop=no
"""

    service_contents = f"""[Unit]
Description=Temporary Atlas authority IPC activated service probe {token}

[Service]
Type=oneshot
ExecStart={quote_unit(str(PYTHON))} {quote_unit(str(HELPER))}
Environment=PYTHONPATH={ROOT / "src"}
Environment=ATLAS_EXPECTED_UID={uid}
Environment=ATLAS_EXPECTED_SOCKET={socket_path}
"""

    try:
        created_units = True
        socket_unit_path.write_text(socket_contents, encoding="utf-8")
        service_unit_path.write_text(service_contents, encoding="utf-8")
        os.chmod(socket_unit_path, 0o600)
        os.chmod(service_unit_path, 0o600)

        run_systemctl("daemon-reload")
        daemon_reloaded = True

        # The runtime directory was freshly created with mode 0700. Never
        # place a pre-existing object at the socket path: systemd 257.13 on
        # the development host altered a regular file at that path. Collision
        # behavior is documented as unsafe/unresolved and is not retested here.
        run_systemctl("start", socket_unit)
        wait_for(lambda: socket_path.exists(), "systemd-created socket path")
        info = socket_path.lstat()
        if not stat.S_ISSOCK(info.st_mode):
            raise AssertionError("systemd did not create a filesystem socket")
        if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != uid:
            raise AssertionError(
                f"unexpected socket owner/mode: uid={info.st_uid}, "
                f"mode={stat.S_IMODE(info.st_mode):04o}"
            )
        if stat.S_IMODE(private_dir.stat().st_mode) != 0o700:
            raise AssertionError("private runtime directory mode changed")

        for activation_number in (1, 2):
            send_ping(str(socket_path))
            wait_for(
                lambda: active_state(service_unit) in {"inactive", "failed"},
                f"one-shot service activation {activation_number} to finish",
            )
            if active_state(service_unit) == "failed":
                raise AssertionError(f"activated service failed: {service_unit}")

        # The socket unit owns the pathname; the one-shot service must not unlink it.
        if not socket_path.exists() or not stat.S_ISSOCK(socket_path.lstat().st_mode):
            raise AssertionError("activated service removed the systemd-owned socket")
        run_systemctl("stop", service_unit, check=False)
        run_systemctl("stop", socket_unit, check=False)
        if not socket_path.exists():
            raise AssertionError("RemoveOnStop=no did not preserve the socket path")
        socket_path.unlink()
        print("PASS: systemd user socket activation, descriptor validation,")
        print("      two activations and private ownership/mode.")
        print("PASS: RemoveOnStop=no leaves pathname cleanup to the test harness.")
        return 0
    finally:
        run_systemctl("stop", service_unit, check=False)
        run_systemctl("stop", socket_unit, check=False)
        if created_units:
            socket_unit_path.unlink(missing_ok=True)
            service_unit_path.unlink(missing_ok=True)
            if daemon_reloaded:
                run_systemctl("daemon-reload", check=False)
        # This directory was created uniquely by this invocation. Never recurse
        # through a path outside it; unlink only the expected socket path.
        if socket_path.exists() or socket_path.is_symlink():
            info = socket_path.lstat()
            if stat.S_ISSOCK(info.st_mode) or stat.S_ISREG(info.st_mode):
                socket_path.unlink()
        try:
            private_dir.rmdir()
        except OSError:
            print(f"Manual cleanup may be needed for temporary directory: {private_dir}", file=sys.stderr)
        for created_dir in missing_unit_dirs:
            try:
                created_dir.rmdir()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
