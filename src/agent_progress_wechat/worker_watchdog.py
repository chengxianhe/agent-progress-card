"""Observe the bridge's own worker progress; never kill unrelated or existing processes."""
import os
import time

from .files import read_json, save_json

STALL_SECONDS = 120


def publish(directory, thread_id, ages, grace_until=0):
    stalled = [] if time.time() < grace_until else [name for name, age in ages.items() if age > STALL_SECONDS]
    save_json(directory / 'service-heartbeat.json', {'pid': os.getpid(), 'thread_id': thread_id,
              'written_at': time.time(), 'ages': ages, 'stalled': stalled})
    return bool(stalled)


def unresponsive(directory, thread_id, child_pid, launched_at, now=None):
    now = time.time() if now is None else now
    if not isinstance(child_pid, int) or now - launched_at < STALL_SECONDS:
        return False
    try:
        data = read_json(directory / 'service-heartbeat.json')
        if data.get('pid') != child_pid or data.get('thread_id') != thread_id:
            return True  # Another heartbeat cannot prove this owned child is making progress.
        age = now - data['written_at']
        if age > STALL_SECONDS or age < -30:
            return True
        return bool(data.get('stalled'))
    except (OSError, ValueError, KeyError, TypeError):
        return True
