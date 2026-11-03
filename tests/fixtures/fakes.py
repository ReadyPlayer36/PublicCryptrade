"""Network fakes for tests; these never open sockets."""
class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, json_error=None):
        self.status_code=status_code; self.payload=payload; self.headers=headers or {}; self.json_error=json_error
    def json(self):
        if self.json_error is not None: raise self.json_error
        return self.payload

class FakeHttpClient:
    def __init__(self, responses=(), errors=()):
        self.responses=list(responses); self.errors=list(errors); self.calls=[]
    def get(self, url, *, params=None):
        self.calls.append((url,params or {}))
        if self.errors: raise self.errors.pop(0)
        if not self.responses: raise AssertionError("unexpected HTTP request")
        return self.responses.pop(0)

class SequenceFakeHttpClient:
    """Deterministic ordered events: each get consumes exactly one response or exception."""
    def __init__(self, events):
        self.events = list(events)
        self.calls = []
    def get(self, url, *, params=None):
        self.calls.append((url, params or {}))
        if not self.events:
            raise AssertionError("unexpected HTTP request")
        event = self.events.pop(0)
        if isinstance(event, BaseException):
            raise event
        return event
