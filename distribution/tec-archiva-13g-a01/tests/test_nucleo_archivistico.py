"""Reglas locales conservadoras: datos sintéticos, sin ORM, archivos o IA."""
import ast
import copy
import dataclasses
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from geology.dominio import periodos as p, clasificacion as c, verificar_hoja as v
from geology.dominio.fechas import normalizar_fecha
from geology.dominio.folios import Tramite
from geology.dominio.estados import Estado

ROOT = Path(__file__).resolve().parents[1]


def catalogo():
    return [p.RangoPeriodo('I',date(1900,1,1),date(1909,12,31)),
            p.RangoPeriodo('II',date(1910,1,1),date(1919,12,31))]


def opcion(dep='001', periodo='I'):
    return c.OpcionTvd(periodo,'01','Serie sintética','02','Subserie sintética',5,'CT',dep,'Oficina sintética')


class Periodos(unittest.TestCase):
    def test_01_intervalo_completo(self):
        r=p.resolver_por_fechas(date(1900,1,1),date(1909,12,31),catalogo())
        self.assertEqual((r.romano,r.origen,r.resuelto,r.requiere_persona),('I','fechas',True,False))

    def test_02_fecha_unica_completa(self):
        self.assertEqual(p.resolver_por_fechas(date(1910,1,1),date(1910,1,1),catalogo()).romano,'II')

    def test_03_fecha_parcial_no_inventa_dia(self):
        r=p.resolver_periodo('I',normalizar_fecha('1902'),normalizar_fecha('1903'),catalogo())
        self.assertFalse(r.resuelto); self.assertTrue(r.requiere_persona)

    def test_04_extremo_ausente(self):
        r=p.resolver_periodo('I',date(1901,1,1),None,catalogo())
        self.assertFalse(r.resuelto)

    def test_05_cruce_no_escoge_inicial(self):
        r=p.resolver_periodo('I',date(1909,1,1),date(1910,1,1),catalogo())
        self.assertFalse(r.resuelto); self.assertIn('cruzan',r.aviso)

    def test_06_discrepancia_gana_fecha(self):
        r=p.resolver_periodo('I',date(1911,1,1),date(1912,1,1),catalogo())
        self.assertEqual(r.romano,'II'); self.assertIn('inventario',r.discrepancia)

    def test_07_manual_explicito_prevalece(self):
        r=p.resolver_periodo('I',date(1901,1,1),date(1902,1,1),catalogo(),'II')
        self.assertEqual((r.romano,r.origen),('II',p.ORIGEN_MANUAL))

    def test_08_manual_desconocido_no_cae_a_fechas(self):
        self.assertFalse(p.resolver_periodo('I',date(1901,1,1),date(1902,1,1),catalogo(),'XX').resuelto)

    def test_09_inventario_sin_fechas_no_certifica(self):
        r=p.resolver_periodo(' i ',None,None,catalogo())
        self.assertEqual((r.romano,r.origen),('I',p.ORIGEN_INVENTARIO))
        self.assertTrue(r.requiere_persona)

    def test_10_sugerencia_no_asigna(self):
        r=p.resolver_periodo('S/F',None,None,catalogo(),sugerencia_caja=('I','mayoría de caja'))
        self.assertFalse(r.resuelto); self.assertIn('sugerencia',r.aviso)

    def test_11_catalogo_superpuesto(self):
        rangos=catalogo()+[p.RangoPeriodo('III',date(1900,1,1),date(1919,12,31))]
        self.assertFalse(p.resolver_por_fechas(date(1902,1,1),date(1903,1,1),rangos).resuelto)

    def test_12_catalogo_incompleto(self):
        for rangos in ([],[p.RangoPeriodo('I',None,None)],[p.RangoPeriodo('I',date(1910,1,1),date(1900,1,1))]):
            self.assertFalse(p.resolver_por_fechas(date(1902,1,1),date(1903,1,1),rangos).resuelto)

    def test_13_fechas_invertidas_fuera_y_texto_no_ejecutable(self):
        for inicio,fin in ((date(1903,1,1),date(1902,1,1)),(date(1800,1,1),date(1801,1,1)),
                           ('__import__("os").system("x")',None)):
            self.assertFalse(p.resolver_periodo('I',inicio,fin,catalogo()).resuelto)

    def test_14_no_modifica_catalogo(self):
        rangos=catalogo(); antes=copy.deepcopy(rangos)
        p.resolver_periodo('',date(1901,1,1),date(1902,1,1),rangos)
        self.assertEqual(rangos,antes)

    def test_15_identificador_duplicado_aun_sin_solapamiento(self):
        rangos=[p.RangoPeriodo('I',date(1900,1,1),date(1909,12,31)),
                p.RangoPeriodo('I',date(1910,1,1),date(1919,12,31))]
        self.assertFalse(p.resolver_por_fechas(date(1901,1,1),date(1902,1,1),rangos).resuelto)

    def test_16_hueco_entre_periodos_no_asigna(self):
        rangos=[p.RangoPeriodo('I',date(1900,1,1),date(1904,12,31)),
                p.RangoPeriodo('II',date(1910,1,1),date(1919,12,31))]
        self.assertFalse(p.resolver_por_fechas(date(1905,1,1),date(1906,1,1),rangos).resuelto)

    def test_17_catalogo_como_generador(self):
        r=p.resolver_periodo('',date(1901,1,1),date(1902,1,1),(r for r in catalogo()))
        self.assertEqual(r.romano,'I')


class Clasificacion(unittest.TestCase):
    def test_01_codigos_completos(self):
        o=opcion(); r=c.asimilar_encabezado(c.Encabezado('01','','02'),[o])
        self.assertTrue(r.alineada); self.assertIs(r.opcion,o)

    def test_02_codigos_no_son_numeros(self):
        self.assertIsNone(c.elegir_de_la_lista([opcion()],'1','2'))

    def test_03_dependencia_desambigua(self):
        a,b=opcion('001'),opcion('002')
        self.assertIs(c.elegir_de_la_lista([a,b],'01','02',codigo_dependencia='002'),b)
        h=c.Encabezado('01','','02',codigo_dependencia='002')
        self.assertIs(c.asimilar_encabezado(h,[a,b]).opcion,b)

    def test_04_ambigua_sin_dependencia(self):
        self.assertIsNone(c.elegir_de_la_lista([opcion('001'),opcion('002')],'01','02'))

    def test_05_dependencia_desconocida_no_fallback(self):
        self.assertIsNone(c.elegir_de_la_lista([opcion()],'01','02',codigo_dependencia='999'))

    def test_06_encabezado_incompleto(self):
        for h in (c.Encabezado(),c.Encabezado('01'),c.Encabezado(serie='Serie sintética',subserie='Subserie sintética')):
            r=c.asimilar_encabezado(h,[opcion()]); self.assertTrue(r.requiere_persona); self.assertFalse(r.alineada)

    def test_07_etiqueta_discrepante(self):
        for h in (c.Encabezado('01','Otra serie','02'),c.Encabezado('01','','02','Otra subserie')):
            self.assertFalse(c.asimilar_encabezado(h,[opcion()]).alineada)

    def test_08_duplicado_identico_no_se_deduplica(self):
        self.assertIsNone(c.elegir_de_la_lista([opcion(),opcion()],'01','02'))

    def test_09_no_fuzzy_ni_frecuencia(self):
        r=c.elegir_por_contenido([opcion()],['Subserie sintética'],{'001|01|02':999})
        self.assertFalse(r.hay); self.assertTrue(r.requiere_persona); self.assertIsNone(r.como_dict())
        self.assertIn('revisión humana',r.frase())

    def test_10_eleccion_compatible(self):
        e=c.Eleccion(opcion(),'Propuesta sintética',c.CONFIANZA_MEDIA,'inventario')
        self.assertTrue(e.hay); self.assertEqual(e.como_dict()['cod_subserie'],'02')
        self.assertTrue(e.como_dict()['requiere_persona']); json.dumps(e.como_dict())

    def test_11_seguridad_no_modifica_entrada(self):
        opciones=[opcion()]; antes=copy.deepcopy(opciones)
        c.elegir_por_contenido(opciones,['=SUM(A1:A2)','<script>alert(1)</script>'])
        self.assertEqual(opciones,antes)

    def test_12_contrato_posicional_y_rotulo(self):
        o=opcion(); self.assertEqual(o.retencion_central_anios,5)
        self.assertEqual(o.disposicion_final,'CT'); self.assertIn('001',str(o))


class Verificacion(unittest.TestCase):
    def datos(self):
        lectura=v.Lectura(c.Encabezado('01','Serie sintética','02','Subserie sintética','Expediente sintético'),
            [Tramite(fecha=normalizar_fecha('1901-01-01'),tipo_documental='Acta sintética',
                folio_desde_leido='1',folio_hasta_leido='2',fila=7)],'Persona sintética','2026-01-01')
        return lectura,v.UnidadInventario('CP-00001','I',2,'Asunto','CJ-1')

    def verificar(self,lectura,unidad): return v.verificar_hoja(lectura,unidad,[opcion()])

    def test_01_normal_solo_pendiente_humano(self):
        lectura,unidad=self.datos(); r=self.verificar(lectura,unidad)
        self.assertEqual(r.errores,[]); self.assertTrue(r.alineada)
        self.assertEqual(r.estado_resultante,Estado.HOJA_POR_REVISAR)
        self.assertTrue(r.requiere_persona)
        self.assertEqual((r.tramites,r.folios),(1,2))

    def test_02_normaliza_calculo_compatible_con_guardado(self):
        lectura,unidad=self.datos(); self.verificar(lectura,unidad)
        self.assertEqual((lectura.tramites[0].no_item,lectura.tramites[0].folio_desde,lectura.tramites[0].folio_hasta),(1,1,2))

    def test_03_no_cambia_inventario(self):
        lectura,unidad=self.datos(); antes=copy.deepcopy(unidad); self.verificar(lectura,unidad)
        self.assertEqual(unidad,antes)

    def test_04_diferencia_folios_es_constancia(self):
        lectura,unidad=self.datos(); unidad=dataclasses.replace(unidad,folios=3)
        r=self.verificar(lectura,unidad)
        self.assertTrue(r.diferencia_folios); self.assertFalse(r.errores)

    def test_05_folios_invertidos_error_localizado(self):
        lectura,unidad=self.datos(); lectura.tramites[0].folio_hasta_leido='0'
        r=self.verificar(lectura,unidad)
        self.assertTrue(r.errores); self.assertEqual(r.estado_resultante,Estado.HOJA_EN_ELABORACION)
        self.assertEqual(r.errores_localizados[0].fila,7)

    def test_06_tramite_sin_fecha_no_inventa(self):
        lectura,unidad=self.datos(); lectura.tramites[0].fecha=normalizar_fecha(None)
        r=self.verificar(lectura,unidad)
        self.assertIsNone(lectura.tramites[0].fecha.completa)
        self.assertTrue(any('SF' in o for o in r.observaciones))

    def test_07_fecha_parcial_se_conserva_como_sf_en_hoja(self):
        lectura,unidad=self.datos(); lectura.tramites[0].fecha=normalizar_fecha('1901')
        self.verificar(lectura,unidad)
        self.assertTrue(lectura.tramites[0].fecha.sin_fecha)

    def test_08_sin_tramites(self):
        lectura,unidad=self.datos(); lectura.tramites=[]
        self.assertTrue(self.verificar(lectura,unidad).errores)

    def test_09_tipo_documental_vacio(self):
        lectura,unidad=self.datos(); lectura.tramites[0].tipo_documental=''
        self.assertTrue(any(e.campo=='tipo_documental' for e in self.verificar(lectura,unidad).errores_localizados))

    def test_10_folio_ilegible(self):
        lectura,unidad=self.datos(); lectura.tramites[0].folio_desde_leido='ilegible'
        self.assertTrue(self.verificar(lectura,unidad).errores)

    def test_11_tvd_de_otro_periodo(self):
        lectura,unidad=self.datos()
        r=v.verificar_hoja(lectura,unidad,[opcion(periodo='II')])
        self.assertFalse(r.alineada); self.assertTrue(r.errores)

    def test_12_sin_periodo_y_encabezado(self):
        lectura,unidad=self.datos(); lectura.encabezado=c.Encabezado()
        r=self.verificar(lectura,dataclasses.replace(unidad,periodo=''))
        self.assertTrue(r.errores); self.assertFalse(r.alineada)

    def test_13_diligenciamiento_y_responsable(self):
        lectura,unidad=self.datos(); lectura.fecha_diligenciamiento='1901-01-01'; lectura.responsable=''
        self.assertGreaterEqual(len(self.verificar(lectura,unidad).errores),2)

    def test_14_error_tardio_actualiza_propuesta_de_estado(self):
        lectura,unidad=self.datos(); r=self.verificar(lectura,unidad)
        r.errores.append('Cruce de períodos detectado por consumidor')
        self.assertEqual(r.estado_resultante,Estado.HOJA_EN_ELABORACION)

    def test_15_rechaza_entidad_ajena_sin_mutarla(self):
        lectura,unidad=self.datos(); objeto=SimpleNamespace(estado='Original')
        lectura.tramites=[objeto]
        with self.assertRaises(TypeError): self.verificar(lectura,unidad)
        self.assertEqual(objeto.estado,'Original')

    def test_16_contrato_respuesta_json(self):
        lectura,unidad=self.datos(); r=self.verificar(lectura,unidad)
        json.dumps({'errores':r.errores,'errores_localizados':[dataclasses.asdict(e) for e in r.errores_localizados],
            'observaciones':r.observaciones,'subserie':str(r.clasificacion.opcion),'tramites':r.tramites,
            'folios':r.folios,'mensaje':r.detalle('Persona')})

    def test_17_continuidad_y_reintento(self):
        lectura,unidad=self.datos()
        lectura.tramites.append(Tramite(fecha=normalizar_fecha('1902-01-01'),tipo_documental='Oficio sintético',
            folio_desde_leido='3',folio_hasta_leido='4'))
        unidad=dataclasses.replace(unidad,folios=4)
        a=self.verificar(lectura,unidad); b=self.verificar(lectura,unidad)
        self.assertEqual(a.errores,[]); self.assertEqual(b.errores,[])
        self.assertEqual((a.folios,b.folios),(4,4))

    def test_18_ambiguedad_tvd_bloquea_verificacion(self):
        lectura,unidad=self.datos()
        r=v.verificar_hoja(lectura,unidad,[opcion('001'),opcion('002')])
        self.assertFalse(r.alineada); self.assertEqual(r.estado_resultante,Estado.HOJA_EN_ELABORACION)


class Consumidores(unittest.TestCase):
    def test_01_propuesta_exacta_del_consumidor_real(self):
        tree=ast.parse((ROOT/'geology/rutas/unidades.py').read_text(encoding='utf-8-sig'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_proponer_subserie')
        import __future__
        ns={'Encabezado':c.Encabezado,'_opciones_tvd':lambda db,romano:[opcion()]}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'consumidor_real','exec',flags=__future__.annotations.compiler_flag),ns)
        unidad=SimpleNamespace(cod_serie='01',serie='Serie sintética',cod_subserie='02',subserie='Subserie sintética')
        propuesta,porque,seguridad=ns['_proponer_subserie'](None,unidad,'I')
        self.assertEqual(propuesta['codigo_dependencia'],'001'); self.assertEqual(seguridad,c.CONFIANZA_MEDIA)

    def test_02_consulta_tvd_real_construye_opciones(self):
        tree=ast.parse((ROOT/'geology/rutas/unidades.py').read_text(encoding='utf-8-sig'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_opciones_tvd')
        ret=next(n for n in fn.body if isinstance(n,ast.Return))
        ns={'OpcionTvd':c.OpcionTvd,'consulta':SimpleNamespace(all=lambda:[('I','01','Serie','02','Subserie',5,'CT','001','Oficina')])}
        valor=eval(compile(ast.Expression(body=ret.value),'contrato_tvd','eval'),ns)
        self.assertEqual(valor[0].codigo_dependencia,'001')

    def test_03_sin_operaciones_externas(self):
        with patch('socket.socket.connect',side_effect=AssertionError), patch('builtins.open',side_effect=AssertionError):
            p.resolver_periodo('I',None,None,catalogo())
            c.elegir_por_contenido([opcion()],['Texto sintético'])
            lectura,unidad=Verificacion().datos(); v.verificar_hoja(lectura,unidad,[opcion()])


if __name__=='__main__': unittest.main()
