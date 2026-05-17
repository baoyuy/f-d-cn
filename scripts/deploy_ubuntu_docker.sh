#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="${APP_NAME:-freqtrade-cn}"
INSTALL_DIR="${INSTALL_DIR:-/opt/freqtrade-cn}"
REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-develop}"
API_PORT="${API_PORT:-8080}"
STRATEGY="${STRATEGY:-SampleStrategy}"
IMAGE_NAME="${IMAGE_NAME:-freqtrade-cn:local}"

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
    log "安装基础工具"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        ca-certificates \
        curl \
        git \
        gnupg \
        lsb-release
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
        return
    fi

    if [ -d "$INSTALL_DIR/.git" ]; then
        git -C "$INSTALL_DIR" fetch origin "$BRANCH"
        git -C "$INSTALL_DIR" checkout "$BRANCH"
        git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
        return
    fi

    if [ -e "$INSTALL_DIR" ]; then
        fail "${INSTALL_DIR} 已存在但不是 git 仓库，请先处理该目录或修改 INSTALL_DIR。"
    fi

    if [ -z "$REPO_URL" ]; then
        fail "未设置 REPO_URL。使用 curl 一键部署时必须传入你的中文化仓库地址。"
    fi

    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
}

write_compose_file() {
    log "生成 docker-compose.yml"
    cd "$INSTALL_DIR"

    if [ -f docker-compose.yml ]; then
        cp docker-compose.yml "docker-compose.yml.bak.$(date +%Y%m%d_%H%M%S)"
    fi

    cat >docker-compose.yml <<EOF
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
    "timeframe": "5m",
    "minimal_roi": {
        "0": 0.04,
        "20": 0.02,
        "30": 0.01,
        "40": 0.0
    },
    "stoploss": -0.10,
    "trailing_stop": false,
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
            "BTC/USDT",
            "ETH/USDT"
        ],
        "pair_blacklist": []
    },
    "pairlists": [
        {
            "method": "StaticPairList"
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

initialize_user_data() {
    log "构建镜像并执行官方 user_data 初始化"
    cd "$INSTALL_DIR"
    docker compose build
    docker compose run --rm freqtrade create-userdir --userdir user_data
    write_default_config
    mkdir -p user_data/logs
    chown -R 1000:1000 user_data
}

start_bot() {
    log "启动 Freqtrade 容器"
    cd "$INSTALL_DIR"
    docker compose up -d --build
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
  cd ${INSTALL_DIR} && git pull --ff-only && docker compose up -d --build

注意:
  默认是 dry_run: true，不会真实下单。
  Telegram 默认关闭。启用前请编辑 config.json，填写 token/chat_id，并保留 language: "zh"。
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
