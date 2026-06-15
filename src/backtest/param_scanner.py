"""
参数敏感性测试

测试策略参数变化对结果的影响
"""

from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from itertools import product

from src.backtest.engine import BacktestEngine
from src.utils.logger import logger


class ParameterScanner:
    """
    参数扫描器

    用于参数敏感性分析和参数优化
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
    ):
        """
        初始化参数扫描器

        参数：
            initial_capital: 初始资金
            commission: 手续费率
            slippage: 滑点率
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    def grid_search(
        self,
        data: pd.DataFrame,
        strategy_class,
        param_grid: Dict[str, List],
    ) -> pd.DataFrame:
        """
        网格搜索参数空间

        参数：
            data: OHLCV 数据
            strategy_class: 策略类
            param_grid: 参数网格，例如 {'short_window': [3, 5, 7], 'long_window': [10, 15, 20]}

        返回：
            结果 DataFrame
        """
        logger.info(f"Starting grid search with {len(param_grid)} parameters")

        # 生成所有参数组合
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(product(*param_values))

        logger.info(f"Total combinations: {len(combinations)}")

        results = []

        for i, params in enumerate(combinations, 1):
            # 创建参数字典
            param_dict = dict(zip(param_names, params))

            logger.debug(f"Testing combination {i}/{len(combinations)}: {param_dict}")

            # 创建策略实例
            strategy = strategy_class(**param_dict)

            # 运行回测
            engine = BacktestEngine(
                initial_capital=self.initial_capital,
                commission=self.commission,
                slippage=self.slippage,
            )

            backtest_results = engine.run(data=data, strategy=strategy)

            if backtest_results["success"]:
                # 提取关键指标
                metrics = backtest_results.get("metrics", {})

                result = {
                    **param_dict,
                    "total_return": backtest_results["total_return"],
                    "annual_return": metrics.get("annual_return", 0),
                    "max_drawdown": metrics.get("max_drawdown", 0),
                    "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                    "win_rate": metrics.get("win_rate", 0),
                    "total_trades": backtest_results["total_trades"],
                }

                results.append(result)

        # 转换为 DataFrame
        df_results = pd.DataFrame(results)

        logger.info(f"Grid search completed: {len(results)} results")

        return df_results

    def sensitivity_analysis(
        self,
        data: pd.DataFrame,
        strategy_class,
        base_params: Dict,
        test_param: str,
        variations: List[float] = [-0.2, -0.1, 0, 0.1, 0.2],
    ) -> pd.DataFrame:
        """
        参数敏感性分析

        测试单个参数变化对结果的影响

        参数：
            data: OHLCV 数据
            strategy_class: 策略类
            base_params: 基准参数
            test_param: 要测试的参数名
            variations: 变化比例列表（如 [-0.2, 0, 0.2] 表示 -20%, 0%, +20%）

        返回：
            结果 DataFrame
        """
        logger.info(f"Starting sensitivity analysis for parameter: {test_param}")

        if test_param not in base_params:
            raise ValueError(f"Parameter {test_param} not in base_params")

        base_value = base_params[test_param]
        results = []

        for variation in variations:
            # 计算新参数值
            new_value = base_value * (1 + variation)

            # 对于整数参数，取整
            if isinstance(base_value, int):
                new_value = int(round(new_value))

            # 创建新参数字典
            params = base_params.copy()
            params[test_param] = new_value

            logger.debug(f"Testing {test_param}={new_value} (variation={variation:.1%})")

            # 创建策略实例
            strategy = strategy_class(**params)

            # 运行回测
            engine = BacktestEngine(
                initial_capital=self.initial_capital,
                commission=self.commission,
                slippage=self.slippage,
            )

            backtest_results = engine.run(data=data, strategy=strategy)

            if backtest_results["success"]:
                metrics = backtest_results.get("metrics", {})

                result = {
                    "parameter": test_param,
                    "variation": variation,
                    "value": new_value,
                    "total_return": backtest_results["total_return"],
                    "annual_return": metrics.get("annual_return", 0),
                    "max_drawdown": metrics.get("max_drawdown", 0),
                    "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                    "total_trades": backtest_results["total_trades"],
                }

                results.append(result)

        df_results = pd.DataFrame(results)

        logger.info(f"Sensitivity analysis completed: {len(results)} results")

        return df_results

    def analyze_stability(
        self,
        sensitivity_results: pd.DataFrame,
        tolerance: float = 0.5,
    ) -> Dict:
        """
        分析参数稳定性

        参数：
            sensitivity_results: 敏感性分析结果
            tolerance: 容忍度（收益变化 < tolerance 为稳定）

        返回：
            稳定性分析结果
        """
        if sensitivity_results.empty:
            return {"stable": False, "message": "No results"}

        # 获取基准结果（variation = 0）
        base_result = sensitivity_results[sensitivity_results["variation"] == 0]

        if base_result.empty:
            return {"stable": False, "message": "No base result"}

        base_return = base_result.iloc[0]["total_return"]

        # 计算所有变化的收益偏差
        max_deviation = 0
        for _, row in sensitivity_results.iterrows():
            if row["variation"] != 0:
                deviation = abs(row["total_return"] - base_return)
                # 相对偏差（相对于参数变化）
                relative_deviation = deviation / abs(row["variation"]) if row["variation"] != 0 else 0
                max_deviation = max(max_deviation, relative_deviation)

        # 判断稳定性
        is_stable = max_deviation < tolerance

        return {
            "stable": is_stable,
            "max_deviation": max_deviation,
            "tolerance": tolerance,
            "base_return": base_return,
            "parameter": sensitivity_results.iloc[0]["parameter"],
        }


# 导出
__all__ = ["ParameterScanner"]
