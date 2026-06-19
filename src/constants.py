"""
Centralized constants for the trading system.

Avoids magic numbers scattered across modules.
"""

# --------------------------------------------------------------------------
# Trading defaults
# --------------------------------------------------------------------------
DEFAULT_SYMBOL = "BTC/USDT"
DEFAULT_INITIAL_CAPITAL = 10000.0
DEFAULT_COMMISSION = 0.001
DEFAULT_SLIPPAGE = {"BTC/USDT": 0.0005}

# Grid strategy
GRID_COUNT = 10
GRID_BOUNDARY_OFFSET = 0.1  # 10% from extremes

# Risk limits
MAX_POSITION_PER_TRADE = 1.0
MAX_TOTAL_POSITION = 1.0
WARMUP_BARS = 30  # Pre-heat bars for grid boundaries + indicators

# --------------------------------------------------------------------------
# Data defaults
# --------------------------------------------------------------------------
DEFAULT_TIMEFRAME = "4h"
DEFAULT_DATA_SYMBOLS = ["BTC/USDT", "ETH/USDT"]

# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/!ticker@arr"
DEFAULT_POLL_SECONDS = 60
DEFAULT_API_PORT = 8000

# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------
__all__ = [
    "DEFAULT_SYMBOL", "DEFAULT_INITIAL_CAPITAL", "DEFAULT_COMMISSION",
    "DEFAULT_SLIPPAGE", "GRID_COUNT", "GRID_BOUNDARY_OFFSET",
    "MAX_POSITION_PER_TRADE", "MAX_TOTAL_POSITION", "WARMUP_BARS",
    "DEFAULT_TIMEFRAME", "DEFAULT_DATA_SYMBOLS",
    "BINANCE_WS_URL", "DEFAULT_POLL_SECONDS", "DEFAULT_API_PORT",
]
