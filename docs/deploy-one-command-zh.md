# Ubuntu/Debian 一键部署

这个脚本用于把中文化版 Freqtrade 部署到全新的 Ubuntu/Debian 服务器，或者已经使用过一段时间的 Ubuntu/Debian 服务器。

部署方式使用 Docker Compose。脚本会自动安装 Docker、拉取源码、构建本地镜像、执行官方 `create-userdir` 初始化，并生成非交互的 dry-run 默认配置。

## 一键命令

把下面的仓库地址换成你自己的中文化仓库地址：

```bash
curl -fsSL https://raw.githubusercontent.com/<你的账号>/<你的仓库>/<分支>/scripts/deploy_ubuntu_docker.sh \
  | sudo env REPO_URL="https://github.com/<你的账号>/<你的仓库>.git" BRANCH="<分支>" bash
```

使用 `curl | bash` 方式时必须传入 `REPO_URL`，否则脚本会拒绝部署，避免误装官方原版。

如果源码已经在服务器上，也可以在仓库根目录运行：

```bash
sudo bash scripts/deploy_ubuntu_docker.sh
```

## 默认行为

- 部署目录：`/opt/freqtrade-cn`
- 镜像：本地构建的 `freqtrade-cn:local`
- 容器名：`freqtrade-cn`
- 配置文件：`/opt/freqtrade-cn/user_data/config.json`
- 默认交易模式：`dry_run: true`
- 默认交易所：`binance`
- 默认策略：`SampleStrategy`
- Telegram 默认关闭，但配置里已写入 `"language": "zh"`
- API 只映射到宿主机 `127.0.0.1:8080`

## 可选环境变量

```bash
sudo env \
  REPO_URL="https://github.com/<你的账号>/<你的仓库>.git" \
  BRANCH="main" \
  INSTALL_DIR="/opt/freqtrade-cn" \
  API_PORT="8080" \
  STRATEGY="SampleStrategy" \
  bash scripts/deploy_ubuntu_docker.sh
```

字段说明：

- `REPO_URL`：你的中文化源码仓库。不要填官方原仓库，否则不会包含中文化改动。
- `BRANCH`：部署分支，默认 `develop`。
- `INSTALL_DIR`：部署目录，默认 `/opt/freqtrade-cn`。
- `API_PORT`：宿主机本地 API 端口，默认 `8080`。
- `STRATEGY`：启动策略，默认 `SampleStrategy`。

## 初始化说明

官方 Docker 初始化通常是：

```bash
docker compose run --rm freqtrade create-userdir --userdir user_data
docker compose run --rm freqtrade new-config --config user_data/config.json
```

本脚本会自动执行 `create-userdir`。`new-config` 是交互式命令，不适合一键部署，所以脚本会直接生成一个安全的 dry-run 默认配置。

如果 `user_data/config.json` 已经存在，脚本不会覆盖。

## 常用命令

```bash
cd /opt/freqtrade-cn
docker compose ps
docker compose logs -f
docker compose restart
docker compose down
```

更新代码并重启：

```bash
cd /opt/freqtrade-cn
git pull --ff-only
docker compose up -d --build
```

## 启用 Telegram 中文版

编辑：

```bash
nano /opt/freqtrade-cn/user_data/config.json
```

把 Telegram 配置改成：

```json
"telegram": {
    "enabled": true,
    "language": "zh",
    "token": "你的 Telegram Bot Token",
    "chat_id": "你的 Chat ID"
}
```

然后重启：

```bash
cd /opt/freqtrade-cn
docker compose restart
```

## 安全提醒

默认配置是 `dry_run: true`，不会真实下单。填入交易所 API key 并切换到实盘前，先确认策略、交易对、风控和止损。

不要把 API 端口直接暴露到公网。脚本默认只绑定 `127.0.0.1`，需要远程访问时建议通过 SSH 隧道或反向代理加认证。
