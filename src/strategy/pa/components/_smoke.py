"""Quick sanity check for pa.components on BTCUSDT_1h.csv.

Not a full pytest — just runs each detector on real data and prints counts/samples.
Run: python -m src.strategy.pa.components._smoke
"""

import pandas as pd
from pathlib import Path
from src.strategy.pa.components import (
    detect_swings,
    detect_fvgs,
    cluster_equal_highs,
    cluster_equal_lows,
    parse_wick,
)
from src.strategy.pa.components.fvg import mark_mitigated


CSV = Path("data/Binance/BTCUSDT_1h.csv")


def main() -> None:
    df = pd.read_csv(CSV)
    print(f"loaded {len(df)} bars, range {df['open_time_str'].iloc[0]} → {df['open_time_str'].iloc[-1]}")

    # Swing
    for n in (3, 5):
        swings = detect_swings(df, n=n)
        highs = [s for s in swings if s.typ == "high"]
        lows = [s for s in swings if s.typ == "low"]
        print(f"  swings N={n}: {len(swings)} total ({len(highs)} highs, {len(lows)} lows)")

    swings3 = detect_swings(df, n=3)

    # Equal levels
    eq_highs = cluster_equal_highs(swings3, tolerance_pct=0.001, min_members=2)
    eq_lows = cluster_equal_lows(swings3, tolerance_pct=0.001, min_members=2)
    print(f"  equal highs (tol=0.1%): {len(eq_highs)} groups")
    print(f"  equal lows  (tol=0.1%): {len(eq_lows)} groups")
    if eq_highs:
        top = sorted(eq_highs, key=lambda g: g.count, reverse=True)[:3]
        for g in top:
            print(f"    high@{g.price:.0f} ({g.count} members)")

    # FVG
    fvgs = detect_fvgs(df, body_ratio_threshold=0.6, min_height_pct=0.003, max_height_pct=0.03)
    bull_fvgs = [f for f in fvgs if f.typ == "bullish"]
    bear_fvgs = [f for f in fvgs if f.typ == "bearish"]
    print(f"  FVGs: {len(fvgs)} total ({len(bull_fvgs)} bullish, {len(bear_fvgs)} bearish)")
    mark_mitigated(fvgs, df, expire_bars=50)
    mitigated = sum(1 for f in fvgs if f.mitigated and f.mitigated_at >= 0)
    expired = sum(1 for f in fvgs if f.mitigated and f.mitigated_at == -1)
    print(f"    mitigated within 50 bars: {mitigated} ({mitigated / len(fvgs):.1%})")
    print(f"    expired:                 {expired} ({expired / len(fvgs):.1%})")

    # Wick parse sanity
    sample = parse_wick(df.iloc[100])
    print(f"  wick sample bar 100: body_ratio={sample.body_ratio:.2f} upper={sample.upper_wick_ratio:.2f} lower={sample.lower_wick_ratio:.2f} dir={sample.direction}")


if __name__ == "__main__":
    main()
