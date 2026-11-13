"""Verificación local nueva: delega foliación a reglas existentes; no aprueba ni persiste.

Normaliza los objetos Tramite de cálculo del llamador, como exige _guardar_tramites.
Solo acepta esas estructuras, nunca entidades ORM. El resultado propone un estado;
no lo aplica. Los consumidores actuales que sí persisten requieren revisión separada.
"""
from dataclasses import dataclass, field

from geology.dominio.clasificacion import Encabezado, Asimilacion, asimilar_encabezado
from geology.dominio.estados import Estado
from geology.dominio.fechas import fecha_diligenciamiento_valida
from geology.dominio.folios import Tramite, ErrorEnTramite, verificar_folios


@dataclass(frozen=True)
class UnidadInventario:
    codigo_carpeta: str
    periodo: str
    folios: int | None
    asunto: str = ""
    caja_origen: str = ""


@dataclass
class Lectura:
    encabezado: Encabezado
    tramites: list[Tramite]
    responsable: str = ""
    fecha_diligenciamiento: str = ""


@dataclass
class ResultadoVerificacion:
    clasificacion: Asimilacion = field(default_factory=Asimilacion)
    errores: list[str] = field(default_factory=list)
    errores_localizados: list[ErrorEnTramite] = field(default_factory=list)
    observaciones: list[str] = field(default_factory=list)
    tramites: int = 0
    folios: int = 0
    diferencia_folios: str = ""

    @property
    def alineada(self):
        return self.clasificacion.alineada

    @property
    def requiere_persona(self):
        return True

    @property
    def estado_resultante(self):
        # Dinámico: el consumidor agrega después avisos/errores de resolución del período.
        return Estado.HOJA_EN_ELABORACION if self.errores else Estado.HOJA_POR_REVISAR

    def detalle(self, responsable=""):
        return (f"{self.tramites} trámite(s), {self.folios} folio(s). "
                + ("Corrija los hallazgos; " if self.errores else "Verificación técnica terminada; ")
                + "requiere revisión humana. No constituye aprobación archivística.")


def verificar_hoja(lectura, unidad, opciones, periodo_sugerido=None) -> ResultadoVerificacion:
    if type(lectura) is not Lectura or type(unidad) is not UnidadInventario:
        raise TypeError("Se requieren estructuras de cálculo de lectura e inventario.")
    if type(lectura.encabezado) is not Encabezado or any(type(t) is not Tramite for t in lectura.tramites):
        raise TypeError("Solo se aceptan encabezados y trámites de cálculo; no entidades persistidas.")
    r = ResultadoVerificacion(tramites=len(lectura.tramites))
    if not unidad.periodo:
        r.errores.append("Falta un período comprobable; requiere revisión humana.")
    tvd = [o for o in opciones if o.periodo.strip().upper() == unidad.periodo.strip().upper()]
    r.clasificacion = asimilar_encabezado(lectura.encabezado, tvd)
    r.errores.extend(r.clasificacion.errores)
    if not lectura.tramites:
        r.errores.append("La hoja no contiene trámites; requiere revisión humana.")
    if not lectura.responsable.strip():
        r.errores.append("Falta identificar a quien diligencia la hoja; requiere revisión humana.")
    if not fecha_diligenciamiento_valida(lectura.fecha_diligenciamiento).completa:
        r.errores.append("La fecha de diligenciamiento no es completa o válida; requiere revisión humana.")
    folios = verificar_folios(lectura.tramites, unidad.folios)
    r.errores.extend(folios.errores)
    r.errores_localizados.extend(folios.errores_localizados)
    r.observaciones.extend(folios.observaciones)
    r.folios, r.diferencia_folios = folios.total_folios, folios.diferencia_folios
    if periodo_sugerido:
        r.observaciones.append("Existe una sugerencia de caja; no sustituye la verificación humana del período.")
    return r
