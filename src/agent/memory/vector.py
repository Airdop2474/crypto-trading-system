"""
向量生成 — 将记忆文本转为 embedding 向量

优先使用 OpenAI 兼容的 embedding API（text-embedding-3-small），
无 API key 时回退到空向量（此时检索仅依赖标签 + 时间）。
"""

import json
from typing import List, Optional

from loguru import logger
from src.utils.config import config as _cfg


def _content_to_text(content: dict) -> str:
    """将记忆内容转为可嵌入的文本字符串。"""
    parts = []
    for k, v in content.items():
        if isinstance(v, (dict, list)):
            parts.append(f"{k}: {json.dumps(v, ensure_ascii=False, default=str)}")
        else:
            parts.append(f"{k}: {v}")
    return " | ".join(parts)


class EmbeddingGenerator:
    """embedding 生成器，自动检测可用后端。"""

    def __init__(self):
        self._provider = self._detect_provider()
        self._dimension = 1536  # text-embedding-3-small 默认维度

    def _detect_provider(self) -> str:
        """检测可用的 embedding 后端。"""
        if _cfg.LLM_API_KEY or _cfg.OPENAI_API_KEY:
            return "openai"
        return "none"

    @property
    def available(self) -> bool:
        return self._provider != "none"

    def generate(self, content: dict) -> List[float]:
        """生成单条记忆的 embedding。"""
        text = _content_to_text(content)
        return self._generate_text(text)

    def generate_batch(self, contents: List[dict]) -> List[List[float]]:
        """批量生成 embedding。"""
        texts = [_content_to_text(c) for c in contents]
        return self._generate_texts(texts)

    def _generate_text(self, text: str) -> List[float]:
        """单文本 embedding。"""
        if self._provider == "openai":
            try:
                import openai
                client = openai.OpenAI(
                    api_key=_cfg.LLM_API_KEY or _cfg.OPENAI_API_KEY,
                )
                resp = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=text,
                )
                return resp.data[0].embedding
            except Exception as e:
                logger.warning(f"Embedding 生成失败，回退空向量: {type(e).__name__}: {e}")

        return []

    def _generate_texts(self, texts: List[str]) -> List[List[float]]:
        """多文本批量 embedding。"""
        if not texts:
            return []
        if self._provider == "openai":
            try:
                import openai
                client = openai.OpenAI(
                    api_key=_cfg.LLM_API_KEY or _cfg.OPENAI_API_KEY,
                )
                resp = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts,
                )
                # 按输入顺序排列
                indexed = {d.index: d.embedding for d in resp.data}
                return [indexed[i] for i in range(len(texts))]
            except Exception as e:
                logger.warning(f"批量 Embedding 失败: {type(e).__name__}: {e}")

        return [[] for _ in texts]


# 全局单例
_embedder = EmbeddingGenerator()


def get_embedder() -> EmbeddingGenerator:
    return _embedder
