"""
Testigo documental (formato F-GDM-009 versión 4): cuándo hace falta y con qué datos se llena.

Qué es. Un testigo documental es una hoja que se deja dentro de la carpeta, en el lugar donde
debería estar un documento que NO está ahí, para decir qué documento es, de qué expediente es,
en qué soporte está y dónde se encuentra. Sin él, quien abre la carpeta cree que el expediente
está incompleto o no sabe que existe un plano, una fotografía o un disco que le pertenece.

Cuándo hace falta. Cuando un documento del expediente vive fuera de la carpeta:

  1. Está en otro soporte que no cabe en la carpeta: planos y mapas, fotografías, negativos,
     discos (CD, DVD), cintas, video o audio, radiografías, muestras o medios magnéticos.
  2. Está en soporte electrónico y su original vive en un sistema de información.
  3. Es de papel pero se retiró o falta: un documento desglosado, enviado a otra dependencia,
     prestado o extraviado.
  4. Es de gran formato y se guarda en planoteca.

Dónde se detecta en el flujo. En el paso humano 1, cuando alguien del equipo revisa la hoja de
control («Hoja de control por revisar»): es la persona que tiene el expediente delante y puede
colocar el testigo. La plataforma le avisa leyendo los tipos documentales y las observaciones
de los trámites de la hoja, el asunto del inventario y las características físicas, y le deja el
formato ya lleno con lo que se sabe. Que haya o no testigo lo decide la persona; la plataforma
solo avisa, nunca coloca ni quita nada.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy.orm import Session

FORMATOS = {
    "planos": "Planos o mapas",
    "fotografias": "Fotografías, negativos o diapositivas",
    "optico": "Disco óptico (CD, DVD)",
    "magnetico": "Medio magnético (USB, disco duro, disquete)",
    "cintas": "Cintas o rollos",
    "sonoros": "Audio o video",
    "radiografias": "Radiografías",
    "electronico": "Documento electrónico",
    "otro": "Otro soporte (muestras, núcleos, láminas)",
    "papel": "Documento de papel retirado o faltante",
}

# Cada regla: (formato, patrón, motivo). Se evalúan sobre el texto de cada trámite y sobre los
# textos generales del expediente. Todo en minúsculas y sin depender de tildes.
_REGLAS: list[tuple[str, re.Pattern, str]] = [
    ("planos", re.compile(r"\b(planos?|mapas?|planchas?|cartograf\w*|croquis|planimetr\w*|"
                          r"secci[oó]n(?:es)? geol[oó]gic\w*|perfil(?:es)? geol[oó]gic\w*|pliegos?|"
                          r"gran formato)\b"),
     "Menciona planos o mapas, que por su tamaño suelen guardarse en planoteca y no en la carpeta."),
    ("fotografias", re.compile(r"\b(fotograf\w*|fotos?|negativos?|diapositivas?|[aá]lbum(?:es)?|"
                               r"registro fotogr[aá]fico)\b"),
     "Menciona fotografías, negativos o diapositivas, que van en su propio soporte."),
    ("optico", re.compile(r"\b(cd|cds|dvd|dvds|cd-rom|blu-?ray|disco(?:s)? compacto(?:s)?|disco(?:s)? [oó]ptico(?:s)?)\b"),
     "Menciona un disco óptico, que no se guarda dentro de la carpeta de papel."),
    ("magnetico", re.compile(r"\b(usb|memoria usb|disco duro|disquetes?|medio(?:s)? magn[eé]tico(?:s)?|"
                             r"memoria externa)\b"),
     "Menciona un medio magnético o una memoria externa."),
    ("cintas", re.compile(r"\b(cintas?|casetes?|cassettes?|vhs|rollos?|microfilm\w*|microficha\w*)\b"),
     "Menciona cintas, rollos o microfilm."),
    ("sonoros", re.compile(r"\b(audios?|grabaci[oó]n(?:es)?|sonor\w*|videos?|v[ií]deos?|pel[ií]culas?)\b"),
     "Menciona audio o video."),
    ("radiografias", re.compile(r"\b(radiograf\w*|rayos x|placas? radiogr[aá]fic\w*)\b"),
     "Menciona radiografías."),
    ("electronico", re.compile(r"\b(documentos? electr[oó]nic\w*|archivos? electr[oó]nic\w*|expediente electr[oó]nic\w*|"
                               r"correos? electr[oó]nic\w*|sgdea|anexos? digital(?:es)?|medio digital|en digital)\b"),
     "Menciona documentos electrónicos, cuyo original vive en un sistema de información."),
    ("otro", re.compile(r"\b(muestras?|n[uú]cleos?|l[aá]minas? delgadas?|ripios|testigos? de perforaci[oó]n)\b"),
     "Menciona muestras u otros objetos que no son papel (confirme si es un documento o solo el nombre del estudio)."),
    ("papel", re.compile(r"\b(desglos\w*|se retira|retirad[oa]s?|faltante\w*|extrav[ií]ad\w*|perdid[oa]s?|"
                         r"prestad[oa]s?|pr[eé]stamo|trasladad[oa]s? a|enviad[oa]s? a|no se encuentra)\b"),
     "Indica que un documento se retiró, falta o está en otro lugar."),
]


# Lo que la hoja de control escribe cuando una casilla no aplica.
_VACIOS = {"na", "n a", "no aplica", "ninguno", "ninguna", "-", "--", "sin dato", "sin datos", "s d", "sd", "no", "nulo", "0"}


def _plano(texto: str) -> str:
    return (texto or "").lower()


def _fragmento(texto: str, m: re.Match, ancho: int = 70) -> str:
    t = texto or ""
    ini, fin = max(0, m.start() - ancho // 2), min(len(t), m.end() + ancho // 2)
    return ("…" if ini else "") + t[ini:fin].strip() + ("…" if fin < len(t) else "")


def senales(db: Session, exp) -> list[dict]:
    """Lo que hace pensar que esta carpeta necesita uno o más testigos documentales."""
    from geology.modelos import UnidadInventario
    salida: list[dict] = []
    vistos: set[tuple] = set()

    def agregar(formato, motivo, fuente, texto, m, tramite=None):
        clave = (formato, tramite.no_item if tramite else None, fuente)
        if clave in vistos:
            return
        vistos.add(clave)
        salida.append({
            "formato": formato, "formato_nombre": FORMATOS[formato], "motivo": motivo, "fuente": fuente,
            "fragmento": _fragmento(texto, m), "tramite": tramite.no_item if tramite else None,
            "folio_desde": tramite.folio_desde if tramite else None, "folio_hasta": tramite.folio_hasta if tramite else None,
            "documento": ((tramite.tipo_documental or "")[:200] if tramite else ""),
        })

    # 1. Trámite por trámite, que es donde se sabe en qué folios está el documento
    for t in sorted(exp.tramites or [], key=lambda x: x.no_item):
        for campo, nombre in ((t.tipo_documental, "tipo documental"), (t.observaciones, "observaciones")):
            texto = campo or ""
            for formato, rx, motivo in _REGLAS:
                m = rx.search(_plano(texto))
                if m:
                    agregar(formato, motivo, f"Trámite {t.no_item}, {nombre}", texto, m, t)
        electronicos = [x.strip() for x in (t.sistema_informacion, t.expediente_sgdea, t.enlace_acceso)
                        if x and x.strip() and x.strip().lower().replace(".", "").replace("/", "") not in _VACIOS]
        if electronicos:
            texto = " ".join(electronicos)
            class _M:  # un «match» mínimo para citar el texto completo
                def start(self): return 0
                def end(self): return len(texto)
            agregar("electronico", "El trámite indica un sistema de información, un número de expediente electrónico o un enlace: el documento está fuera de la carpeta.",
                    f"Trámite {t.no_item}, localización electrónica", texto, _M(), t)

    # 2. Textos generales del expediente y del inventario de origen
    u = db.query(UnidadInventario).filter(UnidadInventario.codigo_carpeta == exp.codigo_carpeta).first()
    generales = [(exp.nombre_expediente, "nombre del expediente"), (exp.titulo, "título"),
                 (exp.soporte if (exp.soporte or "").strip().lower() not in ("", "papel") else None, "soporte declarado"),
                 (exp.caracteristicas_fisicas, "características físicas"), (exp.existencia_originales, "existencia de originales"),
                 (exp.existencia_copias, "existencia de copias"), (exp.diferencia_folios, "diferencia de folios"),
                 (u.asunto if u else None, "asunto del inventario de origen")]
    for texto, nombre in generales:
        if not texto:
            continue
        for formato, rx, motivo in _REGLAS:
            m = rx.search(_plano(texto))
            if m:
                agregar(formato, motivo, nombre.capitalize(), texto, m)
    return salida


def resumen(db: Session, exp) -> dict:
    s = senales(db, exp)
    formatos = sorted({x["formato_nombre"] for x in s})
    return {"hay": bool(s), "total": len(s), "formatos": formatos, "senales": s,
            "que_hacer": ("Si el documento está fuera de la carpeta, deje un testigo documental (F-GDM-009) en el lugar "
                          "donde iría: un formato por documento o por grupo de documentos del mismo soporte. Anote en las "
                          "observaciones de la hoja de control que se colocó el testigo. Si la mención es solo el nombre de un "
                          "estudio y el documento sí está en la carpeta, no se necesita.")}


def datos_formato(db: Session, exp, senal: dict, responsable: str = "") -> dict:
    """Los datos para llenar el F-GDM-009 de una señal, con lo que ya sabe la plataforma."""
    from geology.modelos import Periodo, Seccion, Serie, Subserie
    sub = db.get(Subserie, exp.subserie_id) if exp.subserie_id else None
    serie = db.get(Serie, sub.serie_id) if sub else None
    seccion = db.get(Seccion, serie.seccion_id) if serie else None
    t = next((x for x in (exp.tramites or []) if x.no_item == senal.get("tramite")), None)
    fmt = senal["formato"]
    obs = [f"Documento ubicado fuera de la carpeta {exp.codigo_carpeta}. {senal['motivo']}"]
    if senal.get("folio_desde"):
        obs.append(f"Folios de la hoja de control: {senal['folio_desde']}" + (f" a {senal['folio_hasta']}" if senal.get("folio_hasta") else "") + ".")
    obs.append(f"Origen del aviso: {senal['fuente']}. [Completar: dónde está hoy el documento y quién lo tiene]")
    return {
        "codigo_dependencia": seccion.codigo_dependencia if seccion else "",
        "dependencia": seccion.oficina_productora if seccion else "",
        "codigo_serie": serie.codigo if serie else "", "serie": serie.nombre if serie else "",
        "codigo_subserie": sub.codigo if sub else "", "subserie": sub.nombre if sub else "",
        "nombre_expediente": exp.nombre_expediente or exp.titulo or "",
        "documento": senal.get("documento") or "",
        "fecha": t.fecha if t and t.fecha else None,
        "formatos": [fmt],
        "otro_cual": "Muestras u otro objeto" if fmt == "otro" else "",
        "localizacion": {
            "caja": exp.caja_definitiva or exp.caja_trabajo or exp.caja_origen or "",
            "carpeta": exp.codigo_carpeta,
            "sistema": (t.sistema_informacion if t else "") or "",
            "expediente_sgdea": (t.expediente_sgdea if t else "") or "",
            "enlace": (t.enlace_acceso if t else "") or "",
        },
        "observaciones": " ".join(obs),
        "responsable": responsable,
        "fecha_diligenciamiento": date.today().strftime("%d/%m/%Y"),
    }
