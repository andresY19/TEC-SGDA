"""
Asignación de carpetas y cronograma del contrato.

Dos tablas nuevas, sin tocar ninguna existente:

  asignacion        qué carpeta le tocó a quién, en qué etapa y para cuándo. NO guarda el avance:
                    el avance sale del estado real del expediente y de la bitácora, para que no
                    haya un contador que alguien tenga que acordarse de actualizar.
  hito_cronograma   una meta con fechas: cuántas carpetas deben estar en qué estado, para cuándo,
                    en un periodo o en todo el contrato.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from geology.nucleo.bd import Base


class Asignacion(Base):
    __tablename__ = "asignacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_carpeta: Mapped[str] = mapped_column(String(20), index=True)
    persona: Mapped[str] = mapped_column(String(150), index=True)      # correo de quien la trabaja
    etapa: Mapped[str] = mapped_column(String(20), default="hoja_control")   # hoja_control | descripcion
    asignado_por: Mapped[Optional[str]] = mapped_column(String(150))
    asignado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    fecha_limite: Mapped[Optional[date]] = mapped_column(Date)
    nota: Mapped[Optional[str]] = mapped_column(Text)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", index=True)
    cerrada_en: Mapped[Optional[datetime]] = mapped_column(DateTime)


class HitoCronograma(Base):
    __tablename__ = "hito_cronograma"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    periodo: Mapped[str] = mapped_column(String(6), default="")        # romano; vacío = todo el contrato
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    meta_carpetas: Mapped[Optional[int]] = mapped_column(Integer)      # vacío = todas las del periodo
    estado_meta: Mapped[str] = mapped_column(String(40), default="Descripción validada")
    creado_por: Mapped[Optional[str]] = mapped_column(String(150))
