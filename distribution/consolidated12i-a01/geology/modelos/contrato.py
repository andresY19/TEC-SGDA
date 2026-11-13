"""
Todo lo del Contrato 733 de 2026 que no es un expediente: parámetros, lotes de entrega,
cumplimiento de las obligaciones, observaciones de la supervisión, documentos generados y el
proceso de eliminación documental.

Seis tablas nuevas, ninguna toca las existentes.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from geology.nucleo.bd import Base


class ParametroContrato(Base):
    """Un valor del contrato que la administradora puede corregir (valor, plazo, metros…)."""
    __tablename__ = "parametro_contrato"
    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(Text)


class LoteContrato(Base):
    """Un lote mensual de entrega, con su meta en metros lineales. Sale del plan de trabajo."""
    __tablename__ = "lote_contrato"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    meta_ml: Mapped[float] = mapped_column(Float, default=0)
    recibido_en: Mapped[Optional[date]] = mapped_column(Date)       # recibo a satisfacción
    facturado_en: Mapped[Optional[date]] = mapped_column(Date)
    valor_facturado: Mapped[Optional[float]] = mapped_column(Float)
    nota: Mapped[Optional[str]] = mapped_column(Text)


class ObligacionContrato(Base):
    """Estado de cada obligación específica de la cláusula 12 (las 19)."""
    __tablename__ = "obligacion_contrato"
    numero: Mapped[int] = mapped_column(Integer, primary_key=True)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")   # pendiente | en_curso | cumplida
    evidencia: Mapped[Optional[str]] = mapped_column(Text)
    actualizado_por: Mapped[Optional[str]] = mapped_column(String(150))
    actualizado_en: Mapped[Optional[datetime]] = mapped_column(DateTime)


class ObservacionSupervision(Base):
    """Lo que pide la supervisión: correcciones, ajustes o mejoras (obligación 8)."""
    __tablename__ = "observacion_supervision"
    id: Mapped[int] = mapped_column(primary_key=True)
    fecha: Mapped[date] = mapped_column(Date)
    origen: Mapped[str] = mapped_column(String(40), default="muestreo")    # muestreo | reunión | oficio | otro
    lote: Mapped[Optional[int]] = mapped_column(Integer)
    descripcion: Mapped[str] = mapped_column(Text)
    carpetas: Mapped[Optional[str]] = mapped_column(Text)                  # códigos separados por coma
    responsable: Mapped[Optional[str]] = mapped_column(String(150))
    fecha_limite: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="abierta", index=True)   # abierta | corregida | cerrada
    cerrada_en: Mapped[Optional[date]] = mapped_column(Date)
    respuesta: Mapped[Optional[str]] = mapped_column(Text)
    creado_por: Mapped[Optional[str]] = mapped_column(String(150))


class DocumentoContrato(Base):
    """
    Un documento generado por la plataforma (informe, ficha técnica, acta…) y editable.

    El contenido son bloques —títulos, párrafos, listas y tablas— y no un archivo: así el visor
    los edita uno por uno, se guardan versiones y el mismo contenido sale en Word, en
    presentación o en Excel sin que haya que rehacerlo.
    """
    __tablename__ = "documento_contrato"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(40), index=True)
    titulo: Mapped[str] = mapped_column(String(250))
    clave: Mapped[Optional[str]] = mapped_column(String(80), index=True)    # p. ej. el mes o el lote
    contenido: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)
    estado: Mapped[str] = mapped_column(String(20), default="borrador")     # borrador | firmado
    creado_por: Mapped[Optional[str]] = mapped_column(String(150))
    editado_por: Mapped[Optional[str]] = mapped_column(String(150))
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    editado_en: Mapped[Optional[datetime]] = mapped_column(DateTime)
    proceso_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)  # si es de una eliminación


class ProcesoEliminacion(Base):
    """Una propuesta de eliminación documental y el camino que recorre según el procedimiento."""
    __tablename__ = "proceso_eliminacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(30), default="propuesta", index=True)
    metodo: Mapped[Optional[str]] = mapped_column(String(200))
    # Hitos, en el orden del procedimiento. Los plazos de publicación y de concepto técnico se
    # calculan en días hábiles a partir de estas fechas.
    fecha_sustentacion: Mapped[Optional[date]] = mapped_column(Date)
    acta_comite: Mapped[Optional[str]] = mapped_column(String(80))
    fecha_aprobacion: Mapped[Optional[date]] = mapped_column(Date)
    publicacion_inicio: Mapped[Optional[date]] = mapped_column(Date)
    hubo_observaciones: Mapped[Optional[bool]] = mapped_column(Boolean)
    concepto_solicitado: Mapped[Optional[date]] = mapped_column(Date)
    concepto_recibido: Mapped[Optional[date]] = mapped_column(Date)
    fecha_eliminacion: Mapped[Optional[date]] = mapped_column(Date)
    acta_publicada: Mapped[Optional[date]] = mapped_column(Date)
    nota: Mapped[Optional[str]] = mapped_column(Text)
    creado_por: Mapped[Optional[str]] = mapped_column(String(150))
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ItemEliminacion(Base):
    """Una carpeta propuesta para eliminar y lo que una persona decidió sobre ella."""
    __tablename__ = "item_eliminacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    proceso_id: Mapped[int] = mapped_column(Integer, index=True)
    codigo_carpeta: Mapped[str] = mapped_column(String(20), index=True)
    disposicion: Mapped[str] = mapped_column(String(10))                    # E | S
    periodo: Mapped[Optional[str]] = mapped_column(String(6))
    serie_tvd: Mapped[Optional[str]] = mapped_column(String(250))
    subserie_tvd: Mapped[Optional[str]] = mapped_column(String(250))
    estado: Mapped[str] = mapped_column(String(20), default="propuesta")    # propuesta | confirmada | excluida
    motivo: Mapped[Optional[str]] = mapped_column(Text)
    posible_ddhh: Mapped[bool] = mapped_column(Boolean, default=False)      # el asunto sugiere derechos humanos
    decidido_por: Mapped[Optional[str]] = mapped_column(String(150))
    decidido_en: Mapped[Optional[datetime]] = mapped_column(DateTime)


class PagoContrato(Base):
    """
    Un pago mensual vencido del contrato (cláusula cuarta): metros lineales intervenidos y
    recibidos a satisfacción en el periodo, factura y trámite de cobro. La proyección que
    entrega el Servicio Geológico (30, 40, 40 y 65 ML) es el punto de partida y se puede editar.
    """
    __tablename__ = "pago_contrato"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    periodo_desde: Mapped[date] = mapped_column(Date)
    periodo_hasta: Mapped[date] = mapped_column(Date)
    ml_proyectados: Mapped[float] = mapped_column(Float, default=0)          # proyección del SGC
    ml_a_cobrar: Mapped[Optional[float]] = mapped_column(Float)              # lo que la administradora decide cobrar
    estado: Mapped[str] = mapped_column(String(20), default="proyectado")    # proyectado | prefactura | aprobado | facturado | radicado | pagado
    prefactura_enviada: Mapped[Optional[date]] = mapped_column(Date)
    prefactura_aprobada: Mapped[Optional[date]] = mapped_column(Date)
    recibo_satisfaccion: Mapped[Optional[date]] = mapped_column(Date)
    factura_numero: Mapped[Optional[str]] = mapped_column(String(60))
    factura_fecha: Mapped[Optional[date]] = mapped_column(Date)
    radicado_en: Mapped[Optional[date]] = mapped_column(Date)
    pagado_en: Mapped[Optional[date]] = mapped_column(Date)
    valor_pagado: Mapped[Optional[float]] = mapped_column(Float)
    soportes: Mapped[Optional[dict]] = mapped_column(JSONB)                  # {clave: true} de la lista de soportes
    nota: Mapped[Optional[str]] = mapped_column(Text)
