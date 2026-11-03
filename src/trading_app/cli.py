"""Command-line entrypoint: public market-data download and stored-data verification.

Public data only: no credentials, no private endpoints, no orders.

Exit codes (documented contract, CLI-02):
  0   success (download stored / verification clean)
  1   expected operational failure (network, validation, conflict, cooldown, not-final data)
  2   usage or configuration error (bad arguments, invalid settings)
  3   verification completed and found problems in the stored data
  4   --strict-end: the requested end is later than the final-data boundary (nothing was stored)
  70  unexpected internal error
Expected failures print ONE fixed-vocabulary line to stderr and never a traceback; messages are
never echoed from exceptions, so they cannot leak URLs, headers, response bodies or values.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from sqlalchemy.exc import OperationalError

from trading_app.config import Settings
from trading_app.data.binance_client import BinanceClientError, BinanceMarketDataClient
from trading_app.data.finality import StrictEndError
from trading_app.data.repository import CandleRepository, create_engine_from_url
from trading_app.data.service import MarketDataService, safe_error_text
from trading_app.data.verification import verify_database

EXIT_OK, EXIT_FAILURE, EXIT_USAGE, EXIT_VERIFY, EXIT_STRICT_END, EXIT_INTERNAL = 0, 1, 2, 3, 4, 70


def parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("not an ISO-8601 datetime") from None
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("datetime must include a timezone, e.g. 2026-01-05T00:00:00+00:00")
    return parsed.astimezone(timezone.utc)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:        # fixed text only; argparse's own message may echo the input
        self.print_usage(sys.stderr)
        sys.stderr.write("error: invalid command-line arguments\n")
        raise SystemExit(EXIT_USAGE)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Download and verify Binance Spot historical candles (public data only).",
                     epilog="Exit codes: 0 ok, 1 operational failure, 2 usage/config error, 3 verification found problems, "
                            "4 strict-end violated, 70 internal error.")
    parser.add_argument("--symbol")
    parser.add_argument("--timeframe")
    parser.add_argument("--start", type=parse_datetime)
    parser.add_argument("--end", type=parse_datetime)
    parser.add_argument("--strict-end", action="store_true",
                        help="fail (exit 4, store nothing) instead of clamping an end later than the final-data boundary")
    parser.add_argument("--verify", action="store_true",
                        help="verify the stored data (read-only) instead of downloading")
    return parser


def _err(text: str) -> None:
    sys.stderr.write(text + "\n")


def main(argv: Sequence[str] | None = None, *, settings: Settings | None = None, http_client: Any | None = None,
         sleep: Callable[[float], None] | None = None, jitter: Callable[[], float] | None = None,
         now_ms: Callable[[], int] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.verify:
        if any(v is not None for v in (args.symbol, args.timeframe, args.start, args.end)) or args.strict_end:
            _err("error: --verify takes no download options")
            return EXIT_USAGE
    else:
        missing = [n for n in ("symbol", "timeframe", "start", "end") if getattr(args, n) is None]
        if missing:
            _err("error: --symbol, --timeframe, --start and --end are required")
            return EXIT_USAGE

    try:
        cfg = settings if settings is not None else Settings()
    except Exception:                      # pydantic ValidationError etc.; never echo values
        _err("error: invalid configuration")
        return EXIT_USAGE

    client = None
    try:
        engine = create_engine_from_url(cfg.database_url)
        if args.verify:
            report = verify_database(engine)
            for (symbol, timeframe), n in report.counts.items():
                print(f"{symbol} {timeframe}: {n} candles")
            if report.ok:
                print("Verification: OK")
                return EXIT_OK
            for code, n in report.issue_counts().items():
                print(f"{code}: {n}")
            print("Verification: PROBLEMS FOUND (nothing was changed)")
            return EXIT_VERIFY
        repository = CandleRepository(engine, max_candles_per_fetch=cfg.max_candles_per_fetch)
        repository.create_tables()
        client = BinanceMarketDataClient(
            base_url=cfg.binance_base_url, http_client=http_client, timeout_seconds=cfg.binance_timeout_seconds,
            sleep=sleep, jitter=jitter, now_ms=now_ms, cooldown_path=cfg.cooldown_path,
            finality_lag_ms=cfg.finality_lag_ms)
        service = MarketDataService(settings=cfg, client=client, repository=repository, now_ms=now_ms)
        inserted = service.download_and_store(symbol=args.symbol, timeframe=args.timeframe, start=args.start,
                                              end=args.end, strict_end=args.strict_end)
        total = repository.count(symbol=args.symbol.upper(), timeframe=args.timeframe)
        print(f"New candles inserted: {inserted}")
        print(f"Total stored candles: {total}")
        return EXIT_OK
    except OperationalError:
        _err("error: database is unavailable or has no candle table")
        return EXIT_FAILURE
    except StrictEndError as exc:
        _err("error: " + safe_error_text(exc))
        return EXIT_STRICT_END
    except (BinanceClientError, ValueError, RuntimeError) as exc:
        _err("error: " + safe_error_text(exc))
        return EXIT_FAILURE
    except Exception:
        _err("error: unexpected internal error")
        return EXIT_INTERNAL
    finally:
        if client is not None:
            client.close()
