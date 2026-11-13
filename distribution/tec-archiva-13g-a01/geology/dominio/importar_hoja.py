"""Lectura completa antes de devolver hojas; solo mapa F-GDM-007 v4 documentado.

No acepta fórmulas, macros, vínculos externos, pestañas desconocidas ni libros
sobredimensionados. Sin escrituras ni importación ORM; no adivina códigos.
"""
from dataclasses import dataclass,field
from datetime import date,datetime
from io import BytesIO
from pathlib import Path
import re
import zipfile
import openpyxl
from geology.dominio import formatos_sgc as fmt
from geology.dominio.codigos import normalizar_codigo_carpeta
from geology.dominio.fechas import normalizar_fecha,fecha_diligenciamiento_valida

MAX_BYTES=25*1024*1024


@dataclass
class HojaImportada:
    hoja:str
    codigo_carpeta:str
    encabezado:dict
    tramites:list
    avisos:list=field(default_factory=list)
    error:str=''


def _texto(v):
    return v.isoformat() if isinstance(v,(date,datetime)) else str(v or '').strip()


def leer_libro(origen,nombre=''):
    try:
        if isinstance(origen,(bytes,bytearray)):
            raw=bytes(origen)
        else:
            with Path(origen).open('rb') as f: raw=f.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES: raise ValueError
        with zipfile.ZipFile(BytesIO(raw)) as z:
            infos=z.infolist()
            if len(infos)>1000 or sum(x.file_size for x in infos)>100*1024*1024: raise ValueError
            if any(x.flag_bits&1 or 'vbaproject' in x.filename.lower() or 'externallinks/' in x.filename.lower() for x in infos): raise ValueError
        libro=openpyxl.load_workbook(BytesIO(raw),read_only=True,data_only=False,keep_links=False)
    except Exception:
        raise ValueError('Libro inválido, protegido, no admitido o demasiado grande.') from None
    resultados=[]
    try:
        if not 1<=len(libro.worksheets)<=50: raise ValueError
        for h in libro.worksheets:
            h.reset_dimensions()
            h.calculate_dimension(force=True)
            if h.sheet_state!='visible' or h.max_row>10000 or h.max_column>30: raise ValueError
            for fila in h.iter_rows():
                if any(c.data_type=='f' or (isinstance(c.value,str) and c.value.lstrip().startswith(('=','+','@'))) for c in fila): raise ValueError
            # Identificador de formato, mapa de celdas conocido y columnas de trámites.
            marca=' '.join(_texto(c.value) for row in h.iter_rows(min_row=1,max_row=10) for c in row)
            if 'F-GDM-007' not in marca or not re.search(r'(?:versi[oó]n\s*:?\s*4|\bv4)(?![\d.])',marca,re.I): raise ValueError
            codigo=normalizar_codigo_carpeta(h.title) or normalizar_codigo_carpeta(Path(nombre).stem)
            if not codigo: raise ValueError
            encabezado={k:_texto(h[celda].value) for k,celda in fmt.HC_ENCABEZADO.items()}
            if not encabezado['codigo_serie'] or not encabezado['codigo_subserie']: raise ValueError
            if any(not isinstance(h[fmt.HC_ENCABEZADO[k]].value,str) for k in ('codigo_serie','codigo_subserie')): raise ValueError
            filas=[]
            terminada=False
            for n in range(fmt.HC_PRIMERA_FILA,h.max_row+1):
                v={k:h[f'{col}{n}'].value for k,col in fmt.HC_COLUMNAS.items()}
                if not any(v.values()):
                    terminada=True
                    continue
                # El pie del formato no es un trámite.
                if not v['no_item'] and not v['tipo_documental']:
                    terminada=True
                    continue
                if terminada: raise ValueError
                if isinstance(v['no_item'],bool) or not re.fullmatch(r'[1-9]\d*',_texto(v['no_item'])): raise ValueError
                if not v['tipo_documental']: raise ValueError
                for k in ('folio_desde','folio_hasta'):
                    if not re.fullmatch(r'[1-9]\d*',_texto(v[k])): raise ValueError
                if int(v['folio_hasta'])<int(v['folio_desde']): raise ValueError
                valor=v['fecha']
                if valor is not None and _texto(valor).upper() not in ('S/F','SF'):
                    if normalizar_fecha(valor).texto is None: raise ValueError
                filas.append({**{k:_texto(x) for k,x in v.items()},'fila':n})
            if not filas: raise ValueError
            desplazamiento=max(0,len(filas)-(fmt.HC_ULTIMA_FILA-fmt.HC_PRIMERA_FILA+1))
            encabezado['fecha_diligenciamiento']=_texto(h[f'D{33+desplazamiento}'].value)
            if not fecha_diligenciamiento_valida(encabezado['fecha_diligenciamiento']).completa: raise ValueError
            resultados.append(HojaImportada(h.title,codigo,encabezado,filas))
        if len({x.codigo_carpeta for x in resultados})!=len(resultados): raise ValueError
        return resultados
    except Exception:
        raise ValueError('Estructura o datos de hoja no admitidos. Libro completo rechazado; no se importó parcialmente.') from None
    finally:
        libro.close()
