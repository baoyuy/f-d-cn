# Ubuntu/Debian 一键部署中文定制版

本文档适用于本仓库的中文定制版 Freqtrade。脚本会使用 Docker Compose 部署，适合全新 Ubuntu/Debian 服务器，也适合已经使用过一段时间、但没有在目标目录部署过本项目的服务器。

!!! Warning "风险说明"
    本仓库是基于 Freqtrade 的非官方中文定制版，不代表 Freqtrade 官方团队。请保留原项目许可证和版权声明，并遵守 GPL-3.0 license、交易所规则和当地法律法规。

    默认配置为 `dry_run: true`，不会真实下单。切换实盘前，请先确认策略、交易对、API key 权限、止损、仓位和服务器安全。

## 一键部署命令

公开仓库可以直接执行：

```bash
curl -fsSL https://raw.githubusercontent.com/baoyuy/f-d-cn/main/scripts/deploy_ubuntu_docker.sh \
  | sudo env REPO_URL="https://github.com/baoyuy/f-d-cn.git" BRANCH="main" bash
```

这同一条命令同时负责首次部署、后续更新和配置修改后的重启。已经部署过时，重复执行它会自动判断状态：代码有更新才拉取并重建 Docker 镜像；代码没变化时只快速重启现有容器。已有配置文件会保留，不会覆盖。

这个命令会自动完成：

- 安装基础工具：`curl`、`git`、`gnupg` 等。
- 安装 Docker Engine 和 Docker Compose 插件。
- 拉取 `https://github.com/baoyuy/f-d-cn.git` 的 `main` 分支。
- 构建本地 Docker 镜像。
- 执行官方初始化命令 `freqtrade create-userdir --userdir user_data`。
- 生成非交互的默认 `user_data/config.json`。
- 启动 `freqtrade-cn` 容器。

已经部署过的服务器会跳过已安装的基础工具和 Docker。没有代码更新时，也会跳过镜像构建，只重启现有容器。

## 一键启用 Telegram 中文版

如果你已经拿到 Telegram Bot Token 和 chat id，可以在部署时直接传入环境变量：

```bash
curl -fsSL https://raw.githubusercontent.com/baoyuy/f-d-cn/main/scripts/deploy_ubuntu_docker.sh \
  | sudo env \
      REPO_URL="https://github.com/baoyuy/f-d-cn.git" \
      BRANCH="main" \
      TELEGRAM_ENABLED="true" \
      TELEGRAM_TOKEN="机器人ID:密钥" \
      TELEGRAM_CHAT_ID="你的 Chat ID" \
      bash
```

脚本会自动写入 `/opt/freqtrade-cn/user_data/config.json` 并校验：

- `TELEGRAM_TOKEN` 必须是完整格式：`机器人ID:密钥`。
- `TELEGRAM_CHAT_ID` 必须是聊天 ID，例如个人私聊 ID，不是 bot id。
- Telegram 语言固定写入 `zh`，除非显式传入 `TELEGRAM_LANGUAGE="en"`。

## 私有仓库部署

如果仓库是私有仓库，`raw.githubusercontent.com` 不能匿名下载脚本。先给服务器配置能访问该仓库的 GitHub SSH key 或 deploy key，然后执行：

```bash
bash -c 'tmp="$(mktemp -d)" && GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new" git clone --depth 1 --branch main git@github.com:baoyuy/f-d-cn.git "$tmp" && sudo env SSH_AUTH_SOCK="${SSH_AUTH_SOCK:-}" GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new" REPO_URL="git@github.com:baoyuy/f-d-cn.git" BRANCH="main" bash "$tmp/scripts/deploy_ubuntu_docker.sh"'
```

这条命令会把当前 SSH agent 传给 `sudo` 后的部署过程。若服务器没有使用 SSH agent，请给 root 用户单独配置只读 deploy key，或先把仓库改为公开后使用公开仓库部署命令。

不要把 GitHub token 直接写进公开文档、截图或服务器命令历史。必须用 token 时，建议使用最小权限、短有效期的 token，并在部署后立即轮换。

## 默认部署结果

- 部署目录：`/opt/freqtrade-cn`
- Docker 镜像：`freqtrade-cn:local`
- 容器名：`freqtrade-cn`
- 配置文件：`/opt/freqtrade-cn/user_data/config.json`
- 默认交易模式：`dry_run: true`
- 默认交易所：`binance`
- 默认交易对：`BTC/USDT`、`ETH/USDT`
- 默认策略：`CnTrendPullbackStrategy`
- Telegram 默认关闭，但配置里已写入 `"language": "zh"`
- API 默认只映射到宿主机本地地址：`127.0.0.1:8080`

## 自定义部署参数

需要换目录、端口、策略或镜像名时，可以通过环境变量覆盖：

```bash
curl -fsSL https://raw.githubusercontent.com/baoyuy/f-d-cn/main/scripts/deploy_ubuntu_docker.sh \
  | sudo env \
      REPO_URL="https://github.com/baoyuy/f-d-cn.git" \
      BRANCH="main" \
      INSTALL_DIR="/opt/freqtrade-cn" \
      API_PORT="8080" \
      STRATEGY="CnTrendPullbackStrategy" \
      IMAGE_NAME="freqtrade-cn:local" \
      bash
```

参数说明：

- `REPO_URL`：源码仓库地址。部署中文定制版时应指向本仓库，不要填官方原仓库。
- `BRANCH`：部署分支，默认 `main`。
- `INSTALL_DIR`：部署目录，默认 `/opt/freqtrade-cn`。
- `API_PORT`：宿主机本地 API 端口，默认 `8080`。
- `STRATEGY`：启动策略，默认 `CnTrendPullbackStrategy`。
- `IMAGE_NAME`：本地 Docker 镜像名，默认 `freqtrade-cn:local`。
- `TELEGRAM_ENABLED`：是否启用 Telegram，传 `true` 会开启。
- `TELEGRAM_TOKEN`：完整 Telegram Bot Token，格式必须是 `机器人ID:密钥`。
- `TELEGRAM_CHAT_ID`：Telegram chat id。
- `TELEGRAM_LANGUAGE`：Telegram 语言，默认 `zh`。

## 初始化行为

官方 Docker 初始化通常需要手动执行：

```bash
docker compose run --rm freqtrade create-userdir --userdir user_data
docker compose run --rm freqtrade new-config --config user_data/config.json
```

一键部署脚本会自动执行 `create-userdir`。`new-config` 是交互式命令，不适合无人值守部署，所以脚本会生成一个默认配置文件。

如果 `/opt/freqtrade-cn/user_data/config.json` 已经存在，脚本会保留原配置，不会覆盖。

## 新手配置向导

部署完成后，可以使用交互式向导调整常用配置：

```bash
cd /opt/freqtrade-cn
python3 scripts/configure_beginner.py --config user_data/config.json
docker compose restart freqtrade
```

向导会引导设置策略名、K 线周期、每笔投入金额、交易对和 Telegram 中文机器人。保存前会自动备份原 `config.json`。默认保持 `dry_run: true`，除非你输入明确的实盘风险确认。

如果只想写入安全默认值，不进入交互提问，可以执行：

```bash
cd /opt/freqtrade-cn
python3 scripts/configure_beginner.py --config user_data/config.json --yes
```

## 更新和重启

更新代码、重建镜像和重启容器不需要另一套命令。改完 `config.json` 后，也继续执行首次部署时的同一条一键部署命令：

```bash
curl -fsSL https://raw.githubusercontent.com/baoyuy/f-d-cn/main/scripts/deploy_ubuntu_docker.sh \
  | sudo env REPO_URL="https://github.com/baoyuy/f-d-cn.git" BRANCH="main" bash
```

脚本会自动判断 `/opt/freqtrade-cn` 是否已经是 Git 仓库：

- 首次部署：克隆仓库、初始化 `user_data`、生成默认配置、启动容器。
- 再次执行且代码有更新：拉取最新代码、保留已有配置、重建镜像、重启容器。
- 再次执行但代码没变化：跳过基础工具安装、跳过初始化、跳过镜像构建，只快速重启现有容器。

## 常用维护命令

查看运行状态：

```bash
cd /opt/freqtrade-cn
docker compose ps
```

查看日志：

```bash
cd /opt/freqtrade-cn
docker compose logs -f
```

重启机器人：

```bash
cd /opt/freqtrade-cn
docker compose restart
```

停止机器人：

```bash
cd /opt/freqtrade-cn
docker compose down
```

## 启用 Telegram 中文版

编辑配置文件：

```bash
nano /opt/freqtrade-cn/user_data/config.json
```

把 Telegram 配置改成：

```json
"telegram": {
    "enabled": true,
    "language": "zh",
    "token": "你的完整 Telegram Bot Token，格式是 机器人ID:密钥",
    "chat_id": "你的 Chat ID"
}
```

`token` 必须填写完整字符串，例如 `123456789:AA...`。冒号前面的数字只是 bot id，不是 `chat_id`；`chat_id` 需要从 `getUpdates` 里获取。

保存后继续执行同一条一键部署命令即可。代码没变化时，脚本只会快速重启现有容器。

也可以在服务器上手动重启：

```bash
cd /opt/freqtrade-cn
docker compose restart
```

## 安全建议

- 先使用 `dry_run: true` 跑通流程，再考虑实盘。
- 交易所 API key 不要开启提现权限。
- 不要把 `/opt/freqtrade-cn/user_data/config.json` 上传到公开仓库。
- 不要把 API 端口直接暴露到公网。默认只绑定 `127.0.0.1`，远程访问建议使用 SSH 隧道、VPN 或带认证的反向代理。
- 实盘前先阅读原项目文档：[Freqtrade Documentation](https://www.freqtrade.io)。
