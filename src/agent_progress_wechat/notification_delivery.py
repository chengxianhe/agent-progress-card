"""Retry notifications independently of task delivery; preserve context refresh races."""
import hashlib
import time

from .ilink import LinkError


def send_outgoing(store, client):
    with store.lock:
        item = store.outgoing()
        if not item:
            return False
        context, context_at = store.get('context'), store.get('context_at')
    wire_id = 'relay_' + hashlib.sha256(item['id'].encode()).hexdigest()[:32]
    try:
        client.send(item['text'], context, wire_id)
    except LinkError as error:
        if error.stale_context:
            with store.lock:
                # An old in-flight send must not invalidate newly received reply context.
                if (store.get('context'), store.get('context_at')) == (context, context_at):
                    store.put('send_paused_until', time.time() + 300)
                    store.sent(item['id'], False)
        else:
            store.sent(item['id'], False)
        raise
    store.sent(item['id'], True)
    return True
