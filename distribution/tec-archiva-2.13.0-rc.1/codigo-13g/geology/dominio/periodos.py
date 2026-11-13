"""Resolución local conservadora; R6/R7/R9 según rutas/unidades.py.

Prioridad comprobada: decisión manual, fechas, inventario sin fechas.
Cruces, extremos incompletos, catálogos ambiguos y sugerencias de caja requieren
persona. No elige por mayoría, fecha inicial ni proximidad. No importa ORM.
"""
from dataclasses import dataclass
from datetime import date

from geology.dominio.fechas import FechaNormalizada

ORIGEN_FECHAS = "fechas"
ORIGEN_INVENTARIO = "inventario"
ORIGEN_MANUAL = "manual"
ORIGEN_SIN_DATO = "sin dato"


@dataclass(frozen=True)
class RangoPeriodo:
    romano: str
    inicio: date | None
    fin: date | None


@dataclass(frozen=True)
class ResolucionPeriodo:
    romano: str = ""
    origen: str = ORIGEN_SIN_DATO
    aviso: str = ""
    discrepancia: str = ""
    requiere_persona: bool = True

    @property
    def resuelto(self) -> bool:
        return bool(self.romano)


def _romano(valor):
    texto = str(valor or "").strip().upper()
    return "" if texto in {"", "S/F", "SF", "SIN FECHA", "N/A", "SP"} else texto


def _fecha(valor):
    if isinstance(valor, FechaNormalizada):
        return valor.completa
    return valor if type(valor) is date else None


def resolver_por_fechas(fecha_inicial, fecha_final, rangos) -> ResolucionPeriodo:
    rangos = tuple(rangos)
    inicio, fin = _fecha(fecha_inicial), _fecha(fecha_final)
    if inicio is None or fin is None:
        return ResolucionPeriodo(aviso="Fechas incompletas o sin fecha; requiere revisión humana.")
    if inicio > fin:
        return ResolucionPeriodo(aviso="Las fechas extremas están invertidas; requiere revisión humana.")
    if not rangos or any(not _romano(r.romano) or type(r.inicio) is not date
                         or type(r.fin) is not date or r.inicio > r.fin for r in rangos):
        return ResolucionPeriodo(aviso="Catálogo de períodos vacío o incompleto; requiere revisión humana.")
    if len({_romano(r.romano) for r in rangos}) != len(rangos):
        return ResolucionPeriodo(aviso="Identificador de período duplicado; requiere revisión humana.")
    # Cobertura inclusiva y única: si toca dos rangos no se adjudica a uno.
    tocados = [r for r in rangos if inicio <= r.fin and fin >= r.inicio]
    completos = [r for r in tocados if r.inicio <= inicio <= fin <= r.fin]
    if len(tocados) == len(completos) == 1:
        return ResolucionPeriodo(_romano(completos[0].romano), ORIGEN_FECHAS, requiere_persona=False)
    aviso = ("Las fechas cruzan períodos o rangos superpuestos" if len(tocados) > 1
             else "Las fechas están fuera de los límites de un período conocido")
    return ResolucionPeriodo(aviso=aviso + "; requiere revisión humana.")


def resolver_periodo(periodo_inventario, fecha_inicial, fecha_final, rangos,
                     periodo_manual="", sugerencia_caja=None) -> ResolucionPeriodo:
    rangos = tuple(rangos)
    inventario, manual = _romano(periodo_inventario), _romano(periodo_manual)
    def conocido(romano):
        return bool(romano) and sum(_romano(r.romano) == romano for r in rangos) == 1
    if manual:
        if not conocido(manual):
            return ResolucionPeriodo(aviso="El período manual no identifica una entrada única del catálogo; requiere revisión humana.")
        return ResolucionPeriodo(manual, ORIGEN_MANUAL, "Período fijado explícitamente por una persona.",
                                 requiere_persona=False)
    por_fechas = resolver_por_fechas(fecha_inicial, fecha_final, rangos)
    if por_fechas.resuelto:
        # Un romano repetido en el catálogo no es un identificador inequívoco.
        if not conocido(por_fechas.romano):
            return ResolucionPeriodo(aviso="Identificador de período duplicado; requiere revisión humana.")
        discrepancia = (f"El inventario indica {inventario}, pero las fechas corresponden a {por_fechas.romano}."
                        if inventario and inventario != por_fechas.romano else "")
        return ResolucionPeriodo(por_fechas.romano, ORIGEN_FECHAS, discrepancia, discrepancia, False)
    # No usar inventario para ocultar una fecha parcial, ilegible o un cruce.
    if fecha_inicial is not None or fecha_final is not None:
        return por_fechas
    if conocido(inventario):
        return ResolucionPeriodo(inventario, ORIGEN_INVENTARIO,
            "Período tomado del inventario, sin comprobación por fechas; requiere revisión humana.")
    aviso = "Sin período inequívoco; requiere revisión humana."
    if sugerencia_caja:
        aviso += " Existe una sugerencia de caja, que no se convierte en asignación automática."
    return ResolucionPeriodo(aviso=aviso)
