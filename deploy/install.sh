#!/bin/bash
#
# Первоначальная установка Project Monitor Bot (Docker)
#
# Использование:
#   curl -sSL https://raw.githubusercontent.com/chastnik/mm_project_monitor_bot/main/deploy/install.sh | bash
#   или:
#   ./deploy/install.sh [--dir /opt/project-monitor-bot]
#

set -euo pipefail

# ─── Параметры ──────────────────────────────────────────────────────────────

REPO_URL="https://github.com/chastnik/mm_project_monitor_bot.git"
DEFAULT_INSTALL_DIR="/opt/project-monitor-bot"
BRANCH="main"

# ─── Разбор аргументов ──────────────────────────────────────────────────────

INSTALL_DIR="$DEFAULT_INSTALL_DIR"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)  INSTALL_DIR="$2"; shift 2 ;;
        --branch) BRANCH="$2"; shift 2 ;;
        -h|--help)
            echo "Использование: $0 [--dir <путь>] [--branch <ветка>]"
            echo "  --dir     Директория установки (по умолчанию: $DEFAULT_INSTALL_DIR)"
            echo "  --branch  Git-ветка (по умолчанию: main)"
            exit 0 ;;
        *) echo "Неизвестный аргумент: $1"; exit 1 ;;
    esac
done

# ─── Цвета ──────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# ─── Проверка зависимостей ──────────────────────────────────────────────────

info "Проверка зависимостей..."

command -v git    >/dev/null 2>&1 || fail "git не установлен"
command -v docker >/dev/null 2>&1 || fail "docker не установлен. Установите: https://docs.docker.com/engine/install/"

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
else
    fail "docker compose не найден. Установите Docker Compose v2."
fi

ok "git, docker, $COMPOSE_CMD"

# ─── Клонирование репозитория ────────────────────────────────────────────────

if [ -d "$INSTALL_DIR/.git" ]; then
    warn "Директория $INSTALL_DIR уже содержит репозиторий"
    info "Если хотите переустановить, удалите её: rm -rf $INSTALL_DIR"
    exit 1
fi

info "Клонирование репозитория в $INSTALL_DIR ..."
sudo mkdir -p "$(dirname "$INSTALL_DIR")"
sudo git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
sudo chown -R "$(id -u):$(id -g)" "$INSTALL_DIR"

ok "Репозиторий склонирован"

# ─── Создание директории данных ──────────────────────────────────────────────

mkdir -p "$INSTALL_DIR/data"
ok "Директория данных: $INSTALL_DIR/data"

# ─── Создание .env ───────────────────────────────────────────────────────────

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/env.example" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    warn "Создан файл .env из шаблона — ОБЯЗАТЕЛЬНО отредактируйте его!"
else
    info "Файл .env уже существует, пропускаем"
fi

# ─── Сборка образа ──────────────────────────────────────────────────────────

info "Сборка Docker-образа..."
cd "$INSTALL_DIR"
$COMPOSE_CMD build
ok "Образ собран"

# ─── Готово ──────────────────────────────────────────────────────────────────

echo ""
echo "========================================"
ok "Установка завершена!"
echo "========================================"
echo ""
echo "Следующие шаги:"
echo ""
echo "  1. Отредактируйте конфигурацию:"
echo "     nano $INSTALL_DIR/.env"
echo ""
echo "  2. Запустите бота:"
echo "     cd $INSTALL_DIR && $COMPOSE_CMD up -d"
echo ""
echo "  3. Проверьте статус:"
echo "     $COMPOSE_CMD ps"
echo "     $COMPOSE_CMD logs -f"
echo ""
