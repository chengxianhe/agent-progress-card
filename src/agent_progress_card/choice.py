"""Explicit, bounded product decisions for the attached conversation."""
import json
import fcntl
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def choice_lock(directory):
    descriptor = os.open(Path(directory) / "choice-send.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def read_choice(directory, thread_id):
    try:
        with (directory / "choice.json").open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return None
        value = json.loads(raw)
        if (value.get("thread_id") != thread_id or not isinstance(value.get("id"), str)
                or len(value["id"]) > 64 or not isinstance(value.get("created_at"), (int, float))
                or not 0 <= time.time() - value["created_at"] <= 86400
                or not isinstance(value.get("question"), str) or len(value["question"]) > 300
                or not isinstance(value.get("options"), list) or not 2 <= len(value["options"]) <= 5
                or any(not isinstance(x, str) or not x or len(x) > 180 for x in value["options"])):
            return None
        return value
    except (OSError, ValueError, TypeError, KeyError):
        return None


def create_choice(directory, question, options):
    from .watcher import atomic_json
    config = json.loads((directory / "activity-source.json").read_text())
    thread_id = config["thread_id"]
    if not isinstance(thread_id, str) or not thread_id or not isinstance(question, str) or not question.strip():
        raise ValueError("缺少已绑定会话或问题")
    if len(question) > 300 or not 2 <= len(options) <= 5 or any(not x or len(x) > 180 for x in options):
        raise ValueError("问题或选项长度不合法")
    value = {"id": uuid.uuid4().hex, "thread_id": thread_id, "created_at": time.time(),
             "question": question, "options": options}
    with choice_lock(directory):
        if read_choice(directory, thread_id):
            raise ValueError("已有待选问题；请先收到答复或清除旧问题")
        atomic_json(directory / "choice.json", value)
    return value


def clear_choice(directory):
    with choice_lock(directory):
        (Path(directory) / "choice.json").unlink(missing_ok=True)


def complete_choice_unlocked(directory, thread_id, identity, index, source):
    """Caller holds choice_lock through the accepted Codex RPC."""
    from .watcher import atomic_json
    directory = Path(directory)
    choice = read_choice(directory, thread_id)
    if not choice or choice["id"] != identity or not 1 <= index <= len(choice["options"]):
        return False
    atomic_json(directory / "choice-result.json", {"choice_id": identity, "thread_id": thread_id,
                "status": "sent", "index": index, "created_at": time.time(),
                "message": "已收到微信选择，送入当前会话" if source == "wechat" else "已收到小看板选择，送入当前会话"})
    (directory / "choice.json").unlink()
    return True


def record_uncertain_choice_unlocked(directory, thread_id, identity, index):
    from .watcher import atomic_json
    atomic_json(Path(directory) / "choice-result.json", {"choice_id": identity, "thread_id": thread_id,
                "status": "uncertain", "index": index, "created_at": time.time(),
                "message": "选择可能已送入当前会话；请在桌面核对，暂不重复发送"})


def read_choice_result(directory, thread_id):
    try:
        with (Path(directory) / "choice-result.json").open("rb") as stream:
            raw = stream.read(1025)
        if len(raw) > 1024:
            return None
        result = json.loads(raw)
        if (result.get("thread_id") != thread_id or result.get("status") not in ("sent", "uncertain", "retry")
                or not isinstance(result.get("created_at"), (int, float))
                or not 0 <= time.time() - result["created_at"] <= 86400):
            return None
        return result
    except (OSError, ValueError, TypeError, KeyError):
        return None


def recent_choice_result(directory, thread_id, index):
    result = read_choice_result(directory, thread_id)
    return result if result and result["status"] == "sent" and result.get("index") == index and \
        time.time() - result["created_at"] <= 300 else None
