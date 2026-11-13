"""
Seguimiento del contrato: asignación de carpetas, cronograma y tablero de control.

Quién puede qué:
  - La administradora asigna, reasigna, define el cronograma y ve todo.
  - La líder ve el tablero y el cronograma, y sus propias carpetas.
  - Cada persona del equipo ve solo sus carpetas asignadas.
  - Consulta y entidad no entran aquí.

Asignar no bloquea a nadie: otra persona puede seguir trabajando una carpeta asignada (por
ejemplo, cubriendo una ausencia). La asignación sirve para repartir la carga y para medir.
"""
from __future__ import annotations

import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from geology.dominio import seguimiento as seg
from geology.dominio.estados import Estado, Rol, Usuario
from geology.modelos import Asignacion, Expediente, HitoCronograma, UnidadInventario, UsuarioBD
from geology.nucleo.bd import obtener_sesion
from geology.rutas.cuentas import usuario_actual

router = APIRouter(prefix="/seguimiento", tags=["Seguimiento"])

EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _admin(q: Usuario) -> None:
    if q.rol is not Rol.ADMINISTRADORA:
        raise HTTPException(403, "Asignar carpetas y definir el cronograma lo hace la administradora.")


def _ve_tablero(q: Usuario) -> None:
    if q.rol not in (Rol.ADMINISTRADORA, Rol.LIDER):
        raise HTTPException(403, "El tablero de seguimiento lo ven la administradora y la líder.")


def _trabaja(q: Usuario) -> None:
    if q.solo_consulta:
        raise HTTPException(403, "Su perfil no tiene carpetas asignadas.")


def _persona(db: Session, correo: str) -> UsuarioBD:
    u = db.query(UsuarioBD).filter(UsuarioBD.correo == (correo or "").strip().lower(),
                                   UsuarioBD.activo.is_(True)).first()
    if not u or u.rol not in ("equipo", "lider", "administradora"):
        raise HTTPException(422, f"{correo} no es una persona activa del equipo.")
    return u


def _etapa(etapa: str) -> str:
    if etapa not in seg.ETAPAS:
        raise HTTPException(422, "La etapa es «hoja_control» o «descripcion».")
    return etapa


def _poner(db: Session, codigo: str, persona: str, etapa: str, quien: Usuario,
           limite: date | None, nota: str | None) -> str:
    """Crea la asignación o, si la carpeta ya estaba asignada en esa etapa, la reasigna."""
    previa = (db.query(Asignacion).filter(Asignacion.codigo_carpeta == codigo,
                                          Asignacion.etapa == etapa,
                                          Asignacion.activa.is_(True)).first())
    if previa:
        if previa.persona == persona and previa.fecha_limite == limite:
            return "igual"
        previa.persona, previa.asignado_por = persona, quien.nombre
        previa.fecha_limite, previa.nota = limite, nota or previa.nota
        from datetime import datetime
        previa.asignado_en = datetime.now()
        return "reasignada"
    db.add(Asignacion(codigo_carpeta=codigo, persona=persona, etapa=etapa,
                      asignado_por=quien.nombre, fecha_limite=limite, nota=nota))
    return "nueva"


# ---------------------------------------------------------------------------------------
class Asignar(BaseModel):
    carpetas: list[str] = Field(min_length=1)
    persona: str
    etapa: str = "hoja_control"
    fecha_limite: date | None = None
    nota: str | None = None


class AsignarLote(BaseModel):
    personas: list[str] = Field(min_length=1)
    etapa: str = "hoja_control"
    por_persona: int = Field(ge=1, le=2000)
    periodo: str = ""
    caja: str = ""
    estado: str = ""
    fecha_limite: date | None = None
    nota: str | None = None


class HitoNuevo(BaseModel):
    nombre: str
    periodo: str = ""
    fecha_inicio: date
    fecha_fin: date
    meta_carpetas: int | None = None
    estado_meta: str = "Descripción validada"


def _validar_hito(h: HitoNuevo) -> None:
    if h.fecha_fin < h.fecha_inicio:
        raise HTTPException(422, "La fecha final no puede ser anterior a la inicial.")
    if h.estado_meta not in seg.RANGO:
        raise HTTPException(422, "El estado de la meta no existe. Use uno de: " + ", ".join(seg.RANGO))
    if h.meta_carpetas is not None and h.meta_carpetas < 1:
        raise HTTPException(422, "La meta debe ser de al menos una carpeta.")


# ---------------------------------------------------------------------------------------
@router.get("/resumen", summary="Tablero de control: cronograma, personas y carpetas colgadas")
def resumen(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _ve_tablero(quien)
    return seg.resumen(db)


@router.get("/mis", summary="Mis carpetas asignadas")
def mis(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _trabaja(quien)
    vivas = seg.asignaciones_vivas(db, solo_persona=quien.correo)
    orden = {"devuelta": 0, "en_curso": 1, "pendiente": 2, "sin_documento": 3, "hecha": 4, "retirada": 5}
    vivas.sort(key=lambda v: (not v["vencida"], orden.get(v["estado"], 9), v["fecha_limite"] or "9999"))
    return {"carpetas": vivas,
            "resumen": {"asignadas": len(vivas),
                        "hechas": sum(1 for v in vivas if v["estado"] == "hecha"),
                        "abiertas": sum(1 for v in vivas if v["estado"] not in ("hecha", "retirada")),
                        "vencidas": sum(1 for v in vivas if v["vencida"]),
                        "colgadas": sum(1 for v in vivas if v["colgada"])}}


@router.get("/equipo", summary="Personas a quienes se les puede asignar")
def equipo(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    _admin(quien)
    return [{"correo": u.correo, "nombre": u.nombre, "rol": u.rol, "funcion": u.funcion}
            for u in seg._personas(db).values()]


@router.get("/disponibles", summary="Carpetas que todavía no tienen responsable en esa etapa")
def disponibles(etapa: str = "hoja_control", periodo: str = "", caja: str = "", estado: str = "",
                buscar: str = "", limite: int = Query(300, le=1000),
                db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    _etapa(etapa)
    return {"carpetas": _candidatas(db, etapa, periodo, caja, estado, buscar, limite)}


def _candidatas(db: Session, etapa: str, periodo: str, caja: str, estado: str, buscar: str,
                limite: int) -> list[dict]:
    asignadas = {c for (c,) in db.query(Asignacion.codigo_carpeta)
                 .filter(Asignacion.etapa == etapa, Asignacion.activa.is_(True)).all()}
    q = (db.query(UnidadInventario, Expediente.estado)
           .outerjoin(Expediente, Expediente.codigo_carpeta == UnidadInventario.codigo_carpeta))
    if periodo:
        q = q.filter(UnidadInventario.periodo == periodo)
    if caja:
        q = q.filter((UnidadInventario.caja_trabajo == caja) | (UnidadInventario.caja_origen == caja))
    if buscar:
        q = q.filter(UnidadInventario.codigo_carpeta.ilike(f"%{buscar.strip()}%"))
    hecha_en = seg.ETAPA_HECHA[etapa]
    salida = []
    for u, est in q.order_by(UnidadInventario.codigo_carpeta).yield_per(500):
        if u.codigo_carpeta in asignadas:
            continue
        est_txt = est or "Sin documento cargado"
        if est == Estado.RETIRADO.value or seg.RANGO.get(est, -1) >= hecha_en:
            continue
        if estado and est_txt != estado:
            continue
        salida.append({"carpeta": u.codigo_carpeta, "periodo": u.periodo, "caja": u.caja_trabajo or u.caja_origen,
                       "folios": u.folios, "estado": est_txt})
        if len(salida) >= limite:
            break
    return salida


@router.post("/asignar", summary="Asignar carpetas elegidas a una persona")
def asignar(datos: Asignar, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    etapa = _etapa(datos.etapa)
    p = _persona(db, datos.persona)
    cuentas = {"nueva": 0, "reasignada": 0, "igual": 0}
    desconocidas = []
    for c in dict.fromkeys(x.strip().upper() for x in datos.carpetas if x.strip()):
        if not db.query(UnidadInventario.id).filter(UnidadInventario.codigo_carpeta == c).first():
            desconocidas.append(c)
            continue
        cuentas[_poner(db, c, p.correo, etapa, quien, datos.fecha_limite, datos.nota)] += 1
    db.commit()
    return {**cuentas, "no_estan_en_el_inventario": desconocidas, "persona": p.nombre}


@router.post("/asignar-lote", summary="Repartir carga: N carpetas por persona, en bloques")
def asignar_lote(datos: AsignarLote, db: Session = Depends(obtener_sesion),
                 quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    etapa = _etapa(datos.etapa)
    personas = [_persona(db, c) for c in datos.personas]
    necesarias = datos.por_persona * len(personas)
    libres = _candidatas(db, etapa, datos.periodo, datos.caja, datos.estado, "", necesarias)
    if not libres:
        raise HTTPException(404, "No hay carpetas sin responsable que cumplan ese filtro.")
    reparto = {}
    i = 0
    for p in personas:
        trozo = libres[i:i + datos.por_persona]
        i += datos.por_persona
        for f in trozo:
            _poner(db, f["carpeta"], p.correo, etapa, quien, datos.fecha_limite, datos.nota)
        reparto[p.nombre] = {"cantidad": len(trozo),
                             "desde": trozo[0]["carpeta"] if trozo else None,
                             "hasta": trozo[-1]["carpeta"] if trozo else None}
    db.commit()
    faltaron = max(0, necesarias - len(libres))
    return {"reparto": reparto, "total": min(len(libres), necesarias),
            "mensaje": (f"Solo había {len(libres)} carpetas libres; faltaron {faltaron} por repartir."
                        if faltaron else "Reparto hecho.")}


@router.put("/asignaciones/{asignacion_id}", summary="Cambiar responsable o fecha límite")
def cambiar(asignacion_id: int, persona: str | None = None, fecha_limite: date | None = None,
            nota: str | None = None, db: Session = Depends(obtener_sesion),
            quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    a = db.get(Asignacion, asignacion_id)
    if not a or not a.activa:
        raise HTTPException(404, "Esa asignación no existe o ya se quitó.")
    if persona:
        a.persona = _persona(db, persona).correo
        from datetime import datetime
        a.asignado_en, a.asignado_por = datetime.now(), quien.nombre
    if fecha_limite is not None:
        a.fecha_limite = fecha_limite
    if nota is not None:
        a.nota = nota
    db.commit()
    return {"id": a.id, "persona": a.persona, "fecha_limite": a.fecha_limite}


@router.delete("/asignaciones/{asignacion_id}", summary="Quitar una asignación")
def quitar(asignacion_id: int, db: Session = Depends(obtener_sesion),
           quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    a = db.get(Asignacion, asignacion_id)
    if not a or not a.activa:
        raise HTTPException(404, "Esa asignación no existe o ya se quitó.")
    from datetime import datetime
    a.activa, a.cerrada_en = False, datetime.now()
    db.commit()
    return {"quitada": a.codigo_carpeta}


@router.get("/asignaciones", summary="Todas las asignaciones con su estado")
def todas(persona: str = "", solo_abiertas: bool = False, db: Session = Depends(obtener_sesion),
          quien: Usuario = Depends(usuario_actual)) -> list[dict]:
    _admin(quien)
    return seg.asignaciones_vivas(db, solo_persona=persona or None, solo_abiertas=solo_abiertas)


# --- cronograma -------------------------------------------------------------------------
def _hito_dict(h: HitoCronograma) -> dict:
    return {"id": h.id, "nombre": h.nombre, "periodo": h.periodo, "fecha_inicio": h.fecha_inicio.isoformat(),
            "fecha_fin": h.fecha_fin.isoformat(), "meta_carpetas": h.meta_carpetas,
            "estado_meta": h.estado_meta}


@router.get("/hitos", summary="Metas del cronograma")
def hitos(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)) -> dict:
    _ve_tablero(quien)
    return {"hitos": [_hito_dict(h) for h in
                      db.query(HitoCronograma).order_by(HitoCronograma.fecha_fin, HitoCronograma.id).all()],
            "estados_posibles": list(seg.RANGO)}


@router.post("/hitos", summary="Crear una meta del cronograma")
def crear_hito(datos: HitoNuevo, db: Session = Depends(obtener_sesion),
               quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    _validar_hito(datos)
    h = HitoCronograma(nombre=datos.nombre.strip(), periodo=datos.periodo.strip().upper(),
                       fecha_inicio=datos.fecha_inicio, fecha_fin=datos.fecha_fin,
                       meta_carpetas=datos.meta_carpetas, estado_meta=datos.estado_meta,
                       creado_por=quien.nombre)
    db.add(h)
    db.commit()
    return _hito_dict(h)


@router.put("/hitos/{hito_id}", summary="Cambiar una meta del cronograma")
def cambiar_hito(hito_id: int, datos: HitoNuevo, db: Session = Depends(obtener_sesion),
                 quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    _validar_hito(datos)
    h = db.get(HitoCronograma, hito_id)
    if not h:
        raise HTTPException(404, "Esa meta no existe.")
    h.nombre, h.periodo = datos.nombre.strip(), datos.periodo.strip().upper()
    h.fecha_inicio, h.fecha_fin = datos.fecha_inicio, datos.fecha_fin
    h.meta_carpetas, h.estado_meta = datos.meta_carpetas, datos.estado_meta
    db.commit()
    return _hito_dict(h)


@router.delete("/hitos/{hito_id}", summary="Borrar una meta del cronograma")
def borrar_hito(hito_id: int, db: Session = Depends(obtener_sesion),
                quien: Usuario = Depends(usuario_actual)) -> dict:
    _admin(quien)
    h = db.get(HitoCronograma, hito_id)
    if not h:
        raise HTTPException(404, "Esa meta no existe.")
    db.delete(h)
    db.commit()
    return {"borrada": h.nombre}


# --- Excel ------------------------------------------------------------------------------
@router.get("/excel", summary="Informe de seguimiento en Excel")
def excel(db: Session = Depends(obtener_sesion), quien: Usuario = Depends(usuario_actual)):
    _admin(quien)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    r = seg.resumen(db)
    wb = Workbook()

    def hoja(titulo, cab, filas, primera=False):
        ws = wb.active if primera else wb.create_sheet()
        ws.title = titulo
        ws.append(cab)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="2F6B52")
        for f in filas:
            ws.append(f)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(48, max(12, max(len(str(c.value or "")) for c in col) + 2))

    hoja("Personas", ["Persona", "Rol", "Asignadas", "Hechas", "En curso", "Pendientes", "Devueltas",
                      "Vencidas", "Colgadas", "Movidas 14 días", "Última actividad", "Lectura"],
         [[p["nombre"], p["rol"], p["asignadas"], p["hechas"], p["en_curso"], p["pendientes"],
           p["devueltas"], p["vencidas"], p["colgadas"], p["movidas_14d"],
           p["ultima_actividad"] or "nunca", p["lectura"]] for p in r["personas"]], primera=True)
    hoja("Cronograma", ["Meta", "Periodo", "Inicio", "Fin", "Estado de la meta", "Meta (carpetas)",
                        "Real", "Esperado a hoy", "Faltan", "Días hábiles restantes",
                        "Ritmo requerido/día", "Ritmo actual/día (7 d)", "Proyección de fin", "Semáforo"],
         [[h["nombre"], h["periodo"], h["fecha_inicio"], h["fecha_fin"], h["estado_meta"], h["meta"],
           h["real"], h["esperado_a_hoy"], h["faltan"], h["dias_habiles_restantes"],
           h["ritmo_requerido"], h["ritmo_actual_7d"], h["proyeccion_fin"], h["semaforo"]]
          for h in r["hitos"]])
    hoja("Carpetas colgadas o vencidas", ["Carpeta", "Persona", "Etapa", "Estado", "Estado del expediente",
                                           "Días sin mover", "Fecha límite", "Vencida", "Colgada"],
         [[c["carpeta"], c["persona_nombre"], c["etapa_texto"], c["estado"], c["estado_expediente"],
           c["dias_sin_mover"], c["fecha_limite"] or "", "sí" if c["vencida"] else "",
           "sí" if c["colgada"] else ""] for c in r["colgadas"]])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type=EXCEL, headers={
        "Content-Disposition": f'attachment; filename="Seguimiento_{date.today().isoformat()}.xlsx"'})
