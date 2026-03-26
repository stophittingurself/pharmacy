#!/usr/bin/env python3
"""
healthcheck.py — Проверка здоровья сервисов + Telegram-алерты

Зачем:
  Дополнительный уровень мониторинга поверх Prometheus.
  Проверяет доступность endpoint'ов, статус Kubernetes подов,
  PostgreSQL и шлёт алерт в Telegram если что-то сломалось.

Использование:
  python3 healthcheck.py                    # однократная проверка
  python3 healthcheck.py --loop --interval 60   # проверка каждые 60с

В резюме:
  "Настроил Prometheus + Grafana с Telegram-алертингом,
   что снизило число незамеченных инцидентов"
"""

import os
import sys
import time
import json
import argparse
import subprocess
from urllib import request, error
from datetime import datetime
from typing import Optional


# ─── Конфигурация ───
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

CHECKS = [
    {
        "name": "Backend API",
        "url": "http://localhost:8000/api/health",
        "expected_status": 200,
    },
    {
        "name": "Frontend",
        "url": "http://localhost:80",
        "expected_status": 200,
    },
    {
        "name": "Prometheus",
        "url": "http://localhost:9090/-/healthy",
        "expected_status": 200,
    },
    {
        "name": "Grafana",
        "url": "http://localhost:3000/api/health",
        "expected_status": 200,
    },
]


def check_http(name: str, url: str, expected_status: int, timeout: int = 5) -> dict:
    """Проверить HTTP endpoint."""
    result = {"name": name, "url": url, "ok": False, "detail": ""}
    try:
        req = request.Request(url, method="GET")
        resp = request.urlopen(req, timeout=timeout)
        if resp.status == expected_status:
            result["ok"] = True
            result["detail"] = f"HTTP {resp.status}"
        else:
            result["detail"] = f"HTTP {resp.status} (expected {expected_status})"
    except error.URLError as e:
        result["detail"] = f"Connection failed: {e.reason}"
    except Exception as e:
        result["detail"] = str(e)
    return result


def check_postgres(host: str = "localhost", port: int = 5432) -> dict:
    """Проверить доступность PostgreSQL."""
    result = {"name": "PostgreSQL", "ok": False, "detail": ""}
    try:
        proc = subprocess.run(
            ["pg_isready", "-h", host, "-p", str(port)],
            capture_output=True, text=True, timeout=5
        )
        result["ok"] = proc.returncode == 0
        result["detail"] = proc.stdout.strip() or proc.stderr.strip()
    except FileNotFoundError:
        result["detail"] = "pg_isready not installed"
    except Exception as e:
        result["detail"] = str(e)
    return result


def check_k8s_pods(namespace: str = "pharmacy-prod") -> dict:
    """Проверить статус подов в Kubernetes."""
    result = {"name": f"K8s Pods ({namespace})", "ok": False, "detail": ""}
    try:
        proc = subprocess.run(
            ["kubectl", "get", "pods", "-n", namespace,
             "-o", "json", "--field-selector=status.phase!=Running,status.phase!=Succeeded"],
            capture_output=True, text=True, timeout=10
        )
        if proc.returncode != 0:
            result["detail"] = f"kubectl failed: {proc.stderr.strip()}"
            return result

        data = json.loads(proc.stdout)
        unhealthy = data.get("items", [])

        if not unhealthy:
            result["ok"] = True
            result["detail"] = "All pods healthy"
        else:
            names = [p["metadata"]["name"] for p in unhealthy]
            result["detail"] = f"Unhealthy pods: {', '.join(names)}"
    except FileNotFoundError:
        result["detail"] = "kubectl not installed"
    except Exception as e:
        result["detail"] = str(e)
    return result


def send_telegram(message: str):
    """Отправить алерт в Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }).encode("utf-8")

    try:
        req = request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        request.urlopen(req, timeout=10)
        print("[INFO] Telegram alert sent")
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram alert: {e}")


def run_checks() -> list[dict]:
    """Запустить все проверки."""
    results = []

    # HTTP checks
    for check in CHECKS:
        res = check_http(check["name"], check["url"], check["expected_status"])
        results.append(res)

    # PostgreSQL
    results.append(check_postgres())

    # K8s pods (если kubectl доступен)
    results.append(check_k8s_pods())

    return results


def format_report(results: list[dict]) -> str:
    """Форматировать отчёт."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"🏥 <b>Pharmacy Health Check</b>", f"📅 {now}", ""]

    failed = []
    for r in results:
        icon = "✅" if r["ok"] else "❌"
        lines.append(f"{icon} <b>{r['name']}</b>: {r['detail']}")
        if not r["ok"]:
            failed.append(r)

    total = len(results)
    ok_count = total - len(failed)
    lines.insert(2, f"Status: {ok_count}/{total} checks passed")

    return "\n".join(lines), failed


def main():
    parser = argparse.ArgumentParser(description="Health check + Telegram alerting")
    parser.add_argument("--loop", action="store_true", help="Запустить в цикле")
    parser.add_argument("--interval", type=int, default=60, help="Интервал проверки (сек)")
    parser.add_argument("--alert-only", action="store_true",
                        help="Отправлять Telegram только при ошибках")
    args = parser.parse_args()

    while True:
        results = run_checks()
        report, failed = format_report(results)

        # Вывод в консоль
        print(report.replace("<b>", "").replace("</b>", ""))
        print("-" * 50)

        # Telegram
        if failed:
            send_telegram(report)
        elif not args.alert_only:
            send_telegram(report)

        if not args.loop:
            sys.exit(1 if failed else 0)

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
