#!/usr/bin/env python3
"""
cleanup.py — Скрипт автоматизации очистки и ротации

Именно такие скрипты ты писал:
"Написание скриптов на Python для автоматизации рутинных задач
 (очистка, ротация, проверки)"

Что делает:
  1. Ротация логов — архивирует старые логи
  2. Очистка Docker — удаляет неиспользуемые образы/контейнеры
  3. Очистка старых бэкапов
  4. Проверка дискового пространства
  5. Отправка отчёта в Telegram

Использование:
  python3 cleanup.py                    # Все проверки
  python3 cleanup.py --dry-run          # Только показать, не удалять
  python3 cleanup.py --task docker      # Только очистка Docker

Cron: 0 3 * * * /opt/scripts/cleanup.py >> /var/log/cleanup.log 2>&1
"""

import os
import sys
import glob
import gzip
import shutil
import subprocess
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ─── Конфигурация ───
LOG_DIRS = ["/var/log/pharmacy", "/var/log/nginx"]
LOG_MAX_AGE_DAYS = 14
BACKUP_DIR = "/var/backups/pharmacy"
BACKUP_MAX_AGE_DAYS = 30
DISK_THRESHOLD_PERCENT = 85
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cleanup")


def send_telegram(message: str) -> None:
    """Отправка уведомления в Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not set, skipping notification")
        return
    try:
        import urllib.request
        import urllib.parse

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }).encode()
        urllib.request.urlopen(url, data, timeout=10)
        log.info("Telegram notification sent")
    except Exception as e:
        log.error(f"Failed to send Telegram: {e}")


def rotate_logs(dry_run: bool = False) -> dict:
    """Ротация и сжатие старых логов."""
    stats = {"compressed": 0, "deleted": 0, "freed_bytes": 0}
    cutoff = datetime.now() - timedelta(days=LOG_MAX_AGE_DAYS)

    for log_dir in LOG_DIRS:
        if not os.path.exists(log_dir):
            continue

        for log_file in glob.glob(f"{log_dir}/**/*.log", recursive=True):
            file_path = Path(log_file)
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

            if mtime < cutoff:
                size = file_path.stat().st_size
                if dry_run:
                    log.info(f"[DRY RUN] Would compress: {file_path} ({size} bytes)")
                else:
                    # Сжимаем в .gz
                    gz_path = f"{file_path}.gz"
                    with open(file_path, "rb") as f_in:
                        with gzip.open(gz_path, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.remove(file_path)
                    log.info(f"Compressed: {file_path} → {gz_path}")
                    stats["compressed"] += 1
                    stats["freed_bytes"] += size

        # Удаляем .gz файлы старше 2x MAX_AGE
        old_cutoff = datetime.now() - timedelta(days=LOG_MAX_AGE_DAYS * 2)
        for gz_file in glob.glob(f"{log_dir}/**/*.gz", recursive=True):
            gz_path = Path(gz_file)
            if datetime.fromtimestamp(gz_path.stat().st_mtime) < old_cutoff:
                size = gz_path.stat().st_size
                if dry_run:
                    log.info(f"[DRY RUN] Would delete: {gz_path}")
                else:
                    os.remove(gz_path)
                    log.info(f"Deleted old archive: {gz_path}")
                    stats["deleted"] += 1
                    stats["freed_bytes"] += size

    return stats


def cleanup_docker(dry_run: bool = False) -> dict:
    """Очистка Docker: dangling images, stopped containers, build cache."""
    stats = {"images_removed": 0, "space_freed": "0B"}

    if dry_run:
        # Показать что будет удалено
        result = subprocess.run(
            ["docker", "system", "df"],
            capture_output=True, text=True
        )
        log.info(f"[DRY RUN] Docker disk usage:\n{result.stdout}")
        return stats

    try:
        # Удаляем остановленные контейнеры
        subprocess.run(
            ["docker", "container", "prune", "-f"],
            capture_output=True, text=True
        )

        # Удаляем dangling images (без тега)
        result = subprocess.run(
            ["docker", "image", "prune", "-f"],
            capture_output=True, text=True
        )
        log.info(f"Docker image prune: {result.stdout.strip()}")

        # Удаляем build cache старше 7 дней
        subprocess.run(
            ["docker", "builder", "prune", "-f", "--filter", "until=168h"],
            capture_output=True, text=True
        )

        # Удаляем неиспользуемые volumes
        subprocess.run(
            ["docker", "volume", "prune", "-f"],
            capture_output=True, text=True
        )

        log.info("Docker cleanup completed")
    except FileNotFoundError:
        log.warning("Docker not found, skipping")

    return stats


def cleanup_backups(dry_run: bool = False) -> dict:
    """Удаление старых бэкапов БД."""
    stats = {"deleted": 0, "freed_bytes": 0}

    if not os.path.exists(BACKUP_DIR):
        log.info(f"Backup dir {BACKUP_DIR} not found, skipping")
        return stats

    cutoff = datetime.now() - timedelta(days=BACKUP_MAX_AGE_DAYS)

    for backup_file in sorted(glob.glob(f"{BACKUP_DIR}/*.sql.gz")):
        file_path = Path(backup_file)
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

        if mtime < cutoff:
            size = file_path.stat().st_size
            if dry_run:
                log.info(f"[DRY RUN] Would delete backup: {file_path} ({size} bytes)")
            else:
                os.remove(file_path)
                log.info(f"Deleted old backup: {file_path}")
                stats["deleted"] += 1
                stats["freed_bytes"] += size

    return stats


def check_disk_space() -> list[dict]:
    """Проверка дискового пространства."""
    alerts = []

    result = subprocess.run(
        ["df", "-h", "--output=target,pcent,avail"],
        capture_output=True, text=True
    )

    for line in result.stdout.strip().split("\n")[1:]:
        parts = line.split()
        if len(parts) >= 3:
            mount = parts[0]
            percent = int(parts[1].rstrip("%"))
            avail = parts[2]

            if percent >= DISK_THRESHOLD_PERCENT:
                alert = {
                    "mount": mount,
                    "used_percent": percent,
                    "available": avail,
                }
                alerts.append(alert)
                log.warning(
                    f"DISK ALERT: {mount} at {percent}% (available: {avail})"
                )

    return alerts


def format_bytes(size: int) -> str:
    """Человекочитаемый размер."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def main():
    parser = argparse.ArgumentParser(description="Pharmacy infra cleanup script")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument(
        "--task",
        choices=["logs", "docker", "backups", "disk", "all"],
        default="all",
        help="Which task to run",
    )
    args = parser.parse_args()

    log.info(f"{'='*50}")
    log.info(f"Cleanup started {'(DRY RUN)' if args.dry_run else ''}")
    log.info(f"{'='*50}")

    report_parts = []
    total_freed = 0

    tasks = args.task
    if tasks == "all":
        tasks_list = ["logs", "docker", "backups", "disk"]
    else:
        tasks_list = [tasks]

    if "logs" in tasks_list:
        log.info("── Log Rotation ──")
        stats = rotate_logs(args.dry_run)
        total_freed += stats["freed_bytes"]
        report_parts.append(
            f"Logs: {stats['compressed']} compressed, "
            f"{stats['deleted']} deleted, "
            f"{format_bytes(stats['freed_bytes'])} freed"
        )

    if "docker" in tasks_list:
        log.info("── Docker Cleanup ──")
        cleanup_docker(args.dry_run)
        report_parts.append("Docker: cleanup completed")

    if "backups" in tasks_list:
        log.info("── Backup Cleanup ──")
        stats = cleanup_backups(args.dry_run)
        total_freed += stats["freed_bytes"]
        report_parts.append(
            f"Backups: {stats['deleted']} deleted, "
            f"{format_bytes(stats['freed_bytes'])} freed"
        )

    if "disk" in tasks_list:
        log.info("── Disk Space Check ──")
        alerts = check_disk_space()
        if alerts:
            alert_text = "\n".join(
                f"  ⚠️ {a['mount']}: {a['used_percent']}% (avail: {a['available']})"
                for a in alerts
            )
            report_parts.append(f"Disk alerts:\n{alert_text}")

    # ─── Отчёт ───
    report = (
        f"<b>🧹 Cleanup Report</b>\n"
        f"<code>{datetime.now().strftime('%Y-%m-%d %H:%M')}</code>\n\n"
        + "\n".join(f"• {part}" for part in report_parts)
        + f"\n\n<b>Total freed: {format_bytes(total_freed)}</b>"
    )

    log.info(f"\n{report}")

    if not args.dry_run:
        send_telegram(report)

    log.info("Cleanup finished")


if __name__ == "__main__":
    main()
