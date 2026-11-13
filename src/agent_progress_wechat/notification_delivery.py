"""Retry notifications independently of task delivery; preserve context refresh races."""
import hashlib

from .ilink import LinkError
from .delivery_policy import pause


def send_outgoing(store, client):
    with store.lock:
        item = store.outgoing()
        if not item:
            return False
        context, context_at = store.get('context'), store.get('context_at')
    identity = item['id'] + (':' + str(item['revision']) if item['revision'] else '')
    wire_id = 'relay_' + hashlib.sha256(identity.encode()).hexdigest()[:32]
    try:
        client.send(item['text'], context, wire_id)
    except LinkError as error:
        with store.lock:
            # An old in-flight failure must not pause a newly received reply context.
            if (store.get('context'), store.get('context_at')) == (context, context_at):
                with store.db:
                    store.sent(item['id'], False, item['revision'])
                    pause(store.db)
        raise
    store.sent(item['id'], True, item['revision'])
    return True
