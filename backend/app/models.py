"""
SQLAlchemy 2.0+ модели с Mapped + mapped_column
=================================================
Старый стиль (Column) всё ещё работает, но Mapped — это:
  - Типизация из коробки (IDE автокомплит, mypy)
  - Меньше бойлерплейта
  - Рекомендуемый подход с SQLAlchemy 2.0
"""

from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str] = mapped_column(String, nullable=False)

    medicines: Mapped[list["Medicine"]] = relationship(back_populates="pharmacy")


class Medicine(Base):
    __tablename__ = "medicines"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    stock: Mapped[int] = mapped_column(default=0, nullable=False)
    pharmacy_id: Mapped[int] = mapped_column(ForeignKey("pharmacies.id"), nullable=False)

    pharmacy: Mapped["Pharmacy"] = relationship(back_populates="medicines")
