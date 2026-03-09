#!/bin/bash
#
# Обновление Project Monitor Bot до последней версии
#
# Использование:
#   ./deploy/update.sh              — обновить и перезапустить
#   ./deploy/update.sh --no-restart — только обновить образ, без перезапуска
#   ./deploy/update.sh --dry-run    — показать изменения, ничего не менять
#

set -euo pipefail

# ─── Параметры ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NO_RESTART=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-restart) NO_RESTART=true; shift ;;
        --dry-run)    DRY_RUN=true;    shift ;;
        -h|--help)
            echo "Использование: $0 [--no-restart] [--dry-run]"
            echo "  --no-restart  Собрать образ, но не перезапускать контейнер"
            echo "  --dry-run     Только показать что изменилось, ничего не делать"
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

# ─── Определяем docker compose ──────────────────────────────────────────────

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
else
    fail "docker compose не найден"
fi

# ─── Переходим в директорию проекта ─────────────────────────────────────────

cd "$PROJECT_DIR"

if [ ! -f docker-compose.yml ]; then
    fail "docker-compose.yml не найден в $PROJECT_DIR"
fi

# ─── Бэкап данных перед обновлением ─────────────────────────────────────────

if [ -d data ] && [ "$(ls -A data 2>/dev/null)" ]; then
    BACKUP_NAME="data_backup_$(date +%Y%m%d_%H%M%S)"
    info "Создание резервной копии данных → backups/$BACKUP_NAME ..."
    mkdir -p backups
    cp -r data "backups/$BACKUP_NAME"
    ok "Бэкап создан"

    # Удаляем бэкапы старше 30 дней
    find backups -maxdepth 1 -name "data_backup_*" -mtime +30 -exec rm -rf {} + 2>/dev/null || true
fi

# ─── Получаем обновления из git ──────────────────────────────────────────────

info "Получение обновлений из git..."

BEFORE=$(git rev-parse HEAD)
git fetch origin
AFTER=$(git rev-parse origin/$(git rev-parse --abbrev-ref HEAD))

if [ "$BEFORE" = "$AFTER" ]; then
    ok "Код уже актуален ($(echo "$BEFORE" | cut -c1-8))"
    if [ "$DRY_RUN" = true ]; then
        exit 0
    fi
else
    CHANGES=$(git log --oneline "$BEFORE..$AFTER" 2>/dev/null || echo "(не удалось получить лог)")
    info "Новые коммиты:"
    echo "$CHANGES"
    echo ""

    if [ "$DRY_RUN" = true ]; then
        info "Режим --dry-run: изменения не применяются"
        exit 0
    fi

    git pull --ff-only || fail "Не удалось обновить. Проверьте наличие локальных изменений (git status)."
    ok "Код обновлён до $(echo "$AFTER" | cut -c1-8)"
fi

# ─── Пересборка образа ──────────────────────────────────────────────────────

info "Пересборка Docker-образа..."
$COMPOSE_CMD build
ok "Образ пересобран"

# ─── Перезапуск ──────────────────────────────────────────────────────────────

if [ "$NO_RESTART" = true ]; then
    warn "Флаг --no-restart: контейнер НЕ перезапущен"
    info "Перезапустите вручную: $COMPOSE_CMD up -d"
else
    info "Перезапуск контейнера..."
    $COMPOSE_CMD up -d
    ok "Контейнер перезапущен"

    sleep 3

    if $COMPOSE_CMD ps | grep -q "running"; then
        ok "Бот работает"
    else
        warn "Контейнер не в статусе running. Проверьте логи:"
        echo "  $COMPOSE_CMD logs --tail 30"
    fi
fi

# ─── Очистка старых образов ──────────────────────────────────────────────────

DANGLING=$(docker images -f "dangling=true" -q 2>/dev/null)
if [ -n "$DANGLING" ]; then
    info "Удаление неиспользуемых образов..."
    docker image prune -f >/dev/null 2>&1 || true
fi

echo ""
ok "Обновление завершено!"
echo ""
echo "Полезные команды:"
echo "  $COMPOSE_CMD logs -f        — следить за логами"
echo "  $COMPOSE_CMD ps             — статус контейнера"
echo "  $COMPOSE_CMD restart bot    — перезапуск"
echo ""
