# Pharmacy Chain Infrastructure

Учебный DevOps-проект — полная инфраструктура для аптечной сети.
Стек: Docker, Kubernetes, GitLab CI/CD, Harbor, Prometheus, Grafana, Ansible, Terraform, Linux, Bash, Python.

---

## Структура проекта

```
pharmacy-infra/
├── backend/                    # FastAPI (Python) — API аптечной сети
│   ├── app/
│   │   ├── main.py             # Endpoints: /api/health, /api/medicines, /api/pharmacies
│   │   ├── models.py           # SQLAlchemy модели: Medicine, Pharmacy
│   │   └── database.py         # Подключение к PostgreSQL
│   ├── Dockerfile              # Мультистейдж билд (builder → runtime)
│   └── requirements.txt
│
├── frontend/                   # Nginx + HTML — панель управления
│   ├── index.html              # Dashboard с таблицами, формами, статистикой
│   ├── nginx.conf              # Reverse proxy: /api/ → backend:8000
│   └── Dockerfile
│
├── docker-compose.yml          # Локальная разработка (все сервисы одной командой)
│
├── helm/pharmacy/              # Helm-чарт для Kubernetes
│   ├── Chart.yaml
│   ├── values.yaml             # Базовые значения
│   ├── values-dev.yaml         # Dev: 1 реплика, без HPA
│   ├── values-stage.yaml       # Stage: 2 реплики, HPA до 5
│   ├── values-prod.yaml        # Prod: 3 реплики, HPA до 20, TLS
│   └── templates/
│       ├── backend-deployment.yaml   # Deployment с probes, resources, securityContext
│       ├── backend-service.yaml      # ClusterIP Service
│       ├── frontend-deployment.yaml
│       ├── frontend-service.yaml
│       ├── postgres-statefulset.yaml  # StatefulSet + PVC
│       ├── ingress.yaml              # Nginx Ingress с optional TLS
│       ├── hpa.yaml                  # HorizontalPodAutoscaler (CPU/Memory)
│       ├── networkpolicy.yaml        # deny-all + whitelist
│       ├── rbac.yaml                 # ServiceAccount + Role + RoleBinding
│       ├── secrets.yaml              # DB credentials (в проде — External Secrets)
│       └── nginx-configmap.yaml      # Nginx конфиг для K8s
│
├── .gitlab-ci.yml              # CI/CD пайплайн (lint → test → build → deploy)
│
├── ansible/                    # Управление конфигурацией серверов
│   ├── inventory/hosts.ini     # Серверы по окружениям
│   ├── playbooks/site.yml      # Главный плейбук
│   └── roles/
│       ├── common/             # Базовая настройка: пакеты, UFW, LVM, SSH, sysctl
│       ├── docker/             # Docker CE + containerd + daemon.json
│       └── k8s/                # kubeadm, kubelet, kubectl, Helm
│
├── terraform/                  # Создание облачной инфраструктуры (AWS)
│   ├── main.tf                 # VPC, EC2, RDS, S3, Security Groups
│   ├── variables.tf
│   ├── outputs.tf
│   └── envs/
│       ├── dev.tfvars          # 1 нода, t3.small
│       └── prod.tfvars         # 3 ноды, t3.large
│
├── monitoring/                 # Мониторинг
│   ├── prometheus/
│   │   └── prometheus.yml      # Scrape config: backend, self-monitoring
│   └── grafana/
│       └── dashboards/
│           ├── dashboards.yml              # Provisioning
│           └── pharmacy-dashboard.json     # Request rate, latency, error rate
│
└── scripts/                    # Python-скрипты автоматизации
    ├── cleanup_images.py       # Очистка Docker-образов + Telegram
    ├── log_rotate.py           # Ротация логов + pg_dump бэкап + S3
    └── healthcheck.py          # Health checks сервисов + Telegram-алерты
```


---

## Пошаговый план практики

### Шаг 0: Подготовка машины

Тебе нужен Linux (Ubuntu 22.04/24.04). Варианты:
- Локальная VM (VirtualBox / UTM на Mac)
- AWS EC2 free tier (t3.micro)
- Любой VPS (Hetzner, DigitalOcean)

Минимально: 4GB RAM, 20GB диск.

```bash
# Клонируй проект
git clone <repo-url> pharmacy-infra
cd pharmacy-infra
```


### Шаг 1: Docker Compose — поднять всё локально

**Цель:** убедиться, что приложение работает, понять как сервисы связаны.

```bash
# Собрать и запустить
docker compose up -d --build

# Проверить
docker compose ps
curl http://localhost:8000/api/health      # Backend
curl http://localhost:8000/api/medicines    # Данные
curl http://localhost:80                    # Frontend
curl http://localhost:9090/targets          # Prometheus targets
# Grafana: http://localhost:3000 (admin/admin)
```

**Что изучить:**
- Открой `docker-compose.yml` — как сервисы зависят друг от друга (`depends_on`, `healthcheck`)
- Открой `backend/Dockerfile` — мультистейдж билд, кэширование слоёв, non-root user
- Зайди на `localhost:80` — frontend дёргает `/api/medicines` через Nginx proxy
- Зайди в Prometheus (`localhost:9090`) → Status → Targets — видишь pharmacy-backend?


### Шаг 2: Docker-образы и Harbor

**Цель:** понять как работает registry, пушить образы.

```bash
# Вариант A: Локальный Harbor (если >= 8GB RAM)
# Скачай Harbor offline installer: https://goharbor.io/docs/
# ./install.sh

# Вариант B: Docker Registry (легковесный)
docker run -d -p 5000:5000 --name registry registry:2

# Тегируем и пушим
docker tag pharmacy-infra-backend localhost:5000/pharmacy/backend:v1
docker push localhost:5000/pharmacy/backend:v1

docker tag pharmacy-infra-frontend localhost:5000/pharmacy/frontend:v1
docker push localhost:5000/pharmacy/frontend:v1
```

**Что изучить:**
- Разница между Docker Hub, Harbor, и приватным registry
- Как работают теги образов (latest vs конкретная версия)
- Harbor: проекты, робот-аккаунты, vulnerability scanning


### Шаг 3: Kubernetes — деплой через Helm

**Цель:** развернуть приложение в K8s, понять объекты (Deployment, Service, Ingress, HPA).

```bash
# Установить minikube (локальный K8s)
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

minikube start --cpus=2 --memory=4096 --driver=docker

# Включить Ingress Controller
minikube addons enable ingress
minikube addons enable metrics-server  # Для HPA

# Деплой через Helm
helm upgrade --install pharmacy helm/pharmacy/ \
  --namespace pharmacy-dev \
  --create-namespace \
  --values helm/pharmacy/values-dev.yaml \
  --set backend.image.repository=localhost:5000/pharmacy/backend \
  --set frontend.image.repository=localhost:5000/pharmacy/frontend \
  --set backend.image.tag=v1 \
  --set frontend.image.tag=v1
```

```bash
# Проверить
kubectl -n pharmacy-dev get all
kubectl -n pharmacy-dev get pods -w          # Следить за подами
kubectl -n pharmacy-dev logs -f deploy/pharmacy-backend
kubectl -n pharmacy-dev describe pod <pod-name>

# Проброс портов (если нет Ingress)
kubectl -n pharmacy-dev port-forward svc/pharmacy-frontend 8080:80
# Открой http://localhost:8080
```

**Что изучить — по одному шаблону:**

1. `backend-deployment.yaml` — readinessProbe vs livenessProbe, resources, securityContext, RollingUpdate
2. `backend-service.yaml` — ClusterIP, как поды находят друг друга по DNS
3. `postgres-statefulset.yaml` — почему StatefulSet, а не Deployment (persistent identity, stable hostname)
4. `ingress.yaml` — маршрутизация по path, TLS termination
5. `hpa.yaml` — автоскейлинг по CPU/Memory
6. `networkpolicy.yaml` — сетевая изоляция (deny all → allow explicit)
7. `rbac.yaml` — принцип наименьших привилегий

**Эксперименты:**
```bash
# Убить под — K8s пересоздаст
kubectl -n pharmacy-dev delete pod <backend-pod>

# Масштабировать руками
kubectl -n pharmacy-dev scale deploy pharmacy-backend --replicas=5

# Посмотреть HPA
kubectl -n pharmacy-dev get hpa

# Обновить образ (rolling update)
kubectl -n pharmacy-dev set image deploy/pharmacy-backend backend=...:v2

# Откатить
kubectl -n pharmacy-dev rollout undo deploy/pharmacy-backend
```


### Шаг 4: Prometheus + Grafana

**Цель:** настроить мониторинг, увидеть метрики, настроить алерты.

В Docker Compose Prometheus уже работает. В K8s:

```bash
# Вариант A: kube-prometheus-stack (полный стек)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace

# Вариант B: Prometheus отдельно (наш конфиг)
kubectl -n pharmacy-dev create configmap prometheus-config \
  --from-file=monitoring/prometheus/prometheus.yml
```

```bash
# Grafana
kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80
# Логин: admin / prom-operator (для kube-prometheus-stack)

# Импортировать наш dashboard
# Grafana → Dashboards → Import → загрузить pharmacy-dashboard.json
```

**Что изучить:**
- PromQL запросы: `rate(pharmacy_requests_total[5m])`, `histogram_quantile(0.95, ...)`
- Как бэкенд экспортирует метрики: откройcurl `localhost:8000/metrics`
- Grafana: создать свой dashboard, добавить панели
- Alertmanager + Telegram: настроить webhook для алертов


### Шаг 5: GitLab CI/CD

**Цель:** автоматизировать lint → test → build → deploy.

```bash
# Установить GitLab Runner (локально или на сервере)
# https://docs.gitlab.com/runner/install/

# Или использовать gitlab.com (бесплатный CI/CD)
# Создай проект, запушь код, CI запустится автоматически
```

**Что изучить в `.gitlab-ci.yml`:**
- 4 стейджа: lint → test → build → deploy
- Кэширование pip (ускоряет повторные билды)
- Docker build с `--cache-from` (переиспользование слоёв)
- Разные окружения: develop → dev, main → stage → prod (manual)
- Переменные: `$HARBOR_PASSWORD`, `$KUBE_CONFIG` → Settings → CI/CD → Variables

**Эксперименты:**
- Сломай линтер (добавь unused import) → увидишь fail в pipeline
- Измени код → push → наблюдай автоматический деплой в dev


### Шаг 6: Ansible — настройка серверов

**Цель:** автоматизировать конфигурацию серверов.

```bash
# Если есть сервера/VM:
cd ansible

# Проверить связь
ansible -i inventory/hosts.ini all -m ping

# Запустить только common роль
ansible-playbook -i inventory/hosts.ini playbooks/site.yml --tags common --check
# --check = dry run (показывает что будет сделано, но не делает)

# Полный прогон
ansible-playbook -i inventory/hosts.ini playbooks/site.yml --limit dev
```

**Что изучить:**
- `roles/common/tasks/main.yml` — UFW, LVM, SSH hardening, sysctl
- `roles/docker/tasks/main.yml` — установка Docker, daemon.json
- `roles/k8s/tasks/main.yml` — kubeadm, kubelet, swap off
- Идемпотентность: запусти плейбук дважды → второй раз "changed=0"


### Шаг 7: Terraform — облачная инфраструктура

**Цель:** создать инфраструктуру кодом (IaC).

```bash
cd terraform

# Для практики без AWS — используй LocalStack
# docker run -d -p 4566:4566 localstack/localstack
# export AWS_ENDPOINT_URL=http://localhost:4566

terraform init
terraform plan -var-file=envs/dev.tfvars -var="db_password=testpass"
terraform apply -var-file=envs/dev.tfvars -var="db_password=testpass"

# Посмотреть состояние
terraform show
terraform state list

# Удалить
terraform destroy -var-file=envs/dev.tfvars -var="db_password=testpass"
```

**Что изучить:**
- `main.tf` — VPC, подсети (public/private), Security Groups, EC2, RDS, S3
- Remote state в S3 + DynamoDB locking
- `terraform plan` vs `terraform apply`
- Как Terraform отслеживает изменения через state


### Шаг 8: Python-скрипты автоматизации

**Цель:** автоматизировать рутину (как в резюме).

```bash
# Очистка Docker-образов
python3 scripts/cleanup_images.py --days 14 --dry-run

# Health check (запусти при работающем docker compose)
export BACKEND_URL=http://localhost:8000/api/health
python3 scripts/healthcheck.py

# Ротация логов + бэкап
python3 scripts/log_rotate.py --logs-only

# Добавить в cron
crontab -e
# */5 * * * * /usr/bin/python3 /opt/scripts/healthcheck.py
# 0 2 * * * /usr/bin/python3 /opt/scripts/log_rotate.py
# 0 3 * * 0 /usr/bin/python3 /opt/scripts/cleanup_images.py --days 14
```


---

## Рекомендуемый порядок практики

| # | Этап | Время | Что прокачивается |
|---|------|-------|-------------------|
| 1 | Docker Compose | 1-2 часа | Docker, сеть, volumes |
| 2 | Dockerfile оптимизация | 1 час | Multi-stage, кэш, безопасность |
| 3 | Harbor / Registry | 1 час | Artifact management |
| 4 | minikube + kubectl | 2-3 часа | K8s объекты, debugging |
| 5 | Helm deploy | 2 часа | Helm-чарты, values, templating |
| 6 | Prometheus + Grafana | 2 часа | Метрики, PromQL, dashboards |
| 7 | GitLab CI/CD | 2-3 часа | Пайплайны, стейджи, переменные |
| 8 | Ansible | 2 часа | Роли, плейбуки, идемпотентность |
| 9 | Terraform | 2 часа | IaC, state, plan/apply |
| 10 | Python-скрипты | 1 час | Автоматизация, cron |

Всего: ~15-20 часов практики.


---

## Дополнительные идеи для углубления

- **cert-manager** — автоматические TLS-сертификаты Let's Encrypt в K8s
- **Sealed Secrets / External Secrets** — безопасное хранение секретов
- **ArgoCD** — GitOps деплой (вместо `helm upgrade` в CI)
- **EFK/Loki** — централизованные логи (Elasticsearch или Grafana Loki)
- **Velero** — бэкапы K8s-кластера
- **Trivy** — сканирование Docker-образов на уязвимости
- **Go** — переписать один из Python-скриптов на Go (у тебя в навыках)
