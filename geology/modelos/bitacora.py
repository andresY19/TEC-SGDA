"""Bitácora local nueva; tabla y detalles de almacenamiento propuestos en 6B.

No configura borrado en cascada ni tareas de purga. El delete-orphan ya presente
en Expediente sigue siendo un riesgo independiente, documentado sin modificarlo.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from geology.nucleo.bd import Base


class Trazabilidad(Base):
    __tablename__ = "trazabilidad"  # Nombre propuesto; no confirmado del original.
    id: Mapped[int] = mapped_column(primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey("unidad_documental.id"), index=True)
    estado_anterior: Mapped[Optional[str]] = mapped_column(String(40))
    estado_nuevo: Mapped[str] = mapped_column(String(40))
    accion: Mapped[str] = mapped_column(Text)
    usuario: Mapped[Optional[str]] = mapped_column(Text)
    motivo: Mapped[Optional[str]] = mapped_column(Text)
    errores: Mapped[Optional[str]] = mapped_column(Text)  # Consumidor entrega json.dumps.
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    expediente: Mapped["Expediente"] = relationship(back_populates="trazabilidad")
