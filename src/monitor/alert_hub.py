"""
全局 AlertManager 单例（API server 路径使用）

daemon 脚本有自己的 AlertManager 实例（含 TelegramChannel），
API server 路径通过此模块共享同一组告警通道，确保急停、
风控事件等在非 daemon 场景下也能发出通知。

用法:
    from src.monitor.alert_hub import alert_manager
    alert_manager.emit("CRITICAL", "api", "远程急停已触发")
"""

from __future__ import annotations

from typing import Optional

from src.monitor.alert_manager import AlertManager
from src.monitor.alert_channels import TelegramChannel, WebhookChannel
from src.utils.logger import logger

_manager: Optional[AlertManager] = None


def _init() -> AlertManager:
    """延迟初始化，避免 import 时触发网络连接。"""
    global _manager
    if _manager is not None:
        return _manager

    channels = [TelegramChannel()]

    # Webhook 通道（仅在配置了 URL 时挂载）
    try:
        import os
        webhook_url = os.getenv("ALERT_WEBHOOK_URL", "")
        if webhook_url:
            channels.append(WebhookChannel(url=webhook_url))
    except Exception as e:
        logger.debug(f"Webhook 通道初始化失败（非致命）: {e}")

    _manager = AlertManager(channels=channels)
    logger.info(f"AlertManager 已初始化（{len(channels)} 个通道）")
    return _manager


def get_alert_manager() -> AlertManager:
    """获取全局 AlertManager 单例"""
    return _init()


# 模块级便捷属性：首次访问时延迟初始化
class _LazyProxy:
    """延迟代理，首次访问任意属性时初始化 AlertManager"""
    def __getattr__(self, name: str):
        mgr = _init()
        return getattr(mgr, name)


alert_manager = _LazyProxy()
