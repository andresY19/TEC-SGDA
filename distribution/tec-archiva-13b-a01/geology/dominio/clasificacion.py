"""Contratos TVD locales nuevos: lista cerrada y coincidencia exacta, sin semejanza.

La ausencia de una regla documentada de clasificación por contenido produce
abstención explícita. Frecuencias y orden de la tabla no deciden la subserie.
"""
from dataclasses import dataclass, field, asdict

CONFIANZA_ALTA = "alta"
CONFIANZA_MEDIA = "media"
CONFIANZA_BAJA = "baja"


def _texto(valor):
    return str(valor or "").strip().casefold()


@dataclass(frozen=True)
class OpcionTvd:
    periodo: str
    cod_serie: str
    serie: str
    cod_subserie: str
    subserie: str
    retencion_central_anios: int | None = None
    disposicion_final: str = ""
    codigo_dependencia: str = ""
    oficina_productora: str = ""

    def __str__(self):
        return f"{self.codigo_dependencia} | {self.cod_serie} {self.serie} › {self.cod_subserie} {self.subserie}"


@dataclass(frozen=True)
class Encabezado:
    cod_serie: str = ""
    serie: str = ""
    cod_subserie: str = ""
    subserie: str = ""
    nombre_expediente: str = ""
    codigo_dependencia: str = ""
    oficina_productora: str = ""


@dataclass
class Asimilacion:
    opcion: OpcionTvd | None = None
    errores: list[str] = field(default_factory=list)

    @property
    def alineada(self):
        return self.opcion is not None and not self.errores

    @property
    def requiere_persona(self):
        return not self.alineada


def elegir_de_la_lista(opciones, cod_serie, cod_subserie, subserie="", codigo_dependencia=""):
    """Ambos códigos obligatorios; nombres/dependencia suministrados restringen.

    No quita ceros, no interpreta códigos como números y no selecciona el primer
    candidato cuando hay duplicados, incluso si sus etiquetas son iguales.
    """
    if not _texto(cod_serie) or not _texto(cod_subserie):
        return None
    candidatos = [o for o in opciones if _texto(o.cod_serie) == _texto(cod_serie)
        and _texto(o.cod_subserie) == _texto(cod_subserie)
        and (not _texto(subserie) or _texto(o.subserie) == _texto(subserie))
        and (not _texto(codigo_dependencia) or _texto(o.codigo_dependencia) == _texto(codigo_dependencia))]
    return candidatos[0] if len(candidatos) == 1 else None


def asimilar_encabezado(encabezado, opciones) -> Asimilacion:
    opcion = elegir_de_la_lista(opciones, encabezado.cod_serie, encabezado.cod_subserie,
                               encabezado.subserie, encabezado.codigo_dependencia)
    if opcion is None:
        return Asimilacion(errores=["Clasificación TVD incompleta, inexistente o ambigua; requiere revisión humana y dependencia cuando corresponda."])
    if ((encabezado.serie and _texto(encabezado.serie) != _texto(opcion.serie)) or
        (encabezado.oficina_productora and _texto(encabezado.oficina_productora) != _texto(opcion.oficina_productora))):
        return Asimilacion(errores=["Los códigos y las etiquetas del encabezado discrepan; requiere revisión humana."])
    return Asimilacion(opcion)


@dataclass(frozen=True)
class Eleccion:
    opcion: OpcionTvd | None = None
    porque: str = "Requiere revisión humana; no hay clasificación inequívoca."
    confianza: str = CONFIANZA_BAJA
    origen: str = "revision_humana"

    @property
    def hay(self):
        return self.opcion is not None

    @property
    def requiere_persona(self):
        return True  # Una propuesta de contenido nunca equivale a aprobación archivística.

    def como_dict(self):
        if self.opcion is None:
            return None  # Contrato de _proponer_subserie: dict | None, motivo por separado.
        return {**asdict(self.opcion), "porque": self.porque, "confianza": self.confianza,
                "origen": self.origen, "requiere_persona": True}

    def frase(self):
        return (f"Propuesta: {self.opcion}. " if self.hay else "") + self.porque + " Requiere revisión humana."


def elegir_por_contenido(opciones, textos, frecuencias=None) -> Eleccion:
    return Eleccion(porque="No hay una regla documentada suficiente para elegir por contenido; "
                    "no se utiliza semejanza, frecuencia ni la primera fila. Requiere revisión humana.")
