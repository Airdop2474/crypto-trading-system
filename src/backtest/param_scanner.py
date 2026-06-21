"""
参数敏感性测试

测试策略参数变化对结果的影响
"""

from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from itertools import product
from concurrent.futures import ProcessPoolExecutor, as_completed

from src.backtest.engine import BacktestEngine
from src.utils.logger import logger


def _run_single_backtest(args: Tuple) -> Optional[Dict]:
    """模块级辅助函数，供 ProcessPoolExecutor pickling。

    args = (strategy_class, param_dict, data, initial_capital, commission, slippage)
    """
    strategy_class, param_dict, data, initial_capital, commission, slippage = args
    try:
        strategy = strategy_class(**param_dict)
        engine = BacktestEngine(
            initial_capital=initial_capital,
            commission=commission,
            slippage=slippage,
        )
        result = engine.run(data=data, strategy=strategy)
        if result["success"]:
            metrics = result.get("metrics", {})
            return {
                **param_dict,
                "total_return": result["total_return"],
                "annual_return": metrics.get("annual_return", 0),
                "max_drawdown": metrics.get("max_drawdown", 0),
                "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                "sortino_ratio": metrics.get("sortino_ratio", 0),
                "win_rate": metrics.get("win_rate", 0),
                "total_trades": result["total_trades"],
            }
    except Exception as e:
        logger.warning(
            f"Param scan failed for params={param_dict}: "
            f"{type(e).__name__}: {e}"
        )
    return None


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
        max_workers: Optional[int] = 1,
    ):
        """
        初始化参数扫描器

        参数：
            initial_capital: 初始资金
            commission: 手续费率
            slippage: 滑点率
            max_workers: 并行进程数（默认 1=串行；设为 >1 启用多进程并行）
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.max_workers = max_workers

    def grid_search(
        self,
        data: pd.DataFrame,
        strategy_class,
        param_grid: Dict[str, List],
    ) -> pd.DataFrame:
        """
        网格搜索参数空间（支持并行执行）

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

        # 构建任务参数
        tasks = [
            (strategy_class, dict(zip(param_names, params)),
             data, self.initial_capital, self.commission, self.slippage)
            for params in combinations
        ]

        results = []

        # 并行或串行取决于 max_workers
        use_parallel = self.max_workers != 1 and len(combinations) > 1

        if not use_parallel:
            # 串行模式（默认 / 单组合）
            for i, task_args in enumerate(tasks, 1):
                logger.debug(f"Testing combination {i}/{len(combinations)}")
                result = _run_single_backtest(task_args)
                if result:
                    results.append(result)
        else:
            # 并行模式（max_workers=None 使用 cpu_count）
            workers = self.max_workers
            with ProcessPoolExecutor(max_workers=workers) as executor:
                future_map = {
                    executor.submit(_run_single_backtest, task_args): i
                    for i, task_args in enumerate(tasks)
                }
                done_count = 0
                for future in as_completed(future_map):
                    done_count += 1
                    result = future.result()
                    if result:
                        results.append(result)
                    if done_count % 10 == 0:
                        logger.info(f"Progress: {done_count}/{len(combinations)}")

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

    def walk_forward(
        self,
        data: pd.DataFrame,
        strategy_class,
        param_grid: Dict[str, List],
        n_windows: int = 3,
        in_sample_ratio: float = 0.7,
    ) -> pd.DataFrame:
        """
        Walk-Forward 分析：样本内优化 + 样本外验证，防止过拟合

        将数据切分为 n_windows 个窗口，每个窗口内：
        1. 前 in_sample_ratio 做样本内参数优化（grid_search）
        2. 后 1 - in_sample_ratio 做样本外验证（用最优参数回测）

        参数：
            data: OHLCV 数据
            strategy_class: 策略类
            param_grid: 参数网格
            n_windows: 窗口数量
            in_sample_ratio: 样本内占比（0-1）

        返回：
            样本外结果 DataFrame（每窗口一行）
        """
        if n_windows < 2:
            raise ValueError("n_windows must be >= 2")

        total_len = len(data)
        window_size = total_len // n_windows
        oos_results = []

        logger.info(
            f"Walk-forward: {n_windows} windows, window_size={window_size}, "
            f"in_sample_ratio={in_sample_ratio}"
        )

        for w in range(n_windows):
            start = w * window_size
            end = min(start + window_size, total_len)
            if end - start < 10:
                break

            window_data = data.iloc[start:end]
            split_idx = int(len(window_data) * in_sample_ratio)

            in_sample = window_data.iloc[:split_idx]
            out_sample = window_data.iloc[split_idx:]

            if len(in_sample) < 5 or len(out_sample) < 3:
                continue

            # 样本内优化
            in_results = self.grid_search(in_sample, strategy_class, param_grid)
            if in_results.empty:
                continue

            # 取样本内 Sharpe 最优参数
            best_idx = in_results["sharpe_ratio"].idxmax()
            best_params = {}
            for key in param_grid:
                best_params[key] = in_results.loc[best_idx, key]

            # 样本外验证
            strategy = strategy_class(**best_params)
            engine = BacktestEngine(
                initial_capital=self.initial_capital,
                commission=self.commission,
                slippage=self.slippage,
            )
            oos_bt = engine.run(data=out_sample, strategy=strategy)

            if oos_bt["success"]:
                metrics = oos_bt.get("metrics", {})
                oos_results.append({
                    "window": w,
                    **best_params,
                    "in_sample_return": float(in_results.loc[best_idx, "total_return"]),
                    "out_sample_return": oos_bt["total_return"],
                    "out_sample_sharpe": metrics.get("sharpe_ratio", 0),
                    "out_sample_max_drawdown": metrics.get("max_drawdown", 0),
                    "out_sample_trades": oos_bt["total_trades"],
                })

        df = pd.DataFrame(oos_results)
        logger.info(f"Walk-forward completed: {len(oos_results)} windows evaluated")
        return df

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
__all__ = ["ParameterScanner", "_run_single_backtest"]
