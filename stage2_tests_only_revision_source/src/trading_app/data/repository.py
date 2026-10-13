"""Persistence contract stubs."""
class CandleConflictError(RuntimeError): pass
def create_engine_from_url(*args, **kwargs): raise NotImplementedError("Stage-2 implementation not started: create_engine_from_url")
class CandleRepository:
    def __init__(self, *args, **kwargs): self._stub_args=(args,kwargs)
    def create_tables(self): raise NotImplementedError("Stage-2 implementation not started: create_tables")
    def insert_candles(self, *args, **kwargs): raise NotImplementedError("Stage-2 implementation not started: insert_candles")
    def get_candles(self, *args, **kwargs): raise NotImplementedError("Stage-2 implementation not started: get_candles")
    def scan_legacy_data(self, *args, **kwargs):
        """Return legacy-data findings without modifying records; not implemented in Stage 2."""
        raise NotImplementedError("Stage-2 implementation not started: scan_legacy_data")
