"""
kalshi_trades.py
----------------
Fetch and display trades for a Kalshi market ticker.

Usage:
    python kalshi_trades.py --ticker KXBTC-25DEC-T100000 --api-key YOUR_KEY
    python kalshi_trades.py --ticker KXBTC-25DEC-T100000 --api-key YOUR_KEY --limit 200
    python kalshi_trades.py --ticker KXBTC-25DEC-T100000 --api-key YOUR_KEY --csv trades.csv

Requirements:
    pip install requests pandas tabulate
"""

"""
Notes

This program fetches data from the Kalshi API endpoint GET market/trades.
When fetching the endpoint, it returns info on the following fields for each
trade in a market.
trade_id: A unique identifier for the specific trade transaction. 
ticker: The unique market symbol associated with the trade (e.g., KXHIGHNY-24JAN01-T60). 
count_fp: String representation of the number of contracts bought or sold in this trade
yes_price_dollars: The price per contract for the "Yes" outcome at the time of the trade, expressed as a dollar string (e.g., "0.5600"). 
no_price_dollars: The price per contract for the "No" outcome, which is mathematically reciprocal to the Yes price ($1.00 - \text{Yes Price}$). 
taker_side: Indicates which side the taker (the party executing the order) took, either "yes" or "no". 
created_time: The timestamp of the trade in ISO 8601 format (e.g., "2023-11-07T05:31:56Z").
"""


import argparse
import sys
import time
from datetime import datetime

import requests
import pandas as pd
from tabulate import tabulate

import time
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, utils
from urllib.parse import urlparse
from cryptography.hazmat.backends import default_backend


BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
RSA_SIG_PATH = "path_to_file"
MY_API_KEY = "replace_with_your_key"

# ── Authentication ──────────────────────────────────────────────────────────────────────
def load_private_key(key_path):
    with open(key_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

def create_signature(private_key, timestamp, method, path):
    """Create the request signature."""
    # Strip query parameters before signing
    path_without_query = path.split('?')[0]
    message = f"{timestamp}{method}{path_without_query}".encode('utf-8')
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def get(private_key, api_key_id, path, limit):
    """Make an authenticated GET request to the Kalshi API."""
    timestamp = str(int(datetime.now().timestamp() * 1000))
    # Signing requires the full URL path from root (e.g. /trade-api/v2/portfolio/balance)
    fullpath = BASE_URL + path
    print(fullpath)
    sign_path = urlparse(fullpath).path
    signature = create_signature(private_key, timestamp, "GET", sign_path)

    headers = {
        'KALSHI-ACCESS-KEY': api_key_id,
        'KALSHI-ACCESS-SIGNATURE': signature,
        'KALSHI-ACCESS-TIMESTAMP': timestamp
    }
    params = {"limit": min(limit, 10000)}
    return requests.get(fullpath, headers=headers, params=params, timeout=10)


# ── Fetch ──────────────────────────────────────────────────────────────────────

def fetch_trades(ticker: str, api_key: str, limit: int = 1000) -> list[dict]:
    """Fetch up to `limit` trades for the given ticker."""

    private_key = load_private_key(RSA_SIG_PATH)
    url = f"{BASE_URL}/markets/trades"
    path = f"/markets/trades"
    
    try:
        resp = get(private_key, MY_API_KEY, path, limit)
        # resp = requests.get(url, headers=headers, params=params, timeout=10)
        # print(f"Status: {resp.status_code}")
        # print(f"URL called: {resp.url}")
        # print(f"Response body: {resp.text[:500]}")
        # print(resp)
        if resp.status_code == 401:
            print("Error: Invalid API key or unauthorized.")
            sys.exit(1)
        if resp.status_code == 404:
            print(f"Error: Ticker '{ticker}' not found.")
            sys.exit(1)
        if resp.status_code == 429:
            print("Rate limited. Waiting 5 seconds and retrying...")
            time.sleep(5)
            resp = get(private_key, MY_API_KEY, path, limit)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to Kalshi API. Check your internet connection.")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Error: Request timed out.")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error: {e}")
        sys.exit(1)

    data = resp.json()
    trades = data.get("trades", [])
    if not trades:
        print(f"No trades returned for ticker '{ticker}'.")
        sys.exit(0)
    return trades


# ── Transform ──────────────────────────────────────────────────────────────────

def build_dataframe(trades: list[dict]) -> pd.DataFrame:
    """
    Parse raw trade dicts into a clean DataFrame.
    yes_price comes back as an integer out of 100 (e.g. 63 = 63¢).
    """
    rows = []
    for t in trades:
        raw_price = t.get("yes_price_dollars")
        yes_price_cents = raw_price if raw_price is not None else None

        rows.append({
            "time":        t.get("created_time", ""),
            "trade_id":    t.get("trade_id", ""),
            "side":        t.get("taker_side", ""),
            "ticker": t.get("ticker", ""),
            "yes_price_c": yes_price_cents,         # in cents (0-100)
            "count":       t.get("count_fp", 0),
        })

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], errors="coerce", utc=True)
    df["yes_price_c"] = pd.to_numeric(df["yes_price_c"], errors="coerce")
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)
    df = df.sort_values("time", ascending=False).reset_index(drop=True)
    return df


# ── Summary stats ──────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame, ticker: str) -> None:
    prices = df["yes_price_c"].dropna()
    total_vol = df["count"].sum()
    yes_trades = (df["side"] == "yes").sum()
    no_trades  = (df["side"] == "no").sum()

    latest = prices.iloc[0] if not prices.empty else float("nan")
    oldest = prices.iloc[-1] if not prices.empty else float("nan")
    change = latest - oldest

    vwap = (
        (df["yes_price_c"] * df["count"]).sum() / total_vol
        if total_vol > 0 else float("nan")
    )

    print("\n" + "═" * 58)
    print(f"  KALSHI TRADE SUMMARY  —  {ticker}")
    print("═" * 58)

    stats = [
        ("Trades fetched",    f"{len(df):,}"),
        ("Total contracts",   f"{total_vol:,}"),
        ("Latest yes price",  f"{latest:.1f}¢"),
        ("Earliest yes price",f"{oldest:.1f}¢"),
        ("Price change",      f"{change:+.1f}¢"),
        ("VWAP (yes)",        f"{vwap:.1f}¢"),
        ("High",              f"{prices.max():.1f}¢"),
        ("Low",               f"{prices.min():.1f}¢"),
        ("Yes-side trades",   f"{yes_trades:,}"),
        ("No-side trades",    f"{no_trades:,}"),
    ]

    for label, value in stats:
        print(f"  {label:<22} {value}")
    print("═" * 58)


# ── ASCII price chart ──────────────────────────────────────────────────────────

def print_price_chart(df: pd.DataFrame, width: int = 54, height: int = 12) -> None:
    """Render a simple ASCII line chart of yes_price over time."""
    prices = df["yes_price_c"].dropna().tolist()[::-1]  # chronological order
    if len(prices) < 2:
        return

    lo, hi = min(prices), max(prices)
    if hi == lo:
        hi = lo + 1  # avoid div/zero

    print("\n  Yes price over time (¢)")
    print("  " + "─" * width)

    def row_for(row_idx):
        # row 0 = top (hi), row height-1 = bottom (lo)
        threshold = hi - (hi - lo) * row_idx / (height - 1)
        return threshold

    # Sample prices down to chart width
    step = max(1, len(prices) // width)
    sampled = [prices[i] for i in range(0, len(prices), step)][:width]
    sampled += [sampled[-1]] * (width - len(sampled))  # pad if short

    for row_idx in range(height):
        threshold = row_for(row_idx)
        next_threshold = row_for(row_idx + 1) if row_idx < height - 1 else -1
        label_val = hi - (hi - lo) * row_idx / (height - 1)

        line = ""
        for p in sampled:
            if next_threshold < p <= threshold + (hi - lo) / height:
                line += "●"
            elif p > threshold:
                line += "│"
            else:
                line += " "

        print(f"  {label_val:5.1f}¢ │{line}")

    print("  " + " " * 8 + "└" + "─" * width)
    t_start = df["time"].min()
    t_end   = df["time"].max()
    if pd.notna(t_start) and pd.notna(t_end):
        left  = t_start.strftime("%b %d %H:%M")
        right = t_end.strftime("%b %d %H:%M")
        padding = width - len(left) - len(right)
        print(f"  {' ' * 9}{left}{' ' * max(0, padding)}{right}")


# ── Trade table ────────────────────────────────────────────────────────────────

def print_trade_table(df: pd.DataFrame, show_n: int = 30) -> None:
    display = df.head(show_n).copy()

    display["time_fmt"] = display["time"].apply(
        lambda t: t.strftime("%b %d  %H:%M:%S") if pd.notna(t) else "—"
    )
    display["price_fmt"] = display["yes_price_c"].apply(
        lambda p: f"{p:.1f}¢" if pd.notna(p) else "—"
    )
    display["side_fmt"] = display["side"].apply(
        lambda s: f"[YES]" if s == "yes" else ("[NO] " if s == "no" else s)
    )
    display["id_short"] = display["trade_id"].apply(
        lambda x: x[:14] + "…" if len(str(x)) > 14 else x
    )

    table_data = display[["time_fmt", "side_fmt", "price_fmt", "count", "id_short"]].values.tolist()
    headers = ["Time (UTC)", "Side", "Yes price", "Contracts", "Trade ID"]

    print(f"\n  Recent trades (showing {min(show_n, len(df))} of {len(df)})")
    print("  " + "─" * 64)
    print(tabulate(table_data, headers=headers, tablefmt="plain",
                   colalign=("left", "center", "right", "right", "left")))
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch and display Kalshi market trades.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--ticker",  required=True, help="Market ticker, e.g. KXBTC-25DEC-T100000")
    parser.add_argument("--api-key", required=True, help="Your Kalshi API bearer token")
    parser.add_argument("--limit",   type=int, default=100, help="Number of trades to fetch (default: 100, max: 1000)")
    parser.add_argument("--show",    type=int, default=30,  help="Rows to show in trade table (default: 30)")
    parser.add_argument("--csv",     default=None,          help="Optional path to save all trades as CSV")
    parser.add_argument("--no-chart",action="store_true",   help="Skip the ASCII price chart")
    return parser.parse_args()


def main():
    args = parse_args()
    ticker = args.ticker.upper()

    print(f"\nFetching {args.limit} trades for {ticker} …")
    trades = fetch_trades(ticker, args.api_key, args.limit)
    df = build_dataframe(trades)

    print_summary(df, ticker)

    if not args.no_chart:
        print_price_chart(df)

    print_trade_table(df, show_n=args.show)

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"  Saved {len(df)} trades to {args.csv}\n")


if __name__ == "__main__":
    main()