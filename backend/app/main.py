"""
Pharmacy Chain API — простой бэкенд для аптечной сети.
Endpoints:
  - GET  /api/health         — healthcheck для K8s probes
  - GET  /api/medicines      — список лекарств
  - POST /api/medicines      — добавить лекарство
  - GET  /api/pharmacies     — список аптек
  - GET  /metrics            — Prometheus-метрики
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
import time
import logging

from .database import engine, get_db, Base, SessionLocal
from .models import Medicine, Pharmacy
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

# ─── Prometheus метрики ───
REQUEST_COUNT = Counter(
    "pharmacy_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "pharmacy_request_duration_seconds",
    "Request latency in seconds",
    ["method", "endpoint"]
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создаём таблицы при старте приложения."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")
    # Seed data
    db = SessionLocal()
    if db.query(Pharmacy).count() == 0:
        pharmacies = [
            Pharmacy(name="Аптека №1 — Центральная", address="ул. Абая 10, Астана", phone="+7 (717) 222-33-44"),
            Pharmacy(name="Аптека №2 — Сарыарка", address="ул. Сарыарка 5, Астана", phone="+7 (717) 333-44-55"),
            Pharmacy(name="Аптека №3 — Байконур", address="пр. Кабанбай батыра 22, Астана", phone="+7 (717) 444-55-66"),
        ]
        medicines = [
            Medicine(name="Парацетамол", category="Жаропонижающее", price=450.0, stock=120, pharmacy_id=1),
            Medicine(name="Ибупрофен", category="Обезболивающее", price=680.0, stock=85, pharmacy_id=1),
            Medicine(name="Амоксициллин", category="Антибиотик", price=1200.0, stock=45, pharmacy_id=2),
            Medicine(name="Омепразол", category="ЖКТ", price=890.0, stock=60, pharmacy_id=2),
            Medicine(name="Лоратадин", category="Антигистаминное", price=350.0, stock=200, pharmacy_id=3),
            Medicine(name="Витамин D3", category="Витамины", price=1500.0, stock=150, pharmacy_id=3),
        ]
        db.add_all(pharmacies)
        db.commit()
        db.add_all(medicines)
        db.commit()
        logger.info("Seed data inserted")
    db.close()
    yield


app = FastAPI(title="Pharmacy Chain API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic-схемы ───
# Pydantic v2: ConfigDict вместо deprecated inner class Config
class MedicineCreate(BaseModel):
    name: str
    category: str
    price: float
    stock: int
    pharmacy_id: int

class MedicineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    price: float
    stock: int
    pharmacy_id: int

class PharmacyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    phone: str


# ─── Middleware для метрик ───
@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    endpoint = request.url.path
    if endpoint != "/metrics":
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(duration)
    return response


# ─── Endpoints ───
@app.get("/api/health")
def health():
    """Healthcheck для Kubernetes liveness/readiness probes."""
    return {"status": "ok", "service": "pharmacy-api"}


@app.get("/metrics")
def metrics():
    """Prometheus-метрики."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/medicines", response_model=list[MedicineResponse])
def list_medicines(
    category: str | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(Medicine)
    if category:
        query = query.filter(Medicine.category == category)
    return query.all()


@app.post("/api/medicines", response_model=MedicineResponse, status_code=201)
def create_medicine(med: MedicineCreate, db: Session = Depends(get_db)):
    pharmacy = db.query(Pharmacy).filter(Pharmacy.id == med.pharmacy_id).first()
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
    obj = Medicine(**med.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    logger.info(f"Created medicine: {obj.name}")
    return obj


@app.get("/api/pharmacies", response_model=list[PharmacyResponse])
def list_pharmacies(db: Session = Depends(get_db)):
    return db.query(Pharmacy).all()
