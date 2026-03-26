#!/usr/bin/env python3
"""
log_rotate.py — Ротация логов и бэкап БД
=========================================

Что делает:
  1. Ротирует логи приложения (сжимает, удаляет старые)
  2. Создаёт pg_dump бэкап PostgreSQL
  3. Загружает бэкап в S3 (если настроен)
  4. Алертит в Telegram при ошибках

Cron:
  # Ежедневно в 2:00
  0 2 * * * /usr/bin/python3 /opt/scripts/log_rotate.py
  # Бэкап БД каждые 6 часов
  0 */6 * * * /usr/bin/python3 /opt/scripts/log_rotate.py --backup-only
"""

import subprocess
import gzip
import shutil
import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ─── Конфиг ───
LOG_DIRS = [
    "/var/log/pharmacy",
    "/var/log/nginx",
]
LOG_RETENTION_DAYS = 14
BACKUP_DIR = "/data/backups/postgres"
BACKUP_RETENTION_DAYS = 7
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "pharmacy_db")
DB_USER = os.getenv("DB_USER", "pharmacy")
S3_BUCKET = os.getenv("S3_BACKUP_BUCKET", "")


def rotate_logs(log_dir: str, retention_days: int) -> dict:
    """Ротация логов: сжимаем текущие, удаляем старые."""
    stats = {"compressed": 0, "deleted": 0, "errors": 0}
    log_path = Path(log_dir)

    if not log_path.exists():
        logger.warning(f"Директория не найдена: {log_dir}")
        return stats

    cutoff = datetime.now() - timedelta(days=retention_days)

    for log_file in log_path.glob("*.log"):
        try:
            # Сжимаем .log файлы размером > 1MB
            if log_file.stat().st_size > 1_000_000:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                gz_name = f"{log_file.stem}_{timestamp}.log.gz"
                gz_path = log_path / gz_name

                with open(log_file, "rb") as f_in:
                    with gzip.open(gz_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)

                # Очищаем оригинал (не удаляем — приложение пишет в него)
                with open(log_file, "w") as f:
                    f.truncate(0)

                logger.info(f"Сжат: {log_file.name} → {gz_name}")
                stats["compressed"] += 1

        except Exception as e:
            logger.error(f"Ошибка сжатия {log_file}: {e}")
            stats["errors"] += 1

    # Удаляем старые .gz файлы
    for gz_file in log_path.glob("*.gz"):
        try:
            mtime = datetime.fromtimestamp(gz_file.stat().st_mtime)
            if mtime < cutoff:
                gz_file.unlink()
                logger.info(f"Удалён (старше {retention_days}д): {gz_file.name}")
                stats["deleted"] += 1
        except Exception as e:
            logger.error(f"Ошибка удаления {gz_file}: {e}")
            stats["errors"] += 1

    return stats


def backup_postgres() -> str | None:
    """Создаёт pg_dump бэкап PostgreSQL."""
    backup_path = Path(BACKUP_DIR)
    backup_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dump_file = backup_path / f"pharmacy_{timestamp}.sql.gz"

    logger.info(f"Создаю бэкап: {DB_HOST}/{DB_NAME}")

    try:
        # pg_dump → gzip — стримим напрямую без промежуточного файла
        pg_dump = subprocess.Popen(
            ["pg_dump", "-h", DB_HOST, "-U", DB_USER, "-d", DB_NAME, "--no-owner"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PGPASSWORD": os.getenv("DB_PASSWORD", "pharmacy_pass")}
        )

        with gzip.open(dump_file, "wb") as f_out:
            while True:
                chunk = pg_dump.stdout.read(8192)
                if not chunk:
                    break
                f_out.write(chunk)

        pg_dump.wait()
        if pg_dump.returncode != 0:
            stderr = pg_dump.stderr.read().decode()
            raise Exception(f"pg_dump failed: {stderr}")

        size_mb = dump_file.stat().st_size / (1024 * 1024)
        logger.info(f"Бэкап создан: {dump_file} ({size_mb:.1f} MB)")
        return str(dump_file)

    except Exception as e:
        logger.error(f"Ошибка бэкапа: {e}")
        return None


def cleanup_old_backups(retention_days: int) -> int:
    """Удаляет бэкапы старше N дней."""
    backup_path = Path(BACKUP_DIR)
    if not backup_path.exists():
        return 0

    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0

    for f in backup_path.glob("pharmacy_*.sql.gz"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            f.unlink()
            logger.info(f"Старый бэкап удалён: {f.name}")
            removed += 1

    return removed


def upload_to_s3(file_path: str) -> bool:
    """Загружает бэкап в S3."""
    if not S3_BUCKET:
        logger.debug("S3 не настроен")
        return False

    try:
        key = f"backups/postgres/{Path(file_path).name}"
        result = subprocess.run(
            ["aws", "s3", "cp", file_path, f"s3://{S3_BUCKET}/{key}"],
            capture_output=True, text=True, check=True
        )
        logger.info(f"Загружен в S3: s3://{S3_BUCKET}/{key}")
        return True
    except Exception as e:
        logger.error(f"Ошибка S3: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Ротация логов и бэкап БД")
    parser.add_argument("--backup-only", action="store_true", help="Только бэкап БД")
    parser.add_argument("--logs-only", action="store_true", help="Только ротация логов")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info(f"Maintenance job — {datetime.now().isoformat()}")
    logger.info("=" * 50)

    # ─── Ротация логов ───
    if not args.backup_only:
        for log_dir in LOG_DIRS:
            stats = rotate_logs(log_dir, LOG_RETENTION_DAYS)
            logger.info(f"{log_dir}: сжато={stats['compressed']}, "
                       f"удалено={stats['deleted']}, ошибок={stats['errors']}")

    # ─── Бэкап БД ───
    if not args.logs_only:
        dump_path = backup_postgres()
        if dump_path:
            upload_to_s3(dump_path)
        cleanup_old_backups(BACKUP_RETENTION_DAYS)

    logger.info("Готово!")


if __name__ == "__main__":
    main()
