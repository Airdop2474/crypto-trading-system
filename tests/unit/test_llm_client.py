"""
LLM Client 单元测试

覆盖：Provider 检测优先级、base_url 传递、model 选择、向后兼容。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest


def _make_config(**overrides):
    """创建一个带默认值的 mock config 对象。"""
    defaults = {
        "LLM_PROVIDER": "",
        "LLM_API_KEY": "",
        "LLM_BASE_URL": "",
        "LLM_MODEL": "",
        "OPENAI_API_KEY": "",
        "OPENAI_MODEL": "gpt-4o-mini",
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_MODEL": "claude-sonnet-4-20250514",
    }
    defaults.update(overrides)
    cfg = MagicMock()
    for k, v in defaults.items():
        setattr(cfg, k, v)
    return cfg


class TestDetectProvider:
    """Provider 检测优先级测试。"""

    def test_llm_api_key_defaults_to_openai(self):
        with patch("src.agent.llm_client._cfg", _make_config(LLM_API_KEY="sk-xxx")):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client.provider == "openai"

    def test_llm_api_key_with_anthropic_provider(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            LLM_API_KEY="sk-xxx", LLM_PROVIDER="anthropic"
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client.provider == "anthropic"

    def test_llm_api_key_with_local_provider(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            LLM_API_KEY="sk-xxx", LLM_PROVIDER="local"
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client.provider == "local"

    def test_llm_api_key_invalid_provider_defaults_openai(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            LLM_API_KEY="sk-xxx", LLM_PROVIDER="unknown_llm"
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client.provider == "openai"

    def test_openai_key_fallback(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            OPENAI_API_KEY="sk-openai-key"
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client.provider == "openai"

    def test_anthropic_key_fallback(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            ANTHROPIC_API_KEY="sk-ant-key"
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client.provider == "anthropic"

    def test_llm_key_takes_priority_over_openai_key(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            LLM_API_KEY="sk-llm", LLM_PROVIDER="anthropic",
            OPENAI_API_KEY="sk-openai",
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client.provider == "anthropic"

    def test_no_keys_returns_local(self):
        with patch("src.agent.llm_client._cfg", _make_config()):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client.provider == "local"


class TestGetModel:
    """Model 选择逻辑测试。"""

    def test_llm_model_takes_priority(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            LLM_API_KEY="sk-xxx", LLM_MODEL="deepseek-chat",
            OPENAI_MODEL="gpt-4o",
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client._get_model() == "deepseek-chat"

    def test_openai_default_model(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            OPENAI_API_KEY="sk-xxx",
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client._get_model() == "gpt-4o-mini"

    def test_openai_custom_model_legacy(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            OPENAI_API_KEY="sk-xxx", OPENAI_MODEL="gpt-4-turbo",
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client._get_model() == "gpt-4-turbo"

    def test_anthropic_default_model(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            ANTHROPIC_API_KEY="sk-ant",
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client._get_model() == "claude-sonnet-4-20250514"

    def test_anthropic_custom_model_legacy(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            ANTHROPIC_API_KEY="sk-ant", ANTHROPIC_MODEL="claude-3-opus",
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client._get_model() == "claude-3-opus"


class TestGetApiKey:
    """API Key 获取逻辑测试。"""

    def test_llm_key_takes_priority(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            LLM_API_KEY="sk-unified", OPENAI_API_KEY="sk-openai",
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client._get_api_key() == "sk-unified"

    def test_openai_key_fallback(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            OPENAI_API_KEY="sk-openai",
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client._get_api_key() == "sk-openai"

    def test_anthropic_key_fallback(self):
        with patch("src.agent.llm_client._cfg", _make_config(
            ANTHROPIC_API_KEY="sk-ant",
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client._get_api_key() == "sk-ant"


class TestBaseUrl:
    """Base URL 传递测试。"""

    def test_openai_with_custom_base_url(self):
        mock_openai = MagicMock()
        mock_client_instance = MagicMock()
        mock_openai.OpenAI.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"summary":"ok","reasoning":"test","risks":"none","confidence":0.8,"recommendation":"apply"}'
        mock_client_instance.chat.completions.create.return_value = mock_response

        with patch("src.agent.llm_client._cfg", _make_config(
            LLM_API_KEY="sk-deepseek",
            LLM_BASE_URL="https://api.deepseek.com/v1",
            LLM_MODEL="deepseek-chat",
        )):
            with patch.dict("sys.modules", {"openai": mock_openai}):
                from src.agent.llm_client import LLMClient
                client = LLMClient()
                result = client.interpret_evolution(
                    "test", {"a": 1}, {"a": 2}, {}, {}, {}
                )

        # Verify base_url was passed
        call_kwargs = mock_openai.OpenAI.call_args
        assert call_kwargs[1]["base_url"] == "https://api.deepseek.com/v1"
        assert call_kwargs[1]["api_key"] == "sk-deepseek"

        # Verify model
        create_kwargs = mock_client_instance.chat.completions.create.call_args
        assert create_kwargs[1]["model"] == "deepseek-chat"

    def test_openai_without_base_url(self):
        mock_openai = MagicMock()
        mock_client_instance = MagicMock()
        mock_openai.OpenAI.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"summary":"ok","reasoning":"t","risks":"n","confidence":0.5,"recommendation":"caution"}'
        mock_client_instance.chat.completions.create.return_value = mock_response

        with patch("src.agent.llm_client._cfg", _make_config(
            OPENAI_API_KEY="sk-openai",
        )):
            with patch.dict("sys.modules", {"openai": mock_openai}):
                from src.agent.llm_client import LLMClient
                client = LLMClient()
                client.interpret_evolution("test", {}, {}, {}, {}, {})

        call_kwargs = mock_openai.OpenAI.call_args
        assert "base_url" not in call_kwargs[1]

    def test_anthropic_with_custom_base_url(self):
        mock_anthropic = MagicMock()
        mock_client_instance = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = '{"summary":"ok","reasoning":"t","risks":"n","confidence":0.7,"recommendation":"apply"}'
        mock_client_instance.messages.create.return_value = mock_response

        with patch("src.agent.llm_client._cfg", _make_config(
            LLM_API_KEY="sk-anthropic",
            LLM_PROVIDER="anthropic",
            LLM_BASE_URL="https://custom-anthropic.example.com",
            LLM_MODEL="claude-3-haiku",
        )):
            with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
                from src.agent.llm_client import LLMClient
                client = LLMClient()
                client.interpret_evolution("test", {}, {}, {}, {}, {})

        call_kwargs = mock_anthropic.Anthropic.call_args
        assert call_kwargs[1]["base_url"] == "https://custom-anthropic.example.com"

        create_kwargs = mock_client_instance.messages.create.call_args
        assert create_kwargs[1]["model"] == "claude-3-haiku"


class TestBackwardCompatibility:
    """向后兼容测试：旧 OPENAI_API_KEY 仍然可用。"""

    def test_old_openai_key_still_works(self):
        """只用 OPENAI_API_KEY + OPENAI_MODEL，不设置任何 LLM_ 变量。"""
        mock_openai = MagicMock()
        mock_client_instance = MagicMock()
        mock_openai.OpenAI.return_value = mock_client_instance

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"summary":"legacy","reasoning":"ok","risks":"none","confidence":0.6,"recommendation":"caution"}'
        mock_client_instance.chat.completions.create.return_value = mock_response

        with patch("src.agent.llm_client._cfg", _make_config(
            OPENAI_API_KEY="sk-legacy-key",
            OPENAI_MODEL="gpt-4-turbo",
        )):
            with patch.dict("sys.modules", {"openai": mock_openai}):
                from src.agent.llm_client import LLMClient
                client = LLMClient()
                assert client.provider == "openai"
                assert client._get_api_key() == "sk-legacy-key"
                assert client._get_model() == "gpt-4-turbo"

                result = client.interpret_evolution("test", {}, {}, {}, {}, {})
                assert result["summary"] == "legacy"

                # base_url should NOT be passed
                call_kwargs = mock_openai.OpenAI.call_args
                assert "base_url" not in call_kwargs[1]

    def test_old_anthropic_key_still_works(self):
        """只用 ANTHROPIC_API_KEY + ANTHROPIC_MODEL。"""
        with patch("src.agent.llm_client._cfg", _make_config(
            ANTHROPIC_API_KEY="sk-ant-legacy",
            ANTHROPIC_MODEL="claude-3-opus",
        )):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client.provider == "anthropic"
            assert client._get_api_key() == "sk-ant-legacy"
            assert client._get_model() == "claude-3-opus"


class TestLocalInterpret:
    """本地规则回退不受影响。"""

    def test_local_provider_uses_rules(self):
        with patch("src.agent.llm_client._cfg", _make_config()):
            from src.agent.llm_client import LLMClient
            client = LLMClient()
            assert client.provider == "local"
            result = client.interpret_evolution(
                "test_strategy",
                {"rsi_period": 14},
                {"rsi_period": 12},
                {"oos_sharpes": [1.2, 1.1, 1.3]},
                {"sharpe_ratio": 1.0, "max_drawdown": 0.1, "total_return": 0.05},
                {"sharpe_ratio": 1.3, "max_drawdown": 0.08, "total_return": 0.08},
            )
            assert result["recommendation"] in ("apply", "reject", "caution")
            assert 0 <= result["confidence"] <= 1
