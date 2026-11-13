"""
Catálogo de los veintiséis elementos de la norma ISAD(G) segunda edición (NTC 4095:2013).

Es la única fuente de verdad sobre qué campos tiene la ficha, cómo se llaman, cuáles son
obligatorios y cuáles pueden editarse a mano. La pantalla, el guardado, la sugerencia con
inteligencia artificial y la validación previa a la entrega leen de aquí, de modo que agregar
o ajustar un elemento se hace en un solo lugar.

Las fechas extremas (3.1.3) se guardan en tres columnas del expediente; aquí se editan como
«fecha inicial», «fecha final» y «texto de las fechas» para que quien describe pueda escribir
una fecha aproximada o con corchetes cuando el documento lo exige.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MARCA_PROPUESTA = "[PROPUESTA DEL MODELO, PENDIENTE DE REVISIÓN]"
_PATRON_MARCA = re.compile(r"\[\s*PROPUESTA DEL MODELO[^\]]*\]\s*", re.IGNORECASE)


@dataclass(frozen=True)
class Elemento:
    clave: str                # nombre de la columna del expediente
    numeral: str              # numeral en la norma
    etiqueta: str
    area: str
    tipo: str = "texto"       # texto | linea | fecha | numero
    obligatorio: bool = False
    ayuda: str = ""
    ia: bool = False          # se le puede pedir una propuesta a la IA
    editable: bool = True


AREAS = {
    "1": "Área de identificación",
    "2": "Área de contexto",
    "3": "Área de contenido y estructura",
    "4": "Área de condiciones de acceso y uso",
    "5": "Área de documentación asociada",
    "6": "Área de notas",
    "7": "Área de control de la descripción",
}

ELEMENTOS: tuple[Elemento, ...] = (
    # Área 1
    Elemento("codigo_referencia", "3.1.1", "Código de referencia", "1", "linea", True,
             "Se construye con el periodo, la serie, la subserie y un consecutivo. Cámbielo solo "
             "si el consecutivo quedó mal."),
    Elemento("titulo", "3.1.2", "Título atribuido", "1", "linea", True,
             "Una línea que identifique la unidad entre todo el fondo, no solo dentro de su carpeta.",
             ia=True),
    Elemento("fechas_texto", "3.1.3", "Fechas extremas (texto)", "1", "linea", True,
             "Como se leerán en la ficha, por ejemplo «1933-02-11 a 1933-09-06» o «[1933]»."),
    Elemento("fecha_inicial", "3.1.3", "Fecha inicial", "1", "fecha", False,
             "Formato año-mes-día. Déjela vacía si no hay fecha legible."),
    Elemento("fecha_final", "3.1.3", "Fecha final", "1", "fecha", False,
             "Formato año-mes-día."),
    Elemento("nivel_descripcion", "3.1.4", "Nivel de descripción", "1", "linea", True,
             "Fondo, sección, serie, subserie, expediente o unidad documental."),
    Elemento("volumen_folios", "3.1.5", "Volumen en folios", "1", "numero", True,
             "Debe coincidir con el último folio de la unidad."),
    Elemento("metros_lineales", "3.1.5", "Extensión en metros lineales", "1", "numero", False,
             "Cien folios equivalen a un centímetro de estante."),
    Elemento("unidades_conservacion", "3.1.5", "Unidades de conservación", "1", "numero", False,
             "Cuántas carpetas, libros o tomos forman la unidad."),
    Elemento("soporte", "3.1.5", "Soporte", "1", "linea", True, "Papel, microfilm, digital…"),
    # Área 2
    Elemento("nombre_productor", "3.2.1", "Nombre del productor", "2", "texto", True,
             "Entidad, unidad administrativa y oficina que produjo la unidad."),
    Elemento("historia_institucional", "3.2.2", "Historia institucional", "2", "texto", False,
             "Se hereda del periodo. Ajústela solo si esta unidad exige precisar algo."),
    Elemento("historia_archivistica", "3.2.3", "Historia archivística", "2", "texto", False,
             "Cómo se custodió la unidad desde su producción hasta hoy."),
    Elemento("forma_ingreso", "3.2.4", "Fuente inmediata de adquisición o transferencia", "2",
             "texto", True, "Por ejemplo, transferencia secundaria."),
    # Área 3
    Elemento("alcance_contenido", "3.3.1", "Alcance y contenido", "3", "texto", True,
             "De qué trata y qué contiene, con asuntos concretos. Es lo que más consulta el "
             "investigador.", ia=True),
    Elemento("valoracion", "3.3.2", "Valoración, selección y eliminación", "3", "texto", True,
             "La disposición final sale de la tabla de valoración documental convalidada."),
    Elemento("nuevos_ingresos", "3.3.3", "Nuevos ingresos", "3", "texto", False,
             "Si se esperan más documentos o el fondo está cerrado."),
    Elemento("organizacion", "3.3.4", "Sistema de organización", "3", "texto", True,
             "Cómo está ordenada y foliada la unidad.", ia=True),
    # Área 4
    Elemento("condiciones_acceso", "3.4.1", "Condiciones de acceso", "4", "texto", True,
             "Restricciones legales o de reserva, o consulta libre."),
    Elemento("condiciones_reproduccion", "3.4.2", "Condiciones de reproducción", "4", "texto", False),
    Elemento("lengua", "3.4.3", "Lengua y escritura de los documentos", "4", "linea", True),
    Elemento("caracteristicas_fisicas", "3.4.4", "Características físicas y requisitos técnicos",
             "4", "texto", False, "Estado de conservación que afecte la consulta.", ia=True),
    Elemento("instrumentos_descripcion", "3.4.5", "Instrumentos de descripción", "4", "texto", False),
    # Área 5
    Elemento("existencia_originales", "3.5.1", "Existencia y localización de originales", "5",
             "texto", False),
    Elemento("existencia_copias", "3.5.2", "Existencia y localización de copias", "5", "texto", False),
    Elemento("unidades_relacionadas", "3.5.3", "Unidades de descripción relacionadas", "5",
             "texto", False, "Otras carpetas o series con las que esta unidad se conecta.", ia=True),
    Elemento("nota_publicaciones", "3.5.4", "Nota de publicaciones", "5", "texto", False),
    # Área 6 y 7
    Elemento("notas", "3.6.1", "Notas", "6", "texto", False,
             "Solo lo que un investigador necesita saber y no cabe en otro elemento.", ia=True),
    Elemento("nota_archivero", "3.7.1", "Nota del archivero", "7", "texto", True),
    Elemento("fuentes_consultadas", "3.7.1", "Fuentes consultadas", "7", "texto", False,
             "Documentos en que se apoyó la descripción (cuadro evolutivo, tabla de valoración, "
             "documento original…)."),
    Elemento("reglas_normas", "3.7.2", "Reglas o normas", "7", "linea", True),
    Elemento("fecha_descripcion", "3.7.3", "Fecha de la descripción", "7", "fecha", True),
)

POR_CLAVE = {e.clave: e for e in ELEMENTOS}
CLAVES_EDITABLES = frozenset(e.clave for e in ELEMENTOS if e.editable)
CLAVES_IA = frozenset(e.clave for e in ELEMENTOS if e.ia)


def tiene_marca(texto) -> bool:
    return bool(texto) and bool(_PATRON_MARCA.search(str(texto)))


def quitar_marca(texto):
    """Quita la marca de propuesta; la persona que edita asume el texto como suyo."""
    if texto is None:
        return None
    return _PATRON_MARCA.sub("", str(texto)).strip()


def _valor_de(exp, clave):
    v = getattr(exp, clave, None)
    if isinstance(v, date):
        return v.isoformat()
    return v


def ficha_completa(exp) -> list[dict]:
    """Los veintiséis elementos con su valor actual, listos para pintar el formulario."""
    salida = []
    for e in ELEMENTOS:
        v = _valor_de(exp, e.clave)
        salida.append({
            "clave": e.clave, "numeral": e.numeral, "etiqueta": e.etiqueta, "area": e.area,
            "area_nombre": AREAS[e.area], "tipo": e.tipo, "obligatorio": e.obligatorio,
            "ayuda": e.ayuda, "ia": e.ia, "valor": "" if v is None else v,
            "es_propuesta": tiene_marca(v)})
    return salida


def convertir(clave: str, valor):
    """Lleva lo escrito en pantalla al tipo de la columna. Lanza ValueError con un mensaje claro."""
    e = POR_CLAVE[clave]
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if e.tipo == "fecha":
        texto = str(valor).strip()
        try:
            return date.fromisoformat(texto[:10])
        except ValueError:
            raise ValueError(f"«{e.etiqueta}» debe escribirse año-mes-día, por ejemplo 1933-02-11.")
    if e.tipo == "numero":
        texto = str(valor).strip().replace(",", ".")
        try:
            n = float(texto)
        except ValueError:
            raise ValueError(f"«{e.etiqueta}» debe ser un número.")
        if n < 0:
            raise ValueError(f"«{e.etiqueta}» no puede ser negativo.")
        return int(n) if clave in ("volumen_folios", "unidades_conservacion") else n
    return str(valor).strip()


def hallazgos(exp) -> list[dict]:
    """
    Lo que impide dar por buena la descripción. Se corre antes de validar y antes de aprobar,
    y así la consulta y la entrega final no llevan textos a medias.

    «bloquea» significa que no se puede validar mientras siga; las advertencias no bloquean pero
    se muestran para que la persona decida.
    """
    salida = []
    for e in ELEMENTOS:
        v = _valor_de(exp, e.clave)
        vacio = v is None or (isinstance(v, str) and not v.strip())
        if tiene_marca(v):
            salida.append({"clave": e.clave, "numeral": e.numeral, "etiqueta": e.etiqueta,
                           "gravedad": "bloquea",
                           "mensaje": "Sigue marcado como propuesta del modelo. Léalo, corríjalo "
                                      "y guarde para que quede como texto suyo."})
        elif vacio and e.obligatorio:
            salida.append({"clave": e.clave, "numeral": e.numeral, "etiqueta": e.etiqueta,
                           "gravedad": "bloquea", "mensaje": "Es obligatorio y está vacío."})

    from geology.dominio.neutralidad import menciona_hoja, rastros
    for e in ELEMENTOS:
        if menciona_hoja(_valor_de(exp, e.clave)):
            salida.append({"clave": e.clave, "numeral": e.numeral, "etiqueta": e.etiqueta,
                           "gravedad": "bloquea",
                           "mensaje": "Menciona la hoja de control. La ficha ISAD(G) describe la "
                                      "unidad sin referirse a ese instrumento; reescriba el pasaje."})
    for e in ELEMENTOS:
        r = rastros(_valor_de(exp, e.clave))
        if r:
            salida.append({"clave": e.clave, "numeral": e.numeral, "etiqueta": e.etiqueta,
                           "gravedad": "bloquea",
                           "mensaje": f"Menciona «{r[0]}». La ficha no debe decir cómo se elaboró; "
                                      "reescriba ese pasaje."})
    titulo = (exp.titulo or "")
    if titulo and not tiene_marca(titulo) and len(titulo.split()) <= 2:
        salida.append({"clave": "titulo", "numeral": "3.1.2", "etiqueta": "Título atribuido",
                       "gravedad": "advertencia",
                       "mensaje": "El título tiene una o dos palabras; difícilmente identifica la "
                                  "unidad entre todo el fondo."})
    if exp.fecha_inicial and exp.fecha_final and exp.fecha_inicial > exp.fecha_final:
        salida.append({"clave": "fecha_final", "numeral": "3.1.3", "etiqueta": "Fecha final",
                       "gravedad": "bloquea", "mensaje": "La fecha final es anterior a la inicial."})
    try:
        ultimo = max((t.folio_hasta or 0) for t in exp.tramites) if exp.tramites else 0
    except Exception:
        ultimo = 0
    if ultimo and exp.volumen_folios and int(exp.volumen_folios) != int(ultimo):
        salida.append({"clave": "volumen_folios", "numeral": "3.1.5", "etiqueta": "Volumen en folios",
                       "gravedad": "advertencia",
                       "mensaje": f"El volumen ({exp.volumen_folios}) no coincide con el último "
                                  f"folio de la hoja de control ({ultimo})."})
    return salida


# ---------------------------------------------------------------------------
# Lo que la plantilla trae y no se edita a mano: se calcula o viene de otro sitio.
# Se muestra para que quien describe vea la fila completa tal como saldrá en la base.
# ---------------------------------------------------------------------------
ESTADO_DESCRIPCION = {
    "Descripción por validar": "Borrador",
    "Descripción validada": "Validada",
    "Archivado": "Aprobada",
    "En inventario de salida": "Aprobada",
}


def _ultima(exp, accion):
    for t in reversed(exp.trazabilidad or []):
        if t.accion == accion:
            return t
    return None


def control_solo_lectura(db, exp) -> list[dict]:
    """Columnas de la plantilla que no se editan aquí: clasificación y control físico."""
    from geology.modelos import Periodo, Seccion, Serie, Subserie
    sub = db.get(Subserie, exp.subserie_id) if exp.subserie_id else None
    serie = db.get(Serie, sub.serie_id) if sub else None
    seccion = db.get(Seccion, serie.seccion_id) if serie else None
    periodo = db.get(Periodo, exp.periodo_id) if exp.periodo_id else None
    val = _ultima(exp, "validar_isadg")
    ultimo_folio = max((t.folio_hasta or 0) for t in exp.tramites) if exp.tramites else ""
    estado = ESTADO_DESCRIPCION.get(exp.estado, "")
    dictamen = {"Borrador": "Pendiente de validación", "Validada": "Validada, pendiente de aprobación",
                "Aprobada": "Aprobado"}.get(estado, "")

    def fila(grupo, etiqueta, valor):
        return {"grupo": grupo, "etiqueta": etiqueta,
                "valor": "" if valor in (None, "") else str(valor)}

    return [
        fila("Clasificación", "Periodo institucional (TVD)",
             f"{periodo.numero_romano} ({periodo.rango_texto})" if periodo else ""),
        fila("Clasificación", "Código de dependencia", seccion.codigo_dependencia if seccion else ""),
        fila("Clasificación", "Código y nombre de serie", f"{serie.codigo} {serie.nombre}" if serie else ""),
        fila("Clasificación", "Código y nombre de subserie", f"{sub.codigo} {sub.nombre}" if sub else ""),
        fila("Control físico", "Carpeta de origen (orden FUID)", exp.codigo_carpeta),
        fila("Control físico", "Caja de origen", exp.caja_origen),
        fila("Control físico", "Lote / caja de trabajo", exp.caja_trabajo),
        fila("Control físico", "Caja definitiva", exp.caja_definitiva),
        fila("Control físico", "Carpeta dentro de la caja", exp.consecutivo_en_caja),
        fila("Control físico", "Folio acumulado final", ultimo_folio),
        fila("Control de la descripción", "Profesional que elabora la descripción", exp.describio),
        fila("Control de la descripción", "Profesional que revisa", val.usuario if val else ""),
        fila("Control de la descripción", "Fecha de la última revisión",
             val.fecha.date().isoformat() if val and val.fecha else ""),
        fila("Control de la descripción", "Estado de la descripción", estado),
        fila("Control de la descripción", "Dictamen", dictamen),
    ]
