"""Free, read-only primary data. An alternate exchange is a labelled proxy."""

import httpx
from datetime import datetime, timezone
from math import log
from statistics import pstdev
from .models import utcnow


def fetch(topic, symbol="BTC-USD"):
    with httpx.Client(timeout=12, follow_redirects=False) as client:
        if topic == "crypto":
            if symbol not in ("BTC-USD", "ETH-USD", "SOL-USD"):
                raise ValueError("Unsupported public product")
            url = f"https://api.exchange.coinbase.com/products/{symbol}/candles"
            r = client.get(url, params={"granularity": 300})
            r.raise_for_status()
            rows = sorted(r.json(), key=lambda x: x[0])
            if not rows:
                raise ValueError("No candles")
            last = datetime.fromtimestamp(rows[-1][0], timezone.utc)
            if (utcnow() - last).total_seconds() > 900:
                raise ValueError("Stale primary candles")
            prices = [float(x[4]) for x in rows]
            changes = [
                log(y / x) for x, y in zip(prices, prices[1:]) if x > 0 and y > 0
            ]
            return {
                "url": url + "?granularity=300",
                "source": "Coinbase Exchange public candles",
                "symbol": symbol,
                "fetched_at": utcnow().isoformat(),
                "observed_at": last.isoformat(),
                "latest_close": str(rows[-1][4]),
                "five_minute_log_volatility": pstdev(changes)
                if len(changes) > 1
                else None,
                "candles": [
                    {
                        "at": datetime.fromtimestamp(x[0], timezone.utc).isoformat(),
                        "close": str(x[4]),
                        "volume": str(x[5]),
                    }
                    for x in rows[-48:]
                ],
                "limitation": "Reference exchange, not Binance or a guaranteed Polymarket resolution source. Candles may include an unfinished interval.",
            }
        if topic == "inflation":
            url = "https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0"
            r = client.get(url)
            r.raise_for_status()
            data = r.json()
            if data.get("status") != "REQUEST_SUCCEEDED":
                raise ValueError("BLS data unavailable")
            return {
                "url": url,
                "source": "BLS unregistered public API v1; US CPI not seasonally adjusted",
                "fetched_at": utcnow().isoformat(),
                "series": data["Results"]["series"][0]["data"][:15],
                "limitation": "Published observations, not a forecast. Check series, seasonal adjustment and release date against market rules.",
            }
        if topic == "weather":
            url = "https://www.nhc.noaa.gov/CurrentStorms.json"
            r = client.get(url)
            r.raise_for_status()
            return {
                "url": url,
                "source": "NOAA National Hurricane Center",
                "fetched_at": utcnow().isoformat(),
                "data": r.json(),
                "limitation": "Current active storms, not the full seasonal hurricane count or a forecast.",
            }
        if topic == "social":
            if symbol.lower() not in ("elonmusk", "realdonaldtrump"):
                raise ValueError("Unsupported tracked user")
            platform = "X" if symbol.lower() == "elonmusk" else "TRUTH_SOCIAL"
            url = f"https://xtracker.polymarket.com/api/users/{symbol}/trackings"
            r = client.get(url, params={"platform": platform, "activeOnly": "true"})
            r.raise_for_status()
            payload = r.json()
            if not payload.get("success"):
                raise ValueError("XTracker reported unsuccessful response")
            details = []
            periods = payload.get("data", [])

            def order(row):
                try:
                    start = datetime.fromisoformat(
                        row["startDate"].replace("Z", "+00:00")
                    )
                    end = datetime.fromisoformat(row["endDate"].replace("Z", "+00:00"))
                    return (not start <= utcnow() < end, (end - start).total_seconds())
                except (KeyError, ValueError):
                    return (True, float("inf"))

            for row in sorted(periods, key=order)[:4]:
                if not row.get("id"):
                    continue
                source = f"https://xtracker.polymarket.com/api/trackings/{row['id']}?includeStats=true"
                detail = client.get(source)
                detail.raise_for_status()
                data = detail.json()
                if not data.get("success"):
                    raise ValueError("XTracker statistics unavailable")
                details.append({"url": source, "tracking": data["data"]})
            return {
                "url": url,
                "source": "Polymarket XTracker public tracking",
                "fetched_at": utcnow().isoformat(),
                "platform": platform,
                "data": details,
                "limitation": "Verify the exact tracking window and market counting rules; no estimate from headlines. At most four active periods are returned.",
            }
        raise ValueError("Unsupported public data topic")
