"""
LLM 抽象层

优先级：OpenAI → Anthropic → 本地规则回退。
无 API key 时功能完整可用，仅解读质量略低。
"""

import json
import time
from typing import Dict, Any, Optional
from loguru import logger

from src.utils.config import config as _cfg

# API 超时
_TIMEOUT_SECONDS = 15


class LLMClient:
    """LLM 调用封装：interpret_evolution 为唯一公共方法。"""

    def __init__(self):
        self.provider = self._detect_provider()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def interpret_evolution(
        self,
        strategy_name: str,
        old_params: Dict[str, Any],
        new_params: Dict[str, Any],
        walk_forward_results: Dict[str, Any],
        current_metrics: Dict[str, Any],
        proposed_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """解读一次策略进化。

        返回:
            {
                "summary": str,
                "reasoning": str,
                "risks": str,
                "confidence": float,   # 0-1
                "recommendation": str,  # "apply" | "reject" | "caution"
            }
        """
        if self.provider == "openai":
            return self._call_openai(
                strategy_name, old_params, new_params,
                walk_forward_results, current_metrics, proposed_metrics,
            )
        elif self.provider == "anthropic":
            return self._call_anthropic(
                strategy_name, old_params, new_params,
                walk_forward_results, current_metrics, proposed_metrics,
            )
        else:
            return self._local_interpret(
                strategy_name, old_params, new_params,
                walk_forward_results, current_metrics, proposed_metrics,
            )

    # ------------------------------------------------------------------
    # Provider 检测
    # ------------------------------------------------------------------

    def _detect_provider(self) -> str:
        if _cfg.OPENAI_API_KEY:
            return "openai"
        if _cfg.ANTHROPIC_API_KEY:
            return "anthropic"
        return "local"

    # ------------------------------------------------------------------
    # OpenAI
    # ------------------------------------------------------------------

    def _call_openai(self, *args) -> Dict[str, Any]:
        try:
            import openai
        except ImportError:
            logger.warning("openai 包未安装，回退本地解读")
            return self._local_interpret(*args)

        prompt = self._build_prompt(*args)

        try:
            client = openai.OpenAI(
                api_key=_cfg.OPENAI_API_KEY,
                timeout=_TIMEOUT_SECONDS,
            )
            resp = client.chat.completions.create(
                model=_cfg.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )
            content = resp.choices[0].message.content
            return self._parse_llm_response(content)
        except Exception as e:
            logger.warning(f"OpenAI 调用失败 ({type(e).__name__}: {e})，回退本地解读")
            return self._local_interpret(*args)

    # ------------------------------------------------------------------
    # Anthropic
    # ------------------------------------------------------------------

    def _call_anthropic(self, *args) -> Dict[str, Any]:
        try:
            import anthropic
        except ImportError:
            logger.warning("anthropic 包未安装，回退本地解读")
            return self._local_interpret(*args)

        prompt = self._build_prompt(*args)

        try:
            client = anthropic.Anthropic(
                api_key=_cfg.ANTHROPIC_API_KEY,
                timeout=_TIMEOUT_SECONDS,
            )
            resp = client.messages.create(
                model=_cfg.ANTHROPIC_MODEL,
                max_tokens=800,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.content[0].text
            return self._parse_llm_response(content)
        except Exception as e:
            logger.warning(f"Anthropic 调用失败 ({type(e).__name__}: {e})，回退本地解读")
            return self._local_interpret(*args)

    # ------------------------------------------------------------------
    # 本地规则回退
    # ------------------------------------------------------------------

    def _local_interpret(
        self,
        strategy_name: str,
        old_params: Dict[str, Any],
        new_params: Dict[str, Any],
        walk_forward_results: Dict[str, Any],
        current_metrics: Dict[str, Any],
        proposed_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """纯规则解读，不依赖外部 API。"""

        old_sharpe = current_metrics.get("sharpe_ratio", 0)
        new_sharpe = proposed_metrics.get("sharpe_ratio", 0)
        old_dd = current_metrics.get("max_drawdown", 0)
        new_dd = proposed_metrics.get("max_drawdown", 0)
        old_return = current_metrics.get("total_return", 0)
        new_return = proposed_metrics.get("total_return", 0)

        # 变化量
        sharpe_delta = new_sharpe - old_sharpe
        dd_delta = new_dd - old_dd
        return_delta = new_return - old_return

        # 参数变化描述
        param_changes = []
        for key in new_params:
            old_v = old_params.get(key, "?")
            new_v = new_params[key]
            if old_v != "?" and old_v != 0:
                pct = (new_v - old_v) / abs(old_v) * 100
                param_changes.append(f"{key}: {old_v} → {new_v} ({pct:+.0f}%)")
            else:
                param_changes.append(f"{key}: {old_v} → {new_v}")

        # 综合判断
        confidence = 0.5
        recommendation = "caution"
        risks_parts = []

        if sharpe_delta > 0:
            confidence += 0.2
        else:
            confidence -= 0.1
            risks_parts.append("Sharpe 下降")

        if dd_delta < 0:
            confidence += 0.1
        elif dd_delta > 0.05:
            confidence -= 0.1
            risks_parts.append(f"回撤上升 {dd_delta:.1%}")

        if return_delta > 0:
            confidence += 0.1
        else:
            risks_parts.append("收益率下降")

        # Walk-forward 稳定性
        oos_sharpes = walk_forward_results.get("oos_sharpes", [])
        if len(oos_sharpes) >= 2:
            import statistics
            cv = statistics.stdev(oos_sharpes) / abs(statistics.mean(oos_sharpes)) if statistics.mean(oos_sharpes) != 0 else 999
            if cv < 0.3:
                confidence += 0.1
            elif cv > 0.5:
                confidence -= 0.1
                risks_parts.append(f"OOS 波动大 (CV={cv:.0%})")

        confidence = max(0.0, min(1.0, confidence))

        if confidence >= 0.7 and sharpe_delta > 0:
            recommendation = "apply"
        elif confidence < 0.4 or sharpe_delta < -0.1:
            recommendation = "reject"

        # 组装文本
        summary = (
            f"{strategy_name} 进化分析：Sharpe {old_sharpe:.3f} → {new_sharpe:.3f} "
            f"({'↑' if sharpe_delta >= 0 else '↓'}{abs(sharpe_delta):.3f})，"
            f"最大回撤 {old_dd:.1%} → {new_dd:.1%}，"
            f"总收益 {old_return:.1%} → {new_return:.1%}。"
        )

        reasoning = (
            f"参数调整: {'; '.join(param_changes)}。"
            f"基于 {len(oos_sharpes)} 个 walk-forward 窗口验证，"
            f"OOS 平均 Sharpe {statistics.mean(oos_sharpes):.3f}" if oos_sharpes else
            f"参数调整: {'; '.join(param_changes)}。"
        )

        risks = "; ".join(risks_parts) if risks_parts else "未发现显著风险"

        return {
            "summary": summary,
            "reasoning": reasoning,
            "risks": risks,
            "confidence": round(confidence, 2),
            "recommendation": recommendation,
        }

    # ------------------------------------------------------------------
    # Prompt 构建 + 响应解析
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        strategy_name: str,
        old_params: Dict[str, Any],
        new_params: Dict[str, Any],
        walk_forward_results: Dict[str, Any],
        current_metrics: Dict[str, Any],
        proposed_metrics: Dict[str, Any],
    ) -> str:
        return (
            f"你是一个量化交易策略分析专家。请分析以下策略参数进化：\n\n"
            f"策略名称: {strategy_name}\n"
            f"当前参数: {json.dumps(old_params, ensure_ascii=False)}\n"
            f"新参数: {json.dumps(new_params, ensure_ascii=False)}\n"
            f"当前指标: {json.dumps(current_metrics, ensure_ascii=False)}\n"
            f"新指标: {json.dumps(proposed_metrics, ensure_ascii=False)}\n"
            f"Walk-Forward 结果: {json.dumps(walk_forward_results, ensure_ascii=False)}\n\n"
            f"请用 JSON 格式返回以下字段：\n"
            f"- summary: 一句话总结（50字内）\n"
            f"- reasoning: 参数调整的逻辑分析\n"
            f"- risks: 潜在风险\n"
            f"- confidence: 0-1 的置信度\n"
            f"- recommendation: 'apply' / 'reject' / 'caution'\n"
        )

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """从 LLM 响应中提取 JSON。"""
        try:
            # 尝试直接解析
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 块
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 尝试提取 { ... } 块
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # 解析失败：返回基本信息
        return {
            "summary": content[:200],
            "reasoning": "LLM 响应解析失败",
            "risks": "未知",
            "confidence": 0.3,
            "recommendation": "caution",
        }


# ------------------------------------------------------------------
# 系统提示
# ------------------------------------------------------------------

SYSTEM_PROMPT = (
    "你是量化交易策略分析专家。请基于 walk-forward 回测数据分析策略参数进化的合理性。"
    "关注 Sharpe 比率变化、最大回撤、交易频率和 OOS 稳定性。"
    "返回严格的 JSON 格式，不要添加多余解释。"
)
