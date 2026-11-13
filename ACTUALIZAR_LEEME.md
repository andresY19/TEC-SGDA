# GEOLOGY · Actualización a la versión 2.13 (para el equipo de tecnología)

Este paquete **actualiza la plataforma que ya está en producción**. No es una instalación
nueva. Contiene **únicamente los archivos que cambiaron desde el 30 de septiembre de 2026, ayer y hoy** (código, `Dockerfile`,
`requirements.txt` y documentación). No trae datos, claves ni configuración del servidor.

No hace falta conocer la plataforma. Basta seguir estos pasos en orden. Si algo no coincide
con lo que aquí se dice, **deténgase y avise a Marlín Martínez antes de continuar**; un
paso a medias se puede deshacer, un dato borrado no.

Ruta de la instalación: la carpeta donde está `docker-compose.yml` (en esta guía, `RUTA`).

## 0. Qué cambia y qué no

Los archivos de este paquete se **copian encima** de los existentes, conservando la misma
ubicación relativa (`geology/...`, `scripts/...`, `docs/...`, `Dockerfile`, `requirements.txt`).
**No se borra ninguna carpeta.** Los archivos de `RUTA` que no están en este paquete
quedan como están.

**No se toca, bajo ninguna circunstancia:**

- `.env` (claves y configuración del servidor).
- `deposito/` (documentos digitalizados) y `expedidos/`.
- `datos/` (inventario y plantillas existentes; solo se agregan tres plantillas nuevas con `cp -n`, que no pisa nada).
- `docker-compose.yml` (esta versión no lo modifica).
- Los volúmenes de Docker de la base de datos y de Redis.

**Comandos prohibidos en esta operación:** `docker compose down -v`, `docker volume rm`,
`docker system prune --volumes`, `rm -rf geology`, y los scripts `cargar_inventario.py`,
`crear_usuarios.py`, `cargar_contexto.py`, `vaciar_flujo.py`, `limpiar_fantasmas.py`,
`migrar_plataforma_anterior.py`.

## 1. Cuándo hacerlo

Hoy, sin cargues en curso (Marlín no usará la plataforma durante el día). La plataforma
quedará fuera de servicio unos minutos mientras se reconstruye. Los trabajos pendientes no
se pierden (Redis los guarda).

## 2. Respaldo (obligatorio)

```bash
cd RUTA
mkdir -p ~/respaldo_geology
docker compose exec -T almacen_datos pg_dump -U geology geology > ~/respaldo_geology/base_$(date +%F).sql
tar czf ~/respaldo_geology/codigo_anterior_$(date +%F).tgz geology scripts Dockerfile requirements.txt docs .env docker-compose.yml
```

Si el usuario o la base no se llaman `geology` (revise `PG_USUARIO` y `PG_BASE` en `.env`),
use esos nombres. Compruebe que `base_*.sql` no pesa 0 bytes. Si hay espacio, respalde
también los documentos: `tar czf ~/respaldo_geology/deposito_$(date +%F).tgz deposito`.

## 3. Copiar los archivos nuevos

Descomprima este paquete en una carpeta temporal (por ejemplo `/tmp/act`) y copie su
contenido sobre `RUTA` **sin borrar nada**:

```bash
cd RUTA
cp -r /tmp/act/GEOLOGY_ACTUALIZACION_2.13/geology  .
cp -r /tmp/act/GEOLOGY_ACTUALIZACION_2.13/scripts  .
cp -r /tmp/act/GEOLOGY_ACTUALIZACION_2.13/docs     .
# Plantillas oficiales nuevas (F-GDM-004, F-GDM-009 y F-FIN-007). Con -n no se pisa ningún archivo existente de datos/.
mkdir -p datos/formatos_sgc && cp -n /tmp/act/GEOLOGY_ACTUALIZACION_2.13/datos/formatos_sgc/* datos/formatos_sgc/
cp /tmp/act/GEOLOGY_ACTUALIZACION_2.13/Dockerfile /tmp/act/GEOLOGY_ACTUALIZACION_2.13/requirements.txt .
```

(`cp -r` fusiona las carpetas: reemplaza los archivos que coinciden y deja los demás.)

## 4. Variables nuevas en `.env`

Abra el `.env` **existente** y agregue al final las líneas siguientes que no estén ya. No
borre ni cambie nada de lo que ya tiene.

```
RIGOR_TOMOS=1
RIGOR_PROVEEDOR=gemini
PAGINAS_RIGOR=60
TOPE_PAGINAS_RIGOR=60
PDFA_PERFIL=1b
RIGOR_RESPALDO=1
CUOTA_GEMINI_PAGA=20000
META_CAJAS=1020
FECHA_FIN_CONTRATO=2026-12-31
```

La llave **paga** de Gemini la identifica Marlín desde la plataforma (Centro de control > «Marcar la llave paga»); no hace falta ponerla aparte en el `.env`. Las gratuitas se usan primero y la paga queda de reserva.

Además, deje **una sola vez** `CUOTA_GEMINI=5000` (valor alto). A partir de ahí, Marlín cambia el
tope y reactiva los modelos desde la propia plataforma (Avance > Modelos de lenguaje), así que
no hará falta volver a tocar el `.env` para esto. Las llaves (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`) las
administra Marlín: no las pida por correo ni las pegue en chats.

## 5. Reconstruir y reiniciar

```bash
cd RUTA
docker compose up -d --build
```

Esta versión agrega `python-docx` y `python-pptx` (informes en Word y PowerPoint), por eso el `--build` es obligatorio. La construcción tarda más que antes: instala Java y el validador de PDF/A (veraPDF) y lo
descarga de `software.verapdf.org`, por lo que el servidor necesita salida a internet.
**Si la construcción falla, los contenedores anteriores siguen funcionando**: guarde el
mensaje de error y envíelo a Marlín.

Las tablas se ajustan solas al arrancar (se agregan dos columnas nuevas, `definitiva` en los archivos y `sin_limites` y `aprueba_lo_propio` en las cuentas, y se
crean catorce tablas nuevas vacías (`sesion_edicion`, `alerta`, `descarga_registro`, `documento_apoyo`, `asignacion`, `hito_cronograma`, `pago_contrato`, `parametro_contrato`, `lote_contrato`, `obligacion_contrato`, `observacion_supervision`, `documento_contrato`, `proceso_eliminacion`, `item_eliminacion`); no se borra ni se modifica ningún dato).

Este paquete es **acumulativo**: incluye todo lo de la 2.12 (cobro, acta oficial y testigo) y lo nuevo de la 2.13
(avisos de edición simultánea, registro de descargas e inventario de documentos de apoyo). Si la 2.12 no se instaló, no
hace falta instalarla antes.

## 6. Verificación

```bash
docker compose ps                                              # los 4 servicios en "running/healthy"
docker compose exec almacen_datos psql -U geology -d geology -c "\dt" | grep -E "sesion_edicion|alerta|descarga_registro|documento_apoyo"   # las 4 tablas nuevas
curl -s http://localhost:8080/estado                           # responde sin error y dice "version":"2.13.0"
docker compose exec servidor /opt/verapdf/verapdf --version   # imprime la versión de veraPDF
docker compose exec servidor python -c "import img2pdf, docx, pptx; print('ok')"
docker compose logs --tail=50 servidor procesador              # sin errores (Traceback)
docker compose exec procesador python scripts/revisar_motor.py # todo en verde
docker compose exec almacen_datos psql -U geology -d geology -c "\d archivo_digital" | grep definitiva
docker compose exec almacen_datos psql -U geology -d geology -c "\d cuenta" | grep -E "sin_limites|aprueba_lo_propio"
ls datos/formatos_sgc | grep -E "F-GDM-004|F-GDM-009|F-FIN-007"   # deben aparecer los tres
docker compose exec almacen_datos psql -U geology -d geology -c "\dt" | grep -E "asignacion|hito_cronograma|lote_contrato|documento_contrato|proceso_eliminacion"
```

Si todo responde, avise a Marlín: ella hará la prueba funcional en
https://geology.hometicsa.com/app con un tomo corto.

## 7. Vuelta atrás (si algo falla y no se resuelve rápido)

```bash
cd RUTA
tar xzf ~/respaldo_geology/codigo_anterior_FECHA.tgz
docker compose up -d --build
```

Esto devuelve los archivos a su estado anterior. La base de datos **no necesita
restauración**: la actualización solo agrega columnas y tablas vacías. Restaurar `base_FECHA.sql`
solo se hace ante pérdida de datos y con autorización de Marlín.

## 8. Qué debe saber, en pocas líneas

- La plataforma tiene 4 servicios: base de datos (PostgreSQL), mensajería (Redis), servidor web
  y procesador (Celery). El procesador es el que lee los documentos; si se cae, la web sigue
  pero las hojas de control no se generan.
- El código se monta desde las carpetas del servidor, pero el `--build` es necesario esta vez
  porque cambian las dependencias.
- El proxy debe permitir cargas amplias (hasta 2 GB) con tiempos de espera largos.
- Detalle completo en `docs/DESPLIEGUE.md` y `docs/MANUAL.md`.
