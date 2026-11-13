"""Consumo local nuevo: PK compuesta por día y proveedor/modelo.

La unicidad impide filas duplicadas, pero no resuelve carreras first/add ni la
pérdida de incrementos read-modify-write de los consumidores actuales.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from geology.nucleo.bd import Base


class ConsumoModelo(Base):
    __tablename__ = "consumo_lector"  # Nombre y VARCHAR(120) confirmados por estructura.py.
    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    proveedor: Mapped[str] = mapped_column(String(120), primary_key=True)
    peticiones: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    agotado_en: Mapped[Optional[datetime]] = mapped_column(DateTime)
    ultimo_error: Mapped[Optional[str]] = mapped_column(Text)
    __table_args__ = (CheckConstraint("peticiones >= 0", name="ck_consumo_lector_peticiones_no_negativas"),)
