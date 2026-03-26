#!/usr/bin/env python3
"""
cleanup_images.py — Очистка старых Docker-образов

Зачем:
  Harbor / local Docker накапливает десятки образов при каждом пуше.
  Этот скрипт оставляет только N последних тегов для каждого репозитория,
  остальные удаляет. Запускай через cron или GitLab CI schedule.

Использование:
  python3 cleanup_images.py --keep 5 --dry-run
  python3 cleanup_images.py --keep 5              # реальное удаление

В резюме:
  "Написание скриптов на Python для автоматизации рутинных задач
   (очистка, ротация, проверки)"
"""

import subprocess
import argparse
import json
import sys
from datetime import datetime


def get_docker_images(repository: str) -> list[dict]:
    """Получить список образов из Docker."""
    result = subprocess.run(
        ["docker", "images", repository, "--format", "{{json .}}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[ERROR] docker images failed: {result.stderr}")
        sys.exit(1)

    images = []
    for line in result.stdout.strip().split("\n"):
        if line:
            img = json.loads(line)
            images.append(img)
    return images


def parse_created(created_str: str) -> datetime:
    """Парсим дату создания образа."""
    # Docker выдаёт разные форматы, упрощаем
    try:
        return datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return datetime.min


def cleanup_images(repository: str, keep: int, dry_run: bool):
    """Удалить старые образы, оставив keep штук."""
    images = get_docker_images(repository)

    if not images:
        print(f"[INFO] Нет образов для {repository}")
        return

    # Фильтруем <none> теги
    tagged = [img for img in images if img.get("Tag", "<none>") != "<none>"]
    untagged = [img for img in images if img.get("Tag", "<none>") == "<none>"]

    # Сортируем по дате создания (новые первые)
    tagged.sort(key=lambda x: x.get("CreatedAt", ""), reverse=True)

    to_keep = tagged[:keep]
    to_delete = tagged[keep:] + untagged

    print(f"\n{'='*60}")
    print(f"Repository: {repository}")
    print(f"Total images: {len(images)} (tagged: {len(tagged)}, untagged: {len(untagged)})")
    print(f"Keeping: {keep} | Deleting: {len(to_delete)}")
    print(f"{'='*60}")

    if to_keep:
        print("\n[KEEP]")
        for img in to_keep:
            print(f"  ✓ {img['Repository']}:{img['Tag']}  ({img.get('Size', '?')})")

    if to_delete:
        print(f"\n[{'DRY-RUN DELETE' if dry_run else 'DELETE'}]")
        for img in to_delete:
            tag = img.get("Tag", "<none>")
            image_id = img.get("ID", "")
            ref = f"{img['Repository']}:{tag}" if tag != "<none>" else image_id

            if dry_run:
                print(f"  ✗ {ref}  ({img.get('Size', '?')}) — would be deleted")
            else:
                print(f"  ✗ Deleting {ref}...", end=" ")
                result = subprocess.run(
                    ["docker", "rmi", ref],
                    capture_output=True, text=True
                )
                print("OK" if result.returncode == 0 else f"FAILED: {result.stderr.strip()}")
    else:
        print("\n[INFO] Нечего удалять.")


def cleanup_dangling(dry_run: bool):
    """Удалить dangling образы (<none>:<none>)."""
    result = subprocess.run(
        ["docker", "images", "-f", "dangling=true", "-q"],
        capture_output=True, text=True
    )
    dangling = result.stdout.strip().split("\n")
    dangling = [d for d in dangling if d]

    if not dangling:
        print("\n[INFO] Нет dangling образов")
        return

    print(f"\n[DANGLING] Found {len(dangling)} dangling images")
    if dry_run:
        print("  Would delete all dangling images")
    else:
        subprocess.run(["docker", "image", "prune", "-f"])
        print("  Dangling images removed")


def main():
    parser = argparse.ArgumentParser(description="Очистка старых Docker-образов")
    parser.add_argument("--repo", default="harbor.pharmacy.local/pharmacy/backend",
                        help="Docker репозиторий")
    parser.add_argument("--keep", type=int, default=5,
                        help="Сколько последних тегов оставить")
    parser.add_argument("--dry-run", action="store_true",
                        help="Только показать, что будет удалено")
    parser.add_argument("--all-repos", action="store_true",
                        help="Очистить все pharmacy репозитории")
    args = parser.parse_args()

    repos = [args.repo]
    if args.all_repos:
        repos = [
            "harbor.pharmacy.local/pharmacy/backend",
            "harbor.pharmacy.local/pharmacy/frontend",
        ]

    for repo in repos:
        cleanup_images(repo, args.keep, args.dry_run)

    cleanup_dangling(args.dry_run)

    if args.dry_run:
        print("\n⚠ Это был dry-run. Для реального удаления уберите --dry-run")


if __name__ == "__main__":
    main()
