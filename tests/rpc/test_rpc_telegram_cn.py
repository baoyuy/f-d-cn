# pragma pylint: disable=protected-access

from unittest.mock import AsyncMock, MagicMock

import pytest

from freqtrade.rpc.telegram_cn import TelegramCN


@pytest.fixture
def telegram_cn():
    telegram = TelegramCN.__new__(TelegramCN)
    telegram._config = {
        "telegram": {
            "chat_id": "1235",
            "reload": True,
        }
    }
    return telegram


def test_telegram_cn_translates_common_labels(telegram_cn) -> None:
    message = (
        "*Status:* `running`\n"
        "*Trade ID:* `1`\n"
        "*Current Pair:* BTC/USDT\n"
        "*Unrealized Profit:* `1.00%`"
    )

    translated = telegram_cn._zh_text(message)

    assert "*状态:* `运行中`" in translated
    assert "*交易 ID:* `1`" in translated
    assert "*当前交易对:* BTC/USDT" in translated
    assert "*浮动收益:* `1.00%`" in translated


def test_telegram_cn_normalizes_market_direction_args(telegram_cn) -> None:
    assert telegram_cn._normalize_market_direction_args(["做多"]) == ["long"]
    assert telegram_cn._normalize_market_direction_args(["做空"]) == ["short"]
    assert telegram_cn._normalize_market_direction_args(["震荡"]) == ["even"]
    assert telegram_cn._normalize_market_direction_args(["无"]) == ["none"]


def test_telegram_cn_translates_legacy_keyboard_config(telegram_cn) -> None:
    telegram_cn._config["telegram"]["keyboard"] = [
        ["/daily", "/profit", "/balance"],
        ["/status", "/status table", "/performance"],
        ["/count", "/start", "/stop", "/help"],
    ]

    telegram_cn._init_keyboard()

    assert telegram_cn._keyboard == [
        ["日报", "收益", "余额"],
        ["状态", "状态表", "表现"],
        ["持仓数", "启动", "停止", "帮助"],
    ]


async def test_telegram_cn_dispatches_chinese_text(telegram_cn) -> None:
    telegram_cn._status = AsyncMock()
    update = MagicMock()
    update.message.text = "状态表"
    update.message.chat_id = 1235
    update.message.message_thread_id = None
    update.callback_query = None
    update.effective_user.id = 5432
    context = MagicMock()
    context.args = []

    await telegram_cn._dispatch_chinese_text(update, context)

    telegram_cn._status.assert_awaited_once_with(update=update, context=context)
    assert context.args == ["table"]


async def test_telegram_cn_unknown_text_returns_help_hint(telegram_cn) -> None:
    telegram_cn._send_msg = AsyncMock()
    update = MagicMock()
    update.message.text = "不存在的指令"
    update.message.chat_id = 1235
    update.message.message_thread_id = None
    update.callback_query = None
    update.effective_user.id = 5432
    context = MagicMock()

    await telegram_cn._dispatch_chinese_text(update, context)

    telegram_cn._send_msg.assert_awaited_once_with("未知指令。发送 `帮助` 查看可用中文指令。")
