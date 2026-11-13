"""Fechas locales conservadoras; orden original del libro, sin inferir encuadernación."""
from geology.dominio.fechas import normalizar_fecha, FechaNormalizada


def resolver_fechas(tramites, unidad=None, encuadernada=None, periodo_inicio=None, periodo_fin=None):
    fechas=[]
    for t in tramites:
        valor=getattr(t,'fecha',None) or getattr(t,'fecha_texto',None)
        f=valor if isinstance(valor,FechaNormalizada) else normalizar_fecha(valor)
        fechas.append(f.completa)
    avisos=[]
    if encuadernada is None:
        return None,None,'S/F',None,['Encuadernación no determinada; requiere revisión humana.']
    if not fechas or (encuadernada and (not fechas[0] or not fechas[-1])):
        return None,None,'S/F',encuadernada,['No hay extremos completos suficientes; requiere revisión humana.']
    completas=[f for f in fechas if f]
    if not completas:
        return None,None,'S/F',encuadernada,['Sin fechas completas; requiere revisión humana.']
    fi,ff=(fechas[0],fechas[-1]) if encuadernada else (min(completas),max(completas))
    if fi>ff or any(f<fi or f>ff for f in completas):
        return None,None,'S/F',encuadernada,['Fechas contradictorias con el orden original; requiere revisión humana.']
    if (periodo_inicio and fi<periodo_inicio) or (periodo_fin and ff>periodo_fin):
        return None,None,'S/F',encuadernada,['Las fechas contradicen el período asignado; requiere revisión humana.']
    if len(completas)!=len(fechas): avisos.append('Hay trámites sin fecha completa; requiere revisión humana.')
    return fi,ff,f'{fi.isoformat()} / {ff.isoformat()}',encuadernada,avisos
