#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="${APP_NAME:-freqtrade-cn}"
INSTALL_DIR="${INSTALL_DIR:-/opt/freqtrade-cn}"
REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"
API_PORT="${API_PORT:-8080}"
STRATEGY="${STRATEGY:-CnStrongTrendStrategy}"
IMAGE_NAME="${IMAGE_NAME:-freqtrade-cn:local}"
TELEGRAM_ENABLED="${TELEGRAM_ENABLED:-}"
TELEGRAM_TOKEN="${TELEGRAM_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"
TELEGRAM_LANGUAGE="${TELEGRAM_LANGUAGE:-zh}"
SOURCE_CHANGED=0
COMPOSE_CHANGED=0
IMAGE_BUILT=0

log() {
    printf '\n[%s] %s\n' "$APP_NAME" "$1"
}

fail() {
    printf '\n[%s] 部署失败: %s\n' "$APP_NAME" "$1" >&2
    exit 1
}

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        fail "请使用 root 执行，或使用 sudo bash scripts/deploy_ubuntu_docker.sh"
    fi
}

detect_os() {
    if [ ! -r /etc/os-release ]; then
        fail "无法识别系统。此脚本只支持 Ubuntu/Debian。"
    fi

    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-}"
    OS_CODENAME="${VERSION_CODENAME:-}"

    if [ "$OS_ID" != "ubuntu" ] && [ "$OS_ID" != "debian" ]; then
        fail "当前系统是 ${PRETTY_NAME:-unknown}，此脚本只支持 Ubuntu/Debian。"
    fi

    if [ -z "$OS_CODENAME" ]; then
        fail "无法识别系统版本代号，Docker apt 源无法安全配置。"
    fi
}

install_base_packages() {
    local missing=0

    for cmd in curl git gpg lsb_release python3; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing=1
            break
        fi
    done

    if [ "$missing" -eq 0 ] && [ -r /etc/ssl/certs/ca-certificates.crt ]; then
        log "检测到基础工具已安装，跳过 apt 安装"
        return
    fi

    log "安装基础工具"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        ca-certificates \
        curl \
        git \
        gnupg \
        lsb-release \
        python3
}

install_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        log "检测到 Docker 和 Docker Compose，跳过安装"
        return
    fi

    log "安装 Docker Engine 和 Docker Compose 插件"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" \
        | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    cat >/etc/apt/sources.list.d/docker.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${OS_ID} ${OS_CODENAME} stable
EOF

    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        containerd.io \
        docker-buildx-plugin \
        docker-ce \
        docker-ce-cli \
        docker-compose-plugin

    if command -v systemctl >/dev/null 2>&1; then
        systemctl enable --now docker
    fi

    if [ -n "${SUDO_USER:-}" ] && id "$SUDO_USER" >/dev/null 2>&1; then
        usermod -aG docker "$SUDO_USER" || true
    fi
}

prepare_source() {
    log "准备源码目录: ${INSTALL_DIR}"
    local source_dir
    source_dir="$(pwd)"

    if [ -f "${source_dir}/pyproject.toml" ] \
        && [ -d "${source_dir}/freqtrade" ] \
        && [ -f "${source_dir}/Dockerfile" ]; then
        if [ "$(readlink -f "$source_dir")" = "$(readlink -f "$INSTALL_DIR" 2>/dev/null || true)" ]; then
            log "检测到当前目录就是部署源码目录，跳过复制"
            return
        fi

        log "检测到本地源码，复制到 ${INSTALL_DIR}"
        mkdir -p "$INSTALL_DIR"
        tar \
            --exclude='./.git' \
            --exclude='./.mypy_cache' \
            --exclude='./.pytest_cache' \
            --exclude='./.ruff_cache' \
            --exclude='./.venv' \
            --exclude='./__pycache__' \
            --exclude='./user_data' \
            -cf - . | tar -xf - -C "$INSTALL_DIR"
        if [ -d "${source_dir}/user_data/strategies" ]; then
            mkdir -p "$INSTALL_DIR/user_data/strategies"
            find "${source_dir}/user_data/strategies" \
                -maxdepth 1 \
                -type f \
                -name '*.py' \
                -exec cp {} "$INSTALL_DIR/user_data/strategies/" \;
        fi
        SOURCE_CHANGED=1
        return
    fi

    if [ -d "$INSTALL_DIR/.git" ]; then
        local before_head
        local after_head
        before_head="$(git -C "$INSTALL_DIR" rev-parse HEAD 2>/dev/null || true)"
        git -C "$INSTALL_DIR" fetch origin "$BRANCH"
        git -C "$INSTALL_DIR" checkout "$BRANCH"
        git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
        after_head="$(git -C "$INSTALL_DIR" rev-parse HEAD 2>/dev/null || true)"
        if [ "$before_head" != "$after_head" ]; then
            SOURCE_CHANGED=1
            log "检测到源码已更新: ${before_head:-unknown} -> ${after_head:-unknown}"
        else
            log "源码已经是最新版本"
        fi
        return
    fi

    if [ -e "$INSTALL_DIR" ]; then
        fail "${INSTALL_DIR} 已存在但不是 git 仓库，请先处理该目录或修改 INSTALL_DIR。"
    fi

    if [ -z "$REPO_URL" ]; then
        fail "未设置 REPO_URL。使用 curl 一键部署时必须传入你的中文化仓库地址。"
    fi

    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
    SOURCE_CHANGED=1
}

write_compose_file() {
    log "生成 docker-compose.yml"
    cd "$INSTALL_DIR"

    local compose_tmp
    compose_tmp="$(mktemp)"

    cat >"$compose_tmp" <<EOF
---
services:
  freqtrade:
    build:
      context: .
      dockerfile: ./Dockerfile
    image: ${IMAGE_NAME}
    restart: unless-stopped
    container_name: ${APP_NAME}
    volumes:
      - "./user_data:/freqtrade/user_data"
    ports:
      - "127.0.0.1:${API_PORT}:8080"
    command: >
      trade
      --logfile /freqtrade/user_data/logs/freqtrade.log
      --db-url sqlite:////freqtrade/user_data/tradesv3.sqlite
      --config /freqtrade/user_data/config.json
      --strategy ${STRATEGY}
EOF

    if [ -f docker-compose.yml ] && cmp -s "$compose_tmp" docker-compose.yml; then
        rm -f "$compose_tmp"
        log "docker-compose.yml 未变化"
        return
    fi

    if [ -f docker-compose.yml ]; then
        cp docker-compose.yml "docker-compose.yml.bak.$(date +%Y%m%d_%H%M%S)"
    fi

    mv "$compose_tmp" docker-compose.yml
    COMPOSE_CHANGED=1
}

random_secret() {
    local length="${1:-48}"
    local secret
    set +o pipefail
    secret="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$length")"
    set -o pipefail
    printf '%s' "$secret"
}

write_default_config() {
    local config_file="${INSTALL_DIR}/user_data/config.json"

    if [ -f "$config_file" ]; then
        log "检测到已有 user_data/config.json，保留原配置"
        return
    fi

    log "生成非交互 dry-run 默认配置"
    local jwt_secret
    local ws_token
    jwt_secret="$(random_secret 64)"
    ws_token="$(random_secret 48)"

    cat >"$config_file" <<EOF
{
    "max_open_trades": 3,
    "stake_currency": "USDT",
    "stake_amount": 100,
    "tradable_balance_ratio": 0.99,
    "fiat_display_currency": "USD",
    "dry_run": true,
    "dry_run_wallet": 1000,
    "cancel_open_orders_on_exit": false,
    "trading_mode": "spot",
    "margin_mode": "",
    "timeframe": "15m",
    "minimal_roi": {
        "240": 0.0,
        "120": 0.02,
        "60": 0.04,
        "0": 0.08
    },
    "stoploss": -0.06,
    "trailing_stop": true,
    "trailing_stop_positive": 0.025,
    "trailing_stop_positive_offset": 0.05,
    "trailing_only_offset_is_reached": true,
    "unfilledtimeout": {
        "entry": 10,
        "exit": 10,
        "exit_timeout_count": 0,
        "unit": "minutes"
    },
    "entry_pricing": {
        "price_side": "same",
        "use_order_book": true,
        "order_book_top": 1,
        "price_last_balance": 0.0
    },
    "exit_pricing": {
        "price_side": "same",
        "use_order_book": true,
        "order_book_top": 1,
        "price_last_balance": 0.0
    },
    "order_types": {
        "entry": "limit",
        "exit": "limit",
        "emergency_exit": "market",
        "force_exit": "market",
        "force_entry": "market",
        "stoploss": "market",
        "stoploss_on_exchange": false
    },
    "order_time_in_force": {
        "entry": "GTC",
        "exit": "GTC"
    },
    "exchange": {
        "name": "binance",
        "key": "",
        "secret": "",
        "pair_whitelist": [
            ".*/USDT"
        ],
        "pair_blacklist": [
            "BNB/.*",
            ".*UP/USDT",
            ".*DOWN/USDT",
            ".*BULL/USDT",
            ".*BEAR/USDT",
            ".*3L/USDT",
            ".*3S/USDT",
            "USDC/USDT",
            "FDUSD/USDT",
            "TUSD/USDT",
            "BUSD/USDT"
        ]
    },
    "pairlists": [
        {
            "method": "VolumePairList",
            "number_assets": 40,
            "sort_key": "quoteVolume",
            "min_value": 0,
            "refresh_period": 1800
        },
        {
            "method": "AgeFilter",
            "min_days_listed": 10
        },
        {
            "method": "PrecisionFilter"
        },
        {
            "method": "PriceFilter",
            "low_price_ratio": 0.01
        },
        {
            "method": "SpreadFilter",
            "max_spread_ratio": 0.005
        }
    ],
    "telegram": {
        "enabled": false,
        "language": "zh",
        "token": "",
        "chat_id": ""
    },
    "api_server": {
        "enabled": true,
        "listen_ip_address": "0.0.0.0",
        "listen_port": 8080,
        "verbosity": "error",
        "enable_openapi": false,
        "jwt_secret_key": "${jwt_secret}",
        "ws_token": "${ws_token}",
        "CORS_origins": [],
        "username": "freqtrader",
        "password": "${ws_token}"
    },
    "bot_name": "${APP_NAME}",
    "initial_state": "running",
    "force_entry_enable": false,
    "internals": {
        "process_throttle_secs": 5,
        "heartbeat_interval": 60
    }
}
EOF
}

normalize_telegram_config() {
    local config_file="${INSTALL_DIR}/user_data/config.json"

    if [ ! -f "$config_file" ]; then
        fail "找不到配置文件: ${config_file}"
    fi

    if [ -n "$TELEGRAM_TOKEN" ] || [ -n "$TELEGRAM_CHAT_ID" ] || [ -n "$TELEGRAM_ENABLED" ]; then
        log "根据环境变量更新 Telegram 配置"
    else
        log "检查 Telegram 配置"
    fi

    CONFIG_FILE="$config_file" \
    TELEGRAM_ENABLED="$TELEGRAM_ENABLED" \
    TELEGRAM_TOKEN="$TELEGRAM_TOKEN" \
    TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
    TELEGRAM_LANGUAGE="$TELEGRAM_LANGUAGE" \
    python3 <<'PY'
import json
import os
import re
import sys
from pathlib import Path

config_file = Path(os.environ["CONFIG_FILE"])

try:
    config = json.loads(config_file.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    print(f"config.json 不是合法 JSON: {exc}", file=sys.stderr)
    sys.exit(2)

telegram = config.setdefault("telegram", {})
telegram.setdefault("language", "zh")

language = os.environ.get("TELEGRAM_LANGUAGE") or "zh"
if language not in {"zh", "en"}:
    print("TELEGRAM_LANGUAGE 只能是 zh 或 en。", file=sys.stderr)
    sys.exit(2)
telegram["language"] = language

enabled = os.environ.get("TELEGRAM_ENABLED", "")
token = os.environ.get("TELEGRAM_TOKEN", "")
chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

if token:
    telegram["token"] = token
if chat_id:
    telegram["chat_id"] = chat_id
if enabled:
    telegram["enabled"] = enabled.lower() in {"1", "true", "yes", "on", "y"}
elif token and chat_id:
    telegram["enabled"] = True

if telegram.get("enabled"):
    token_value = str(telegram.get("token", "")).strip()
    chat_value = str(telegram.get("chat_id", "")).strip()
    if not re.match(r"^\d+:[A-Za-z0-9_-]+$", token_value):
        print(
            "Telegram token 格式错误。必须填写完整 token，格式是 机器人ID:密钥，"
            "不能只填冒号后面的密钥。",
            file=sys.stderr,
        )
        sys.exit(2)
    if not re.match(r"^-?\d+$", chat_value):
        print("Telegram chat_id 格式错误。必须是纯数字，例如 6767391336。", file=sys.stderr)
        sys.exit(2)

config_file.write_text(
    json.dumps(config, ensure_ascii=False, indent=4) + "\n",
    encoding="utf-8",
)
PY
}

image_exists() {
    docker image inspect "$IMAGE_NAME" >/dev/null 2>&1
}

needs_build() {
    if [ "$SOURCE_CHANGED" -eq 1 ] || [ "$COMPOSE_CHANGED" -eq 1 ] || ! image_exists; then
        return 0
    fi
    return 1
}

build_image_if_needed() {
    if needs_build; then
        log "构建 Docker 镜像"
        cd "$INSTALL_DIR"
        docker compose build
        IMAGE_BUILT=1
    else
        log "源码、Compose 配置和镜像均未变化，跳过镜像构建"
    fi
}

initialize_user_data() {
    log "检查 user_data 初始化状态"
    cd "$INSTALL_DIR"

    if [ ! -d user_data ] || [ ! -d user_data/strategies ] || [ ! -d user_data/logs ]; then
        build_image_if_needed
        log "执行官方 user_data 初始化"
        docker compose run --rm freqtrade create-userdir --userdir user_data
    else
        log "检测到已有 user_data，跳过官方初始化"
    fi

    write_default_config
    normalize_telegram_config
    mkdir -p user_data/logs
    chown -R 1000:1000 user_data
}

start_bot() {
    cd "$INSTALL_DIR"

    local container_id
    container_id="$(docker compose ps -q freqtrade 2>/dev/null || true)"

    if needs_build; then
        if [ "$IMAGE_BUILT" -eq 1 ]; then
            log "启动 Freqtrade 容器"
            docker compose up -d
        else
            log "源码或部署配置有变化，重建并启动 Freqtrade 容器"
            docker compose up -d --build
        fi
        return
    fi

    if [ -n "$container_id" ]; then
        log "配置可能已调整，快速重启现有容器"
        docker compose restart freqtrade
    else
        log "容器不存在，启动 Freqtrade 容器"
        docker compose up -d
    fi
}

print_summary() {
    cat <<EOF

[$APP_NAME] 部署完成。

部署目录:
  ${INSTALL_DIR}

配置文件:
  ${INSTALL_DIR}/user_data/config.json

常用命令:
  cd ${INSTALL_DIR} && docker compose ps
  cd ${INSTALL_DIR} && docker compose logs -f
  cd ${INSTALL_DIR} && docker compose restart
  cd ${INSTALL_DIR} && docker compose down

更新代码并重启:
  再次执行首次部署时使用的同一条一键部署命令即可。
  脚本会自动判断是否需要安装依赖、拉取代码、重建镜像，没变化时只快速重启容器。

注意:
  默认是 dry_run: true，不会真实下单。
  Telegram 默认关闭。可以编辑 config.json，也可以在一键命令里传入 TELEGRAM_TOKEN 和 TELEGRAM_CHAT_ID。
  token 必须是完整格式: 机器人ID:密钥；chat_id 必须是聊天 ID，不是 bot id。
  API 只映射到宿主机 127.0.0.1:${API_PORT}，不要直接暴露到公网。
EOF
}

main() {
    require_root
    detect_os
    install_base_packages
    install_docker
    prepare_source
    write_compose_file
    initialize_user_data
    start_bot
    print_summary
}

main "$@"
