"""Explicit, bounded product decisions for the attached conversation."""
import json
import time
import uuid


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
    atomic_json(directory / "choice.json", value)
    return value
