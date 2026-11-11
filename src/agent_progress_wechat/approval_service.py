"""Single reader/writer for the subscribed approval socket, separate from chat delivery."""
import select
import time
import uuid

from .approval_transport import ApprovalConnection
from .relay_mirror import check_binding


def run_approvals(store, session, directory, stop, health, state):
    while not stop.is_set():
        client, connection = None, uuid.uuid4().hex
        try:
            check_binding(directory, session.thread_id)
            client = ApprovalConnection(session.socket_path)
            client.subscribe(session)
            for event in client.events:
                state.event(event, connection)
            client.events.clear()
            health('approvals', '')
            while not stop.is_set():
                check_binding(directory, session.thread_id)
                # Drain incoming resolutions before sending queued replies. Concurrent desktop
                # resolution can still race; only report request closure, never who won it.
                readable, _, _ = select.select([client.socket], [], [], .2)
                if readable:
                    state.event(client._receive(time.monotonic() + 12), connection)
                    continue
                state.expire()
                reply = state.claim(connection)
                if reply:
                    client.respond(*reply)
        except Exception:
            health('approvals', '微信审批连接暂不可用；请在电脑端确认，旧编号不会自动重发')
        finally:
            state.invalidate(connection)
            if client:
                client.close()
        stop.wait(5)
