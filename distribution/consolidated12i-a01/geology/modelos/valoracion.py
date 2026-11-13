"""Propuesta ORM local nueva; no reproduce un esquema original certificado.

Tablas confirmadas: periodo_institucional, subserie_documental. Las otras
tablas, claves y relaciones son decisiones locales documentadas en la matriz 6B.
No registra modelos por fuera de Base ni ejecuta conexiones o DDL.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from geology.nucleo.bd import Base


class Fondo(Base):
    __tablename__ = "fondo_archivistico"  # Nombre propuesto localmente.
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    historia_institucional: Mapped[Optional[str]] = mapped_column(Text)
    periodos: Mapped[list["Periodo"]] = relationship(back_populates="fondo")


class Periodo(Base):
    __tablename__ = "periodo_institucional"  # Confirmado por Expediente.periodo_id.
    id: Mapped[int] = mapped_column(primary_key=True)
    # Enlace nuevo opcional: los consumidores actuales no suministran un fondo.
    fondo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("fondo_archivistico.id"), index=True)
    numero_romano: Mapped[str] = mapped_column(String(20), index=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    fecha_inicio: Mapped[Optional[date]] = mapped_column(Date)
    fecha_fin: Mapped[Optional[date]] = mapped_column(Date)
    entidad_productora: Mapped[Optional[str]] = mapped_column(Text)
    historia_institucional: Mapped[Optional[str]] = mapped_column(Text)
    historia_archivistica: Mapped[Optional[str]] = mapped_column(Text)
    caracteristicas_fisicas: Mapped[Optional[str]] = mapped_column(Text)
    fecha_convalidacion_tvd: Mapped[Optional[date]] = mapped_column(Date)
    fondo: Mapped[Optional["Fondo"]] = relationship(back_populates="periodos")
    secciones: Mapped[list["Seccion"]] = relationship(back_populates="periodo")

    @property
    def rango_texto(self) -> str:
        """Presentación local derivada, sin duplicar fechas en una columna."""
        inicio = str(self.fecha_inicio.year) if self.fecha_inicio else "S/F"
        fin = str(self.fecha_fin.year) if self.fecha_fin else "S/F"
        return inicio if inicio == fin else f"{inicio}–{fin}"


class Seccion(Base):
    __tablename__ = "seccion_documental"  # Nombre propuesto localmente.
    id: Mapped[int] = mapped_column(primary_key=True)
    periodo_id: Mapped[int] = mapped_column(ForeignKey("periodo_institucional.id"), index=True)
    codigo_dependencia: Mapped[str] = mapped_column(Text)
    oficina_productora: Mapped[Optional[str]] = mapped_column(Text)
    unidad_administrativa: Mapped[Optional[str]] = mapped_column(Text)
    periodo: Mapped["Periodo"] = relationship(back_populates="secciones")
    series: Mapped[list["Serie"]] = relationship(back_populates="seccion")


class Serie(Base):
    __tablename__ = "serie_documental"  # Nombre propuesto localmente.
    id: Mapped[int] = mapped_column(primary_key=True)
    seccion_id: Mapped[int] = mapped_column(ForeignKey("seccion_documental.id"), index=True)
    codigo: Mapped[str] = mapped_column(Text)
    nombre: Mapped[str] = mapped_column(Text)
    retencion_central_anios: Mapped[Optional[int]] = mapped_column(Integer)
    disposicion_final: Mapped[Optional[str]] = mapped_column(Text)
    seccion: Mapped["Seccion"] = relationship(back_populates="series")
    subseries: Mapped[list["Subserie"]] = relationship(back_populates="serie")


class Subserie(Base):
    __tablename__ = "subserie_documental"  # Confirmado por Expediente.subserie_id.
    id: Mapped[int] = mapped_column(primary_key=True)
    serie_id: Mapped[int] = mapped_column(ForeignKey("serie_documental.id"), index=True)
    codigo: Mapped[str] = mapped_column(Text)
    nombre: Mapped[str] = mapped_column(Text)
    retencion_central_anios: Mapped[Optional[int]] = mapped_column(Integer)
    disposicion_final: Mapped[Optional[str]] = mapped_column(Text)
    soporte: Mapped[Optional[str]] = mapped_column(Text)
    serie: Mapped["Serie"] = relationship(back_populates="subseries")
