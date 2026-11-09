"""Send one explicit card selection to the already bound conversation."""
import argparse
import fcntl
import json
from pathlib import Path

from agent_progress_card.choice import read_choice
from agent_progress_card.watcher import atomic_json

from .local_socket import RpcError, TransportError


def process_card_choice(card_directory, session):
    source = Path(card_directory) / "choice-selection.json"
    try:
        with source.open("rb") as stream:
            raw = stream.read(1025)
        if len(raw) > 1024:
            return
        selection = json.loads(raw)
        choice = read_choice(card_directory, session.thread_id)
        if not choice or selection.get("choice_id") != choice["id"] or selection.get("thread_id") != session.thread_id:
            return
        index = selection.get("index")
        if not isinstance(index, int) or isinstance(index, bool) or not 1 <= index <= len(choice["options"]):
            return
    except (OSError, ValueError, TypeError, KeyError):
        return
    result_path = Path(card_directory) / "choice-result.json"
    try:
        old = json.loads(result_path.read_text())
        if old.get("choice_id") == choice["id"] and old.get("status") != "retry":
            return
    except (OSError, ValueError, TypeError):
        pass
    connection = session.open()
    try:
        text = "我选择第 " + str(index) + " 项：" + choice["options"][index - 1]
        method, params = session.prepare(connection, text, choice["id"], source="card")
        try:
            reply = connection.call(method, params)
            turn = reply.get("turnId") if method == "turn/steer" else reply.get("turn", {}).get("id")
            if not isinstance(turn, str) or not turn:
                raise TransportError("缺少回执")
            status, message = "sent", "已送入当前会话"
        except (RpcError, TransportError, OSError):
            status, message = "uncertain", "投递结果不确定；请在原会话核对，暂不自动重发"
        atomic_json(result_path, {"choice_id": choice["id"], "status": status, "message": message})
    finally:
        connection.close()


def main():
    from agent_progress_card.store import default_directory
    from .current_session import CurrentSession, SessionUnavailable

    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, default=default_directory())
    args = parser.parse_args()
    directory = args.state_dir
    with (directory / "choice-send.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        binding = {}
        try:
            binding = json.loads((directory / "activity-source.json").read_text())
            session = CurrentSession(Path.home() / ".codex/app-server-control/app-server-control.sock", binding["thread_id"])
            process_card_choice(directory, session)
        except (OSError, ValueError, KeyError, SessionUnavailable, RpcError, TransportError):
            try:
                choice = read_choice(directory, binding["thread_id"])
                if choice:
                    atomic_json(directory / "choice-result.json", {"choice_id": choice["id"],
                                "status": "retry", "message": "当前会话暂不可用；稍后可重试"})
            except (OSError, ValueError, KeyError):
                pass


if __name__ == "__main__":
    main()
