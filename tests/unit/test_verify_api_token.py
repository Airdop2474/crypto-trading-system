"""
verify_api_token() dependency 测试

覆盖场景：
- API_TOKEN 未配置（None / 空）→ 503
- 无 token / 不匹配 → 403
- 匹配 → 200
- 边界：token 为 None / 空字符串 → 403
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from fastapi.testclient import TestClient

from src.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


# ── 503: API_TOKEN 未配置 ──────────────────────────────────────────────

def test_api_token_none_returns_503(client, monkeypatch):
    """API_TOKEN = None → 503 SERVICE_UNAVAILABLE"""
    from src.utils.config import config
    monkeypatch.setattr(config, "API_TOKEN", None)
    r = client.get("/account/summary", headers={"X-API-Token": "doesnt-matter"})
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"].lower()


def test_api_token_empty_string_returns_503(client, monkeypatch):
    """API_TOKEN = "" → 503 SERVICE_UNAVAILABLE"""
    from src.utils.config import config
    monkeypatch.setattr(config, "API_TOKEN", "")
    r = client.get("/account/summary", headers={"X-API-Token": "doesnt-matter"})
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"].lower()


# ── 403: Token 无效 / 缺失 ─────────────────────────────────────────────

def test_missing_token_header_returns_403(client, monkeypatch):
    """请求无 X-API-Token header → 403 FORBIDDEN"""
    from src.utils.config import config
    monkeypatch.setattr(config, "API_TOKEN", "my-secret-token")
    r = client.get("/account/summary")
    assert r.status_code == 403
    assert "invalid" in r.json()["detail"].lower()


def test_wrong_token_returns_403(client, monkeypatch):
    """X-API-Token 不匹配 → 403 FORBIDDEN"""
    from src.utils.config import config
    monkeypatch.setattr(config, "API_TOKEN", "my-secret-token")
    r = client.get("/account/summary", headers={"X-API-Token": "wrong-token"})
    assert r.status_code == 403
    assert "invalid" in r.json()["detail"].lower()


# ── 200: Token 正确 ────────────────────────────────────────────────────

def test_correct_token_returns_200(client, monkeypatch):
    """X-API-Token 匹配 → 200 OK（通过认证）"""
    from src.utils.config import config
    monkeypatch.setattr(config, "API_TOKEN", "my-secret-token")
    r = client.get("/account/summary", headers={"X-API-Token": "my-secret-token"})
    assert r.status_code == 200
    data = r.json()
    # 验证返回了 account/summary 的标准契约结构
    assert "totalEquity" in data


# ── 边界 ───────────────────────────────────────────────────────────────

def test_empty_token_header_value_returns_403(client, monkeypatch):
    """X-API-Token 为空字符串 → 403 FORBIDDEN"""
    from src.utils.config import config
    monkeypatch.setattr(config, "API_TOKEN", "my-secret-token")
    r = client.get("/account/summary", headers={"X-API-Token": ""})
    assert r.status_code == 403
    assert "invalid" in r.json()["detail"].lower()


def test_token_case_sensitive(client, monkeypatch):
    """Token 区分大小写 — 大小写不匹配 → 403"""
    from src.utils.config import config
    monkeypatch.setattr(config, "API_TOKEN", "My-Secret-Token")
    r = client.get("/account/summary", headers={"X-API-Token": "my-secret-token"})
    assert r.status_code == 403
