"""Public Binance client contract stubs; no requests are sent."""
class BinanceClientError(RuntimeError): pass
class BinanceMarketDataClient:
    def __init__(self, *args, **kwargs): self._stub_args=(args,kwargs)
    def close(self): raise NotImplementedError("Stage-2 implementation not started: close")
    def get_server_time(self): raise NotImplementedError("Stage-2 implementation not started: get_server_time")
    def get_historical_klines(self, *args, **kwargs): raise NotImplementedError("Stage-2 implementation not started: get_historical_klines")

def validate_public_url(*args, **kwargs):
    raise NotImplementedError("Stage-2 implementation not started: validate_public_url")
