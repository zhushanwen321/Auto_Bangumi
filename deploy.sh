#!/usr/bin/env bash
#
# AutoBangumi 部署脚本
# 从 ghcr.io 拉取指定版本的 Docker 镜像并启动服务
#
# 用法:
#   ./deploy.sh                     # 默认部署 latest
#   ./deploy.sh 3.2.0-beta.4        # 部署指定版本
#   ./deploy.sh dev-latest          # 部署开发版
#   ./deploy.sh --uninstall         # 停止并删除容器和数据
#

set -euo pipefail

# ── 配置 ──────────────────────────────────────
IMAGE="ghcr.io/estrellaxd/auto_bangumi"
CONTAINER_NAME="AutoBangumi"
HOST_PORT=7892
CONFIG_DIR="./config"
DATA_DIR="./data"
TIMEZONE="Asia/Shanghai"
DNS="223.5.5.5"
# ──────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

check_docker() {
    if ! command -v docker &>/dev/null; then
        error "未检测到 docker，请先安装 Docker"
    fi
    if ! docker info &>/dev/null; then
        error "Docker 守护进程未运行，或当前用户无权限。请检查 docker 服务状态"
    fi
}

stop_existing() {
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        info "停止并删除已有容器 ${CONTAINER_NAME}..."
        docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
        docker rm "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    fi
}

deploy() {
    local tag="$1"
    local full_image="${IMAGE}:${tag}"

    info "拉取镜像 ${full_image}..."
    if ! docker pull "${full_image}"; then
        error "镜像拉取失败，请检查 tag 是否正确、网络是否可达 ghcr.io"
    fi

    mkdir -p "${CONFIG_DIR}" "${DATA_DIR}"

    info "启动容器 ${CONTAINER_NAME}..."
    docker run -d \
        --name "${CONTAINER_NAME}" \
        --network bridge \
        -p "${HOST_PORT}:7892" \
        -v "$(pwd)/${CONFIG_DIR}:/app/config" \
        -v "$(pwd)/${DATA_DIR}:/app/data" \
        -e "TZ=${TIMEZONE}" \
        -e "PUID=$(id -u)" \
        -e "PGID=$(id -g)" \
        -e "UMASK=022" \
        --dns "${DNS}" \
        --restart unless-stopped \
        "${full_image}"

    echo ""
    info "部署完成!"
    info "  镜像:  ${full_image}"
    info "  地址:  http://localhost:${HOST_PORT}"
    info "  配置:  $(pwd)/${CONFIG_DIR}"
    info "  数据:  $(pwd)/${DATA_DIR}"
    echo ""
    info "常用命令:"
    info "  查看日志:  docker logs -f ${CONTAINER_NAME}"
    info "  停止服务:  docker stop ${CONTAINER_NAME}"
    info "  重新部署:  $0 ${tag}"
}

uninstall() {
    warn "将删除容器 ${CONTAINER_NAME} 及其配置/数据目录"
    read -rp "确认继续? [y/N] " confirm
    if [[ "${confirm,,}" != "y" ]]; then
        info "已取消"
        exit 0
    fi

    stop_existing
    rm -rf "${CONFIG_DIR}" "${DATA_DIR}"
    info "已卸载"
}

list_tags() {
    info "正在查询可用 tag（可能需要几秒）..."
    local token
    token=$(curl -s "https://ghcr.io/token?scope=repository:estrellaxd/auto_bangumi:pull" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
    if [[ -z "$token" ]]; then
        error "获取 GHCR token 失败"
    fi
    local tags
    tags=$(curl -s -H "Authorization: Bearer ${token}" \
        "https://ghcr.io/v2/estrellaxd/auto_bangumi/tags/list" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in sorted(data.get('tags', [])):
    print(t)
" 2>/dev/null)
    if [[ -z "$tags" ]]; then
        warn "未查询到 tag，可能网络不通或仓库地址有变"
    else
        echo "$tags"
    fi
}

usage() {
    cat <<'EOF'
AutoBangumi 部署脚本

用法:
  ./deploy.sh [选项] [TAG]

选项:
  -l, --list-tags    列出 GHCR 上所有可用 tag
  -u, --uninstall    停止容器并删除配置/数据
  -h, --help         显示此帮助信息

TAG:
  要部署的镜像版本，默认为 "latest"
  示例: latest, dev-latest, 3.2.0-beta.4

示例:
  ./deploy.sh                     部署最新稳定版
  ./deploy.sh dev-latest          部署最新开发版
  ./deploy.sh 3.2.0-beta.4        部署指定版本
  ./deploy.sh --list-tags         查看所有可用版本
EOF
}

# ── 主流程 ────────────────────────────────────
main() {
    check_docker

    case "${1:-}" in
        -h|--help)
            usage
            ;;
        -l|--list-tags)
            list_tags
            ;;
        -u|--uninstall)
            uninstall
            ;;
        -*)
            error "未知选项: $1。使用 -h 查看帮助"
            ;;
        "")
            stop_existing
            deploy "latest"
            ;;
        *)
            stop_existing
            deploy "$1"
            ;;
    esac
}

main "$@"
