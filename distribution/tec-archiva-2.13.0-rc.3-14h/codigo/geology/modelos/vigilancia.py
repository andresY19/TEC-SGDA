"""
Cuatro tablas nuevas de la versión 2.13.0. No tocan ninguna tabla existente.

  sesion_edicion      quién tiene abierta una hoja o una ficha en este momento (se renueva con un
                      latido cada 30 segundos; pasado un minuto y medio sin latido se da por cerrada).
  alerta              avisos para una persona concreta, con su fecha y si ya los leyó.
  descarga_registro   quién descargó qué instrumento y cuándo. Solo se agrega; nunca se edita.
  documento_apoyo     inventario de documentos facilitativos, de apoyo o duplicados (obligación 9).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from geology.nucleo.bd import Base


class SesionEdicion(Base):
    __tablename__ = "sesion_edicion"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_carpeta: Mapped[str] = mapped_column(String(20), index=True)
    lugar: Mapped[str] = mapped_column(String(20), default="hoja")      # hoja | ficha
    correo: Mapped[str] = mapped_column(String(150), index=True)
    nombre: Mapped[str] = mapped_column(String(150))
    abierta_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultimo_latido: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    cerrada: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Alerta(Base):
    __tablename__ = "alerta"
    id: Mapped[int] = mapped_column(primary_key=True)
    destinatario: Mapped[str] = mapped_column(String(150), index=True)   # correo
    tipo: Mapped[str] = mapped_column(String(40), index=True)
    titulo: Mapped[str] = mapped_column(String(200))
    mensaje: Mapped[str] = mapped_column(Text)
    codigo_carpeta: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    leida_en: Mapped[Optional[datetime]] = mapped_column(DateTime)


class DescargaRegistro(Base):
    __tablename__ = "descarga_registro"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    correo: Mapped[str] = mapped_column(String(150), index=True)
    nombre: Mapped[str] = mapped_column(String(150))
    rol: Mapped[str] = mapped_column(String(20))
    instrumento: Mapped[str] = mapped_column(String(80), index=True)
    ruta: Mapped[str] = mapped_column(String(300))
    filtros: Mapped[Optional[str]] = mapped_column(Text)
    archivo: Mapped[Optional[str]] = mapped_column(String(250))
    bytes: Mapped[Optional[int]] = mapped_column(Integer)
    ip: Mapped[Optional[str]] = mapped_column(String(60))


class DocumentoApoyo(Base):
    __tablename__ = "documento_apoyo"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo_carpeta: Mapped[str] = mapped_column(String(20), index=True)
    tramite_no_item: Mapped[Optional[int]] = mapped_column(Integer)
    folio_desde: Mapped[Optional[int]] = mapped_column(Integer)
    folio_hasta: Mapped[Optional[int]] = mapped_column(Integer)
    documento: Mapped[str] = mapped_column(String(300), default="")
    clase: Mapped[str] = mapped_column(String(20), default="facilitativo")   # facilitativo | duplicado | otro
    motivo: Mapped[Optional[str]] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(15), default="propuesto", index=True)  # propuesto | confirmado | descartado
    origen: Mapped[str] = mapped_column(String(10), default="plataforma")             # plataforma | persona
    decidido_por: Mapped[Optional[str]] = mapped_column(String(150))
    decidido_en: Mapped[Optional[datetime]] = mapped_column(DateTime)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
