"""Caja local nueva; vínculo textual con expedientes, sin FK artificial."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from geology.nucleo.bd import Base


class Caja(Base):
    __tablename__ = "caja"  # Nombre propuesto; no confirmado del original.
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    periodo: Mapped[str] = mapped_column(String(20))  # Numeral romano, no periodo_id.
    total_carpetas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cerrada: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    cerrada_en: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cerrada_por: Mapped[Optional[str]] = mapped_column(Text)
    observaciones: Mapped[Optional[str]] = mapped_column(Text)
    __table_args__ = (CheckConstraint("total_carpetas >= 0", name="ck_caja_total_no_negativo"),)
