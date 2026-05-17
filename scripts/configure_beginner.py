#!/usr/bin/env python3
"""Beginner friendly config wizard for the Chinese Freqtrade build."""

from __future__ import annotations

import argparse
import json
import re
import secrets
from datetime import datetime
from getpass import getpass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "max_open_trades": 3,
    "stake_currency": "USDT",
    "stake_amount": 100,
    "tradable_balance_ratio": 0.99,
    "fiat_display_currency": "USD",
    "dry_run": True,
    "dry_run_wallet": 1000,
    "cancel_open_orders_on_exit": False,
    "trading_mode": "spot",
    "margin_mode": "",
    "timeframe": "5m",
    "minimal_roi": {
        "120": 0.0,
        "60": 0.01,
        "30": 0.02,
        "0": 0.04,
    },
    "stoploss": -0.08,
    "trailing_stop": True,
    "trailing_stop_positive": 0.015,
    "trailing_stop_positive_offset": 0.03,
    "trailing_only_offset_is_reached": True,
    "unfilledtimeout": {
        "entry": 10,
        "exit": 10,
        "exit_timeout_count": 0,
        "unit": "minutes",
    },
    "entry_pricing": {
        "price_side": "same",
        "use_order_book": True,
        "order_book_top": 1,
        "price_last_balance": 0.0,
    },
    "exit_pricing": {
        "price_side": "same",
        "use_order_book": True,
        "order_book_top": 1,
        "price_last_balance": 0.0,
    },
    "order_types": {
        "entry": "limit",
        "exit": "limit",
        "emergency_exit": "market",
        "force_exit": "market",
        "force_entry": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
    },
    "order_time_in_force": {
        "entry": "GTC",
        "exit": "GTC",
    },
    "exchange": {
        "name": "binance",
        "key": "",
        "secret": "",
        "pair_whitelist": ["BTC/USDT", "ETH/USDT"],
        "pair_blacklist": [],
    },
    "pairlists": [{"method": "StaticPairList"}],
    "telegram": {
        "enabled": False,
        "language": "zh",
        "token": "",
        "chat_id": "",
    },
    "api_server": {
        "enabled": True,
        "listen_ip_address": "0.0.0.0",
        "listen_port": 8080,
        "verbosity": "error",
        "enable_openapi": False,
        "jwt_secret_key": "",
        "ws_token": "",
        "CORS_origins": [],
        "username": "freqtrader",
        "password": "",
    },
    "bot_name": "freqtrade-cn",
    "initial_state": "running",
    "force_entry_enable": False,
    "internals": {
        "process_throttle_secs": 5,
        "heartbeat_interval": 60,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="中文定制版 Freqtrade 新手配置向导")
    parser.add_argument(
        "--config",
        default="user_data/config.json",
        help="配置文件路径，默认是 user_data/config.json",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="使用安全默认值写入配置，不进入交互提问",
    )
    return parser.parse_args()


def prompt_text(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def prompt_bool(label: str, default: bool) -> bool:
    default_text = "Y/n" if default else "y/N"
    value = input(f"{label} [{default_text}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "true", "1", "是", "确认"}


def prompt_float(label: str, default: float) -> float:
    while True:
        value = prompt_text(label, str(default))
        try:
            return float(value)
        except ValueError:
            print("请输入数字，例如 100 或 25.5。")


def prompt_int(label: str, default: int) -> int:
    while True:
        value = prompt_text(label, str(default))
        try:
            return int(value)
        except ValueError:
            print("请输入整数。")


def prompt_pairs(default: list[str]) -> list[str]:
    value = prompt_text("交易对，用英文逗号分隔", ",".join(default))
    pairs = [pair.strip().upper() for pair in value.split(",") if pair.strip()]
    if not pairs:
        print("交易对不能为空，已保留默认 BTC/USDT,ETH/USDT。")
        return default
    return pairs


def deep_merge(base: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in existing.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    return deep_merge(DEFAULT_CONFIG, json.loads(path.read_text(encoding="utf-8")))


def ensure_api_secrets(config: dict[str, Any]) -> None:
    api_server = config.setdefault("api_server", {})
    api_server.setdefault("enabled", True)
    api_server.setdefault("listen_ip_address", "0.0.0.0")
    api_server.setdefault("listen_port", 8080)
    api_server.setdefault("verbosity", "error")
    api_server.setdefault("enable_openapi", False)
    api_server.setdefault("CORS_origins", [])
    api_server.setdefault("username", "freqtrader")
    if not api_server.get("jwt_secret_key"):
        api_server["jwt_secret_key"] = secrets.token_urlsafe(48)
    if not api_server.get("ws_token"):
        api_server["ws_token"] = secrets.token_urlsafe(36)
    if not api_server.get("password"):
        api_server["password"] = api_server["ws_token"]


def configure_interactively(config: dict[str, Any]) -> dict[str, Any]:
    print("中文定制版 Freqtrade 新手配置向导")
    print("默认保持 dry_run 模拟盘。实盘前必须先回测和模拟盘验证。")

    exchange = config.setdefault("exchange", {})
    telegram = config.setdefault("telegram", {})

    config["strategy"] = prompt_text(
        "策略名",
        str(config.get("strategy") or "CnTrendPullbackStrategy"),
    )
    config["timeframe"] = prompt_text("K线周期", str(config.get("timeframe") or "5m"))
    config["max_open_trades"] = prompt_int("最大同时持仓数", int(config.get("max_open_trades", 3)))
    config["stake_currency"] = prompt_text("计价币种", str(config.get("stake_currency") or "USDT"))
    config["stake_amount"] = prompt_float("每笔投入金额", float(config.get("stake_amount", 100)))

    keep_dry_run = prompt_bool("保持模拟盘 dry_run=true", bool(config.get("dry_run", True)))
    if keep_dry_run:
        config["dry_run"] = True
    else:
        confirm = prompt_text("输入 我确认实盘风险 才会关闭 dry_run", "")
        config["dry_run"] = confirm != "我确认实盘风险"
        if config["dry_run"]:
            print("未确认实盘风险，继续保持 dry_run=true。")

    config["trading_mode"] = "spot"
    config["margin_mode"] = ""
    exchange["name"] = prompt_text("交易所", str(exchange.get("name") or "binance"))
    exchange["pair_whitelist"] = prompt_pairs(
        exchange.get("pair_whitelist") or ["BTC/USDT", "ETH/USDT"]
    )
    exchange.setdefault("pair_blacklist", [])

    if prompt_bool("是否配置 Telegram 中文机器人", bool(telegram.get("enabled", False))):
        telegram["enabled"] = True
        telegram["language"] = "zh"
        token_default = "已配置，直接回车保留" if telegram.get("token") else ""
        token_prompt = f"Telegram Bot Token{f' [{token_default}]' if token_default else ''}: "
        token = getpass(token_prompt).strip()
        if token:
            telegram["token"] = token
        chat_id = prompt_text(
            "Telegram Chat ID",
            str(telegram.get("chat_id") or ""),
        )
        if chat_id:
            telegram["chat_id"] = chat_id
    else:
        telegram["enabled"] = False
        telegram["language"] = "zh"

    validate_config(config)
    ensure_api_secrets(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    telegram = config.get("telegram", {})
    if telegram.get("enabled"):
        token = str(telegram.get("token", "")).strip()
        chat_id = str(telegram.get("chat_id", "")).strip()
        if not re.match(r"^\d+:[A-Za-z0-9_-]+$", token):
            raise SystemExit("Telegram token 格式错误，必须是 机器人ID:密钥。")
        if not re.match(r"^-?\d+$", chat_id):
            raise SystemExit("Telegram chat_id 格式错误，必须是纯数字。")
    if not config.get("dry_run"):
        print("警告：dry_run=false，机器人可能真实下单。")


def write_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + f".bak.{datetime.now():%Y%m%d_%H%M%S}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"已备份原配置：{backup}")
    path.write_text(json.dumps(config, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    print(f"已写入配置：{path}")


def main() -> None:
    args = parse_args()
    path = Path(args.config)
    config = load_config(path)
    ensure_api_secrets(config)
    if args.yes:
        config["strategy"] = config.get("strategy") or "CnTrendPullbackStrategy"
        validate_config(config)
    else:
        config = configure_interactively(config)
    write_config(path, config)


if __name__ == "__main__":
    main()
