"""Public Binance client contract stubs; no requests are sent."""
class BinanceClientError(RuntimeError): pass
class BinanceMarketDataClient:
    def __init__(self, *args, **kwargs): self._stub_args=(args,kwargs)
    def close(self):
        """Close the injected HTTP client; no implementation exists in this scaffold."""
        raise NotImplementedError("Stage-2 implementation not started: close")
    def get_server_time(self):
        """Return Binance public server time; fail closed on time errors and active cooldown."""
        raise NotImplementedError("Stage-2 implementation not started: get_server_time")
    def get_historical_klines(self, *args, **kwargs):
        """Fetch final candles only. Raise EmptyEffectiveRangeError, NaiveDatetimeError,
        or NonFinalCandleError for their respective input/range/upstream failure classes.
        Constructor dependencies include sleep, jitter, now_ms, and http_client.
        """
        raise NotImplementedError("Stage-2 implementation not started: get_historical_klines")

def validate_public_url(*args, **kwargs):
    raise NotImplementedError("Stage-2 implementation not started: validate_public_url")
