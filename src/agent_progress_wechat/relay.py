"""Opt-in bridge to one existing desktop thread; cannot spawn an executor."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid

from agent_progress_card.store import default_directory
from .card_binding import register_connection
from .current_session import CurrentSession, SessionUnavailable
from .files import private_directory, read_json, save_json
from .local_socket import RpcError, TransportError
from .ilink import LinkError
from .login import login
from .relay_mirror import check_binding
from .relay_service import run_relay


def main():
    parser = argparse.ArgumentParser(description="把本人微信连接到已有 Codex 会话")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--card-dir", type=Path, default=default_directory())
    parser.add_argument("--socket", type=Path, default=Path.home() / ".codex/app-server-control/app-server-control.sock")
    parser.add_argument("--window", type=Path)
    parser.add_argument("--reconnect", action="store_true", help="停止旧监听并要求本人重新扫码")
    approvals = parser.add_mutually_exclusive_group()
    approvals.add_argument("--remote-approvals", dest="remote_approvals", action="store_true", default=None,
                           help="启用并记住本人微信单次命令审批，仅绑定账号和会话有效")
    approvals.add_argument("--no-remote-approvals", dest="remote_approvals", action="store_false",
                           help="关闭本人微信单次命令审批，仍保留普通聊天")
    args = parser.parse_args()
    uuid.UUID(args.thread_id)
    os.umask(0o077)
    directory = private_directory(args.state_dir.resolve())
    with (directory / "service.lock").open("a") as lock:
        deadline = time.monotonic() + (45 if args.reconnect else 0)
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not args.reconnect or time.monotonic() >= deadline:
                    parser.error("旧微信监听仍在运行；请稍后再试")
                time.sleep(.5)
        check_binding(args.card_dir, args.thread_id)
        if args.reconnect:
            credential_path = directory / "credentials.json"
            if credential_path.exists():
                credential_path.replace(directory / ("credentials-backup-" + uuid.uuid4().hex + ".json"))
            (directory / "reconnect-request").unlink(missing_ok=True)
        # Start owner-only transport independently. Dispatch/subscription still verify the
        # already-bound live thread; this never opens, forks or restores a closed thread.
        (directory / "stop-request").unlink(missing_ok=True)
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())

        def watch():
            while not stop.wait(.5):
                if (directory / "stop-request").exists() or (directory / "reconnect-request").exists():
                    stop.set()

        threading.Thread(target=watch, daemon=True).start()
        register_connection(args.card_dir, directory)
        save_json(directory / "connection.json", {"mode": "current_session", "thread_id": args.thread_id,
                  "status": "loading", "message": "正在准备当前会话的微信连接。"})
        if args.window:
            subprocess.Popen([str(args.window.resolve()), str(directory)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            credential_path = directory / "credentials.json"
            credentials = read_json(credential_path) if credential_path.exists() else login(directory, stop)
            if not stop.is_set():
                run_relay(directory, credentials, args.thread_id, args.socket, args.card_dir, stop, args.remote_approvals)
        except LinkError as error:
            save_json(directory / "connection.json", {"mode": "current_session", "thread_id": args.thread_id,
                      "status": "expired" if error.expired else "error", "message": str(error)})
            raise
        finally:
            stop.set()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TransportError, RpcError, SessionUnavailable, LinkError):
        raise SystemExit("当前会话转发未能启动；请确认微信已绑定、小看板会话一致、Codex 桌面会话已打开。")
