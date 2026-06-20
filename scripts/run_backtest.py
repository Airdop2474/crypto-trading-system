#!/usr/bin/env python3
"""
统一回测入口脚本

用法：
    python scripts/run_backtest.py --strategy grid
    python scripts/run_backtest.py --strategy rsi
    python scripts/run_backtest.py --strategy ma --short-window 5 --long-window 20
    python scripts/run_backtest.py --strategy buyhold

使用 registry 查找策略类，消除硬编码 import。
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.data.downloader import DataDownloader
from src.backtest.engine import BacktestEngine
from src.strategy.registry import get_strategy, list_strategies, STRATEGY_REGISTRY
from src.utils.logger import setup_logger, logger


# 策略默认参数表
STRATEGY_DEFAULTS = {
    "grid": {
        "lower_price": None,
        "upper_price": None,
        "grid_count": 10,
        "position_per_grid": None,
        "enable_filters": True,
        "max_consecutive_losses": 3,
        "max_daily_loss": 0.02,
    },
    "rsi": {
        "rsi_period": 14,
        "oversold": 30.0,
        "overbought": 70.0,
        "ema_period": 50,
    },
    "ma": {
        "short_window": 5,
        "long_window": 20,
    },
    "buyhold": {},
    "donchian": {
        "period": 20,
        "max_consecutive_losses": 3,
        "max_daily_loss": 0.02,
    },
    "structure": {
        "lookback": 10,
        "max_consecutive_losses": 3,
        "max_daily_loss": 0.02,
    },
    "supertrend": {
        "period": 10,
        "multiplier": 3.0,
        "max_consecutive_losses": 3,
        "max_daily_loss": 0.02,
    },
    "reversal": {
        "lookback": 50,
        "pin_threshold": 2.0,
        "stop_atr_mult": 2.0,
        "atr_period": 14,
        "max_consecutive_losses": 3,
        "max_daily_loss": 0.02,
    },
}


def _build_strategy(args: argparse.Namespace):
    """根据 CLI 参数构建策略实例。

    返回：
        Strategy 实例
    """
    strategy_name = args.strategy
    cls = get_strategy(strategy_name)
    defaults = STRATEGY_DEFAULTS.get(strategy_name, {}).copy()

    # 覆盖 CLI 显式传入的参数
    for key in list(defaults.keys()):
        cli_val = getattr(args, _cli_key(key), None)
        if cli_val is not None:
            defaults[key] = cli_val

    # grid 策略特殊处理：自动从数据推断上下界
    if strategy_name == "grid" and defaults["lower_price"] is None:
        # 将在加载数据后设置
        pass

    try:
        strategy = cls(**defaults)
    except TypeError as e:
        # 尝试去掉不支持的关键字
        import inspect
        sig = inspect.signature(cls.__init__)
        valid = {k: v for k, v in defaults.items() if k in sig.parameters}
        strategy = cls(**valid)

    return strategy


def _cli_key(param_name: str) -> str:
    """将参数名转换为 CLI flags 名（下划线→连字符）。"""
    return param_name.replace("_", "-")


def _add_strategy_args(parser: argparse.ArgumentParser, strategy_name: str) -> None:
    """为指定策略添加 CLI 参数。"""
    defaults = STRATEGY_DEFAULTS.get(strategy_name, {})
    for param, default_val in defaults.items():
        cli_flag = f"--{_cli_key(param)}"
        if isinstance(default_val, bool):
            parser.add_argument(cli_flag, action="store_true", default=None,
                                help=f"Enable {param}")
            parser.add_argument(f"--no-{_cli_key(param)}", dest=cli_flag.lstrip("-"),
                                action="store_false", default=None,
                                help=f"Disable {param}")
        elif isinstance(default_val, float):
            parser.add_argument(cli_flag, type=float, default=None,
                                help=f"{param} (default: {default_val})")
        elif isinstance(default_val, int):
            parser.add_argument(cli_flag, type=int, default=None,
                                help=f"{param} (default: {default_val})")
        elif default_val is None:
            parser.add_argument(cli_flag, type=float, default=None,
                                help=f"{param}")


def main() -> int:
    """主入口。"""
    parser = argparse.ArgumentParser(
        description="Unified backtest runner using strategy registry",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available strategies: {', '.join(list_strategies())}",
    )

    parser.add_argument(
        "--strategy", "-s",
        type=str,
        default="buyhold",
        choices=list_strategies(),
        help="Strategy to run (default: buyhold)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC/USDT",
        help="Trading pair (default: BTC/USDT)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="4h",
        help="Timeframe (default: 4h)",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Initial capital (default: 10000.0)",
    )
    parser.add_argument(
        "--commission",
        type=float,
        default=0.001,
        help="Commission rate (default: 0.001)",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=0.0005,
        help="Slippage rate (default: 0.0005)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    # 先解析 --strategy 以加载对应参数
    known, _ = parser.parse_known_args()
    _add_strategy_args(parser, known.strategy)

    args = parser.parse_args()
    setup_logger(log_level=args.log_level)

    print("=" * 60)
    print(f"Backtest: {args.strategy} on {args.symbol}")
    print("=" * 60)

    # 加载数据
    print("\n[1] Loading data...")
    downloader = DataDownloader()
    df = downloader.load_data(symbol=args.symbol, timeframe=args.timeframe)

    if df.empty:
        print(f"    No data found for {args.symbol} {args.timeframe}. Generating mock...")
        from scripts.generate_mock_data import main as gen_mock
        gen_mock()
        df = downloader.load_data(symbol=args.symbol, timeframe=args.timeframe)

    if df.empty:
        print("    ERROR: Failed to load or generate data")
        return 1

    print(f"    Loaded {len(df)} bars, {df['timestamp'].min()} ~ {df['timestamp'].max()}")

    # grid 策略自动计算默认上下界
    if args.strategy == "grid":
        mid = float(df["close"].mean())
        # 覆盖未显式传入的上下界
        if getattr(args, "lower_price", None) is None:
            setattr(args, "lower_price", round(mid * 0.85, 2))
        if getattr(args, "upper_price", None) is None:
            setattr(args, "upper_price", round(mid * 1.15, 2))

    # 构建策略
    print(f"\n[2] Building strategy: {args.strategy}...")
    strategy = _build_strategy(args)
    print(f"    Strategy: {type(strategy).__name__}")
    print(f"    Params:   {strategy.parameters}")

    # 回测
    print(f"\n[3] Running backtest...")
    engine = BacktestEngine(
        initial_capital=args.capital,
        commission=args.commission,
        slippage=args.slippage,
    )
    results = engine.run(data=df, strategy=strategy)

    if not results.get("success"):
        print(f"    ERROR: {results.get('message', 'Unknown error')}")
        return 1

    # 显示结果
    print(f"\n[4] Results:")
    print("-" * 60)
    print(f"    Initial Capital: ${results['initial_capital']:,.2f}")
    print(f"    Final Equity:    ${results['final_equity']:,.2f}")
    print(f"    Total Return:    {results['total_return']:>10.2%}")
    print(f"    Total Trades:    {results['total_trades']:>10}")

    metrics = results.get("metrics", {})
    if metrics:
        print(f"\n    Performance Metrics:")
        print(f"    {'-' * 50}")
        for key in ["annual_return", "sharpe_ratio", "sortino_ratio",
                     "max_drawdown", "win_rate", "profit_factor",
                     "avg_trade", "kelly_criterion"]:
            val = metrics.get(key)
            if val is not None:
                if key in ("annual_return", "max_drawdown", "win_rate"):
                    print(f"    {key:<22} {val:>10.2%}")
                elif key in ("sharpe_ratio", "sortino_ratio", "profit_factor",
                             "avg_trade", "kelly_criterion"):
                    print(f"    {key:<22} {val:>10.4f}")

    print("\n" + "=" * 60)
    print("Backtest complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
