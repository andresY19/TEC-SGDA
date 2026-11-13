# GEOLOGY · Despliegue

Para el equipo de ingeniería. La plataforma corre completa en Docker Compose; no hay que
instalar nada más en el servidor.

## 1. Servicios

| Servicio        | Imagen / build            | Función                                                     |
|-----------------|---------------------------|-------------------------------------------------------------|
| `almacen_datos` | postgres:15               | Base de datos única.                                        |
| `mensajeria`    | redis:7-alpine            | Cola de trabajos en segundo plano.                          |
| `servidor`      | Dockerfile (python 3.11)  | API + interfaz web en el puerto 8080.                       |
| `procesador`    | mismo Dockerfile          | Celery: lectura de expedientes, recepción técnica, división de documentos. |

Volúmenes en el equipo anfitrión: `./deposito` (documentos digitalizados), `./expedidos`
(instrumentos expedidos), `./datos` (inventario, plantillas), `./.env`.

## 2. Instalación

```bash
git clone <repositorio> geology && cd geology      # o descomprima GEOLOGY.zip
cp .env.example .env
```

Edite `.env`:

- `PG_CLAVE` y la misma clave dentro de `DATABASE_URL`.
- `GEOLOGY_CLAVE`: una cadena larga y propia. Firma las sesiones. Sin ella, las sesiones
  caen en cada reinicio.
- `GEOLOGY_ENTORNO=produccion` en cuanto la plataforma salga del equipo de pruebas: cierra
  `/docs` y activa la cabecera HSTS.
- `ORIGENES_PERMITIDOS`: la URL pública de la plataforma (por ejemplo `https://geology.hometic.com.co`).
- Llaves de los lectores (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`). Se pueden
  poner varias por proveedor, numeradas. Sin llaves la plataforma funciona, pero las hojas de
  control se diligencian a mano o se importan desde Excel.

```bash
docker compose up -d --build
docker compose exec servidor python scripts/cargar_inventario.py
docker compose exec servidor python scripts/cargar_contexto.py
cp datos/equipo.ejemplo.csv datos/equipo.csv     # edite el equipo
docker compose exec servidor python scripts/crear_usuarios.py
docker compose exec procesador python scripts/revisar_motor.py
```

`revisar_motor.py` comprueba en diez segundos lo que cuesta un día descubrir: que el
procesador ve el depósito, que hay llaves y responden, que el motor de imagen está y que
Redis responde.

## 3. Publicación en internet

Ponga un proxy inverso con TLS delante del puerto 8080 (Nginx, Caddy o Traefik). Ejemplo
mínimo con Caddy:

```
geology.hometic.com.co {
    reverse_proxy localhost:8080
    request_body { max_size 2GB }
}
```

El tamaño máximo de carga importa: un libro digitalizado entero puede pesar más de un
gigabyte. Ajuste `client_max_body_size` (Nginx) o `max_size` (Caddy) y los tiempos de
espera del proxy (un cargue grande puede tardar minutos).

## 4. Migración desde la plataforma anterior

Si ya hay trabajo hecho en la plataforma anterior (misma estructura de datos, otros nombres
de tabla), se trae completo: expedientes, hojas, descripciones, cajas, bitácora y cuentas.

```bash
# En el servidor anterior
docker compose exec db pg_dump -U <usuario> --no-owner --no-privileges <base> > respaldo_anterior.sql
# y copie la carpeta «almacen» con los documentos.

# En GEOLOGY, con la base vacía
docker compose up -d almacen_datos
docker compose run --rm servidor python scripts/migrar_plataforma_anterior.py --preparar
docker compose exec -T almacen_datos psql -U geology -d geology < respaldo_anterior.sql
docker compose run --rm servidor python scripts/migrar_plataforma_anterior.py --renombrar --almacen /ruta/al/almacen
docker compose up -d
```

El script renombra las tablas, agrega las columnas nuevas, corrige las rutas del depósito y
copia los documentos. Las cuentas migradas conservan sus contraseñas.

## 5. Respaldo

```bash
docker compose exec almacen_datos pg_dump -U geology geology > respaldo_$(date +%F).sql
tar czf deposito_$(date +%F).tgz deposito
```

La base y el depósito son lo único que hay que respaldar. Todo lo demás se reconstruye
desde el código.

## 6. Actualización

```bash
git pull            # o reemplace la carpeta geology/ y scripts/
docker compose up -d --build
```

Los cambios de estructura de tablas se aplican solos al arrancar (`geology/nucleo/estructura.py`);
nunca borran datos.

## 7. Variables que conviene conocer

| Variable                   | Por defecto | Para qué                                                     |
|----------------------------|-------------|--------------------------------------------------------------|
| `PAGINAS_POR_PARTE`        | 250         | Un archivo con más páginas se divide solo en partes consecutivas. 0 lo apaga. |
| `SEGUNDOS_ANTES_DE_LEER`   | 45          | Espera para que lleguen todas las partes de un expediente antes de leerlo. |
| `TOPE_PAGINAS_POR_ARCHIVO` | 100         | Páginas por petición al lector; por encima se lee por bloques en memoria. |
| `TOPE_MB_POR_ARCHIVO`      | 30          | Peso por petición al lector.                                 |
| `TRABAJADORES_EN_PARALELO` | 6           | Expedientes que se leen a la vez (póngalo igual al número de llaves). |
| `LEVANTAR_AL_CARGAR`       | si          | La lectura arranca sola al cargar. `no` = botón manual.      |
| `UMBRAL_DPI`               | 0           | Resolución mínima exigida en la recepción técnica.           |
| `RIGOR_TOMOS`              | 1           | Los archivos de más de `PAGINAS_RIGOR` páginas los lee solo `RIGOR_PROVEEDOR`, por bloques. |
| `RIGOR_PROVEEDOR`          | gemini      | Lector de los tomos extensos. Solo actúa si ese proveedor tiene llave. |
| `RIGOR_RESPALDO`           | 1           | Si el proveedor del modo riguroso se queda sin cuota a mitad de un tomo, otro modelo lee los bloques que faltan. `0` = el tomo espera. |
| `PAGINAS_RIGOR`            | 60          | Páginas desde las cuales un archivo se lee en modo rigor.    |
| `TOPE_PAGINAS_RIGOR`       | 60          | Páginas por bloque en modo rigor.                            |
| `CUOTA_GEMINI`             | (ver .env)  | Cuota diaria de Gemini; súbala cuando se recargue la llave.  |
| `CUOTA_GEMINI_PAGA`        | 20000       | Tope diario por modelo de la llave paga de Gemini.           |
| `GEMINI_API_KEY_PAGA`      | (vacía)     | La llave paga de Gemini. Se usa de reserva, después de las gratuitas. |
| `META_CAJAS`               | 1020        | Cajas del contrato, para el cálculo «¿alcanzan las llaves?». |
| `FECHA_FIN_CONTRATO`       | 2026-12-31  | Cierre del contrato, para ese mismo cálculo.                 |
| `PETICIONES_EXTRA_POR_CARPETA` | 1       | Peticiones adicionales por carpeta (la revisión).            |
| `CALIDAD_DPI_MINIMO`       | 300         | Resolución mínima del control de calidad de imagen (AGN).    |
| `VERAPDF_BIN`              | /opt/verapdf/verapdf | Validador PDF/A. Ya viene instalado en la imagen.   |
| `PDFA_PERFIL`              | 1b          | Perfil PDF/A exigido (la guía GU-SAD-ODA-001 menciona PDF/A-1). Confirmar por escrito con el Servicio Geológico. |
| `SEGUNDOS_VERAPDF`         | (ver .env)  | Tiempo máximo de validación por archivo.                     |
| `MAX_EXPEDIENTES_POR_ENTREGA` | 40       | Expedientes por paquete de entrega.                          |

## 8. Problemas frecuentes

**El cargue dice que la carpeta no está en el inventario.** Solo se reciben carpetas del
inventario de origen del contrato. Cargue el inventario (`cargar_inventario.py`) o revise el
nombre del archivo (`AC-CP-00374.pdf`, `CARPETA_00374.pdf`, `carpeta-00374- 2.pdf`).

**La hoja no se levanta sola.** `docker compose logs procesador`. Casi siempre es una llave
mal escrita o sin cuota: `revisar_motor.py` lo dice.

**Un cargue grande falla por el proxy.** Suba el tamaño máximo del cuerpo y los tiempos de
espera del proxy inverso (sección 3).

**Se cambió una llave en .env y no la toma.** `docker compose up -d --force-recreate servidor procesador`.

## 9. Aceptación (prueba de humo antes de entregar)

1. `docker compose exec servidor /opt/verapdf/verapdf --version` responde.
2. `revisar_motor.py` en verde (llaves, depósito, Redis, motor de imagen).
3. Ingreso como administradora y como cuenta de la entidad.
4. Cargue de un PDF corto, un PDF/A y varias fotos JPG: la hoja de control se levanta.
5. Imágenes del escáner con «definitivas» y «reemplazar»: la hoja se conserva.
6. Panel de calidad abre y el informe Excel se descarga.
7. Paquete de entrega de un expediente: revisar ZIP, índice, hashes y acta.
8. Cuenta de la entidad: ve el tomo completo en un solo PDF, sin metadatos de proceso, y no ve acciones de administración.

## 10. Lo que debe saber quien opera la plataforma

- Las fotos de cámara son imágenes de trabajo (sirven para avanzar la hoja). Solo las
  imágenes del escáner marcadas como definitivas entran al paquete de entrega.
- Un JPG no puede ser matriz conforme: el escáner debe exportar TIFF.
- La validación y conversión a PDF/A de tomos de 1000 páginas es lenta: genere los
  paquetes fuera del horario de trabajo.
- Fecha incompleta se registra como SF; nunca se deduce.
- La entidad no debe ver rastro de procesamiento (metadatos limpios por diseño).
- La validación automática de calidad es una ayuda de tamizaje; el acta la firman las
  personas responsables tras la revisión visual.
- Pendiente de confirmar por escrito con el Servicio Geológico: PDF/A-1 o 2, escala de
  grises 8 bits o color 24 bits, y si «subsección» equivale a oficina productora.
- Las pruebas se hicieron con datos sintéticos: haga un piloto con un tomo real corto.

## 11. Actualizar una plataforma que ya está en producción (de la versión anterior a la 2.9)

Aplica cuando ya hay una instalación publicada con datos reales.

1. **Respaldo antes de tocar nada** (sección 5) y, si es posible, instantánea del servidor.
2. **No reemplazar** `.env`, `deposito/`, `expedidos/` ni `datos/`: son de la instalación en uso. El zip no trae `.env` ni `deposito/`.
3. Reemplazar solo `geology/`, `scripts/`, `Dockerfile`, `requirements.txt`, `docker-compose.yml` (comparar antes con el actual), `README.md` y `docs/`.
4. Comparar `.env.example` con el `.env` vigente y **agregar las variables nuevas** (sección 7). No borrar las existentes.
5. `docker compose up -d --build`. La reconstrucción es más larga porque instala Java y veraPDF.
6. La tabla `archivo_digital` recibe la columna `definitiva` sola al arrancar (no borra datos). Revisar con `docker compose logs servidor` que no haya errores.
7. **No volver a ejecutar** `cargar_inventario.py`, `crear_usuarios.py`, `cargar_contexto.py`, `vaciar_flujo.py`, `limpiar_fantasmas.py` ni `migrar_plataforma_anterior.py` sobre la base en uso, salvo que se confirme que son seguros.
8. Ejecutar la prueba de aceptación (sección 9) con un tomo corto. Las carpetas ya cargadas antes quedan como imágenes de trabajo hasta que se carguen las del escáner marcadas como definitivas.
9. Plan de vuelta atrás: restaurar la copia de la base y volver a la carpeta de código anterior.
