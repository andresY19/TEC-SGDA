# GEOLOGY · Manual de uso

## Perfiles

| Perfil          | Qué ve                                                                 | Qué hace |
|-----------------|------------------------------------------------------------------------|----------|
| administradora  | Todas las pestañas, incluidas Consulta y Cuentas                       | Aprueba descripciones, retira expedientes, administra cuentas y habilitaciones |
| lider           | Inicio, Cargue, Hojas de control, Proceso, Revisión, Localización, Reubicación, Instrumentos, Calidad, Centro de control | Aprueba descripciones |
| equipo          | Las mismas, según su función (Hoja de control, Descripción o Ambas)    | Carga, diligencia y revisa hojas; genera y valida descripciones |
| consulta        | Localización, Instrumentos, Calidad, Centro de control                 | Auditoría interna; no interviene expedientes |
| entidad         | Únicamente Consulta                                                     | Servicio Geológico: descarga hojas de control, ISAD(G) y FUID; ve imágenes si se le habilita |

## Flujo de un expediente

1. **Cargue.** Se suelta el documento digitalizado. El nombre del archivo lleva el código de
   carpeta (`AC-CP-00374.pdf`, `CARPETA_00374.pdf`, `carpeta-00374- 2.pdf`). Solo entran
   carpetas del inventario de origen del contrato. La recepción técnica mide páginas,
   resolución y capa de texto y lo deja anotado.
2. **Lectura.** En segundo plano, la plataforma lee el documento y propone la hoja de control:
   trámites, fechas, tipos documentales, foliación. Queda en *Hoja de control en elaboración*.
   Si no hay lector disponible, la hoja se diligencia a mano en la pestaña Hojas de control o
   se importa desde Excel.
3. **Verificación.** Al guardar la hoja, la plataforma corrige lo corregible (rangos de folios,
   numeración) y contrasta con el inventario. Queda *Hoja de control por revisar*.
4. **Revisión humana.** Alguien del equipo revisa la hoja y la marca revisada. Desde este
   momento la carpeta se publica al perfil de la entidad.
5. **Descripción ISAD(G).** Quien tiene la función de descripción la genera; la plataforma
   resuelve fechas extremas, periodo y subserie de la tabla de valoración. Queda *Descripción
   por validar*; una persona la valida y la dirección la aprueba (*Archivado*).
6. **Reubicación.** Se asigna caja definitiva (AH-CJ) y número de carpeta en la caja. Queda
   *En inventario de salida*.
7. **Instrumentos.** FUID F-GDM-003 v9, hojas de control F-GDM-007 v4, rótulos F-GDM-006 y
   F-GDM-008 v5, base ISAD(G) en la plantilla del proyecto. Todo sale sobre las plantillas
   oficiales; la plataforma las llena.

## Expedientes por partes y documentos de gran volumen

Un libro empastado llega de dos maneras y las dos terminan igual.

**Por partes nombradas por quien digitalizó.** `carpeta-00001- 1.pdf`, `carpeta-00001- 2.pdf`,
`AC-CP-00001_3.pdf`, `CARPETA 00001 parte 4.pdf`: la plataforma reconoce el código de carpeta
y el número de parte en cualquiera de esas formas. Las partes se pueden subir en cualquier
orden; la lectura las toma en el orden de su número, con la numeración de trámites y de
folios corrida de una a la siguiente, y sale UNA hoja de control. Si falta una parte en la
mitad (1, 2, 4), queda anotado en la bitácora y en la hoja; al cargar la que falta se vuelve a
levantar. Si una parte llega mientras se está leyendo, la plataforma vuelve a leer el
expediente completo en orden.

**Entero, en un solo archivo.** Un documento de más de `PAGINAS_POR_PARTE` páginas (250 por
defecto; un libro de 1.000 imágenes da cuatro partes) lo divide la plataforma en partes
consecutivas dentro del depósito, cada una con el rango de páginas del original que abarca
(1–250, 251–500, …). Las páginas se copian tal cual, sin tocar la imagen; la huella del
archivo entero queda registrada en cada parte y en la bitácora, de modo que la secuencia se
puede demostrar y un segundo cargue del mismo archivo se reconoce como duplicado.

Un expediente no se mezcla: si ya está por partes no entra un archivo entero, y si ya está
entero no entra una parte suelta. Para cambiar de modalidad se retira el expediente y se
vuelve a cargar.

En el visor, las partes aparecen como botones (parte 1, parte 2, …) con su rango de páginas.

## Consulta de la entidad

La dirección crea la cuenta en la pestaña Cuentas con rol *Entidad (consulta SGC)* y marca
qué puede ver: hojas de control, base ISAD(G), inventario FUID e imágenes digitalizadas
(las imágenes vienen apagadas). La cuenta entra a una sola pestaña, Consulta, donde busca
por carpeta, nombre o código de referencia, filtra por caja y periodo y descarga los
instrumentos en los formatos oficiales. Solo ve unidades cuya hoja de control ya fue
revisada; la base ISAD(G) solo lleva descripciones validadas y el FUID solo lo que está en
caja definitiva. Ninguna información del proceso interno (cola, lecturas, reparto de trabajo,
centro de control) le es visible ni accesible por la API.

## Novedades de la versión 2.3

**Ficha ISAD(G) editable.** En Revisión, al abrir una carpeta aparecen los 26 elementos de la norma agrupados por área. Se puede escribir o corregir cualquiera. Los elementos de redacción (título, alcance y contenido, organización, características físicas, unidades relacionadas y notas) tienen tres botones de IA: redactar, convertir mis notas y mejorar mi texto. La IA solo propone; nada se guarda hasta pulsar «Guardar cambios de la ficha». Lo que la persona guarda deja de estar marcado como propuesta del modelo.

**Validación previa.** No se puede validar ni aprobar una ficha que tenga textos marcados como propuesta o elementos obligatorios vacíos.

**Hoja de control contra imágenes.** Al cargar una hoja o un PDF se compara automáticamente: continuidad de folios, tipos documentales, partes faltantes, páginas del PDF frente a folios de la hoja, archivos ausentes y calidad técnica. Botón «Validar hoja contra imágenes» en cada ficha y «Validar todas las hojas» en Proceso.

**Devolver.** Botón «Devolver (está mal)» en la ficha, con motivo obligatorio. Puede devolver a la hoja de control o, si ya hay descripción, a la ficha. Una descripción aprobada pierde la aprobación al devolverse.

**Administradora sin límites.** La administradora elabora, valida y aprueba descripciones y hojas sin importar la función marcada en su cuenta; si aprueba lo que ella misma describió, la bitácora lo deja dicho.

**Consulta de la entidad.** No muestra carpetas retiradas, devueltas ni con errores (hoja contra imagen, textos sin revisar). Nunca muestra la marca de propuesta del modelo. Aplica también a las descargas de hojas de control, ISAD(G) y FUID.

## Novedades de la versión 2.4

**Bandeja de tareas (Inicio).** Ordena el trabajo por lo que sigue: devueltas, hojas por revisar, listas para describir, descripciones por validar, validadas sin enviar y ya visibles en consulta. Desde ahí se abre cada carpeta. Hay dos acciones en lote que adelantan trabajo sin quitarle la decisión al archivista: pedir a la IA una propuesta de ISAD(G) para varias hojas (quedan editables y marcadas) y enviar a consulta todas las validadas que no tengan errores.

**Ver antes de descargar.** En Instrumentos, «Ver FUID» y «Ver descripción ISAD(G)» muestran en pantalla exactamente lo que saldría en el Excel, con buscador y la opción de incluir lo aún no validado. Desde la misma vista se descarga.

**Enviar a consulta es un acto humano.** Ninguna carpeta llega a la entidad hasta que alguien con permiso de validar pulsa «Enviar a consulta» (una por una o en lote). Solo se puede enviar lo que tiene la descripción validada y no tiene errores. Si después se edita, se devuelve o se retira, sale de consulta sola hasta que se envíe de nuevo. «Quitar de consulta» está disponible siempre.

**Importante al actualizar.** Como ahora se publica de forma explícita, al instalar esta versión la consulta de la entidad queda vacía hasta que se envíe lo validado. Para lo que ya estaba validado o archivado, basta el botón de envío en lote de la bandeja.

## Versión 2.5. La entidad no ve rastro de IA

La inteligencia artificial vive solo en el proceso interno. Hacia la entidad:
- Una ficha u hoja de control que mencione IA, un modelo o un proveedor no se puede validar ni enviar a consulta hasta que se reescriba ese pasaje.
- Los Excel de consulta salen sin marcas de propuesta, sin la hoja «Revisión previa», sin comentarios y con propiedades del archivo neutras (autor «Archivo Central»).
- Los PDF se sirven sin metadatos de procesamiento.
- Las instrucciones que recibe la IA le prohíben mencionar cómo se elaboró el texto.

## Versión 2.6. Todos los campos de la plantilla en pantalla

- La ficha muestra ahora los elementos de la norma más los que trae la plantilla de 44 columnas: **Unidades de conservación** y **Fuentes consultadas** son editables; **periodo, código de dependencia, serie y subserie, nombre del expediente, caja, carpeta, lote, folio acumulado final, profesional que elabora y que revisa, fecha de la última revisión, estado de la descripción y dictamen** se muestran calculados.
- **Ver lo que propuso la IA.** Debajo de cada campo aparece «Ver lo que propuso la IA» cuando lo propuesto difiere de lo que quedó. Se puede leer y recuperar con «Usar esta propuesta». Es solo interno: no sale en consulta ni en los instrumentos.
- La base ISAD(G) exportada agrega al final, sin mover nada de la plantilla: Unidades de conservación, Fuentes consultadas, Profesional que revisa, Fecha de la última revisión y Estado de la descripción.

## Versión 2.7

- **Planeación por periodos** (pestaña nueva). Toma el FUID de origen, ubica cada carpeta por sus fechas (no por el periodo del inventario), muestra por caja qué carpetas trae, marca cajas que mezclan periodos y carpetas sin fecha o que cruzan periodos, y ordena «Qué sigue» dentro del periodo en curso para que no se salte de periodo. Descarga en Excel. El cálculo se guarda 20 segundos; «Actualizar» lo fuerza.
- Al cargar un PDF se avisa si su periodo por fechas no es el del periodo en curso.
- **Clasificación editable** en la ficha: periodo y subserie se corrigen a mano (queda en la bitácora y la unidad vuelve a «Descripción por validar» si ya estaba validada).
- **Corregir hoja de control** desde la ficha: si la unidad ya pasó la revisión, la devuelve con motivo y abre la hoja.
- Todos los elementos ISAD(G) son editables. Estado, profesional que revisa, fecha de revisión, dictamen, caja definitiva y consecutivo los fija el sistema para conservar la trazabilidad.
- El ISAD(G) no menciona la hoja de control: los textos nuevos y la exportación lo evitan, y las fichas que ya lo mencionan quedan señaladas para reescribir (no se editan solas).

## Versión 2.8

- **Propuesta de caja para el inventario de salida** (pestaña Reubicación, arriba). Toma las carpetas aprobadas, las ordena por fechas dentro de cada periodo y propone la caja: un solo periodo por caja, llenando hasta 10 cm (espesor estimado: folios × 0,1 mm + 0,3 cm de carpeta o 1,5 cm de pastas si es libro). Completa primero las cajas abiertas del mismo periodo.
- Cada caja dice cuántas carpetas terminadas ya caben en ella y cuáles faltan por terminar entre sus fechas.
- La propuesta es **editable**: la caja de cada carpeta se puede cambiar y cualquier carpeta se puede desmarcar.
- **Nada se asigna solo.** La propuesta no se guarda ni la ve el Servicio Geológico. Solo la administradora, con «Validar y agregar», fija la caja definitiva y el número de carpeta. Asignar a mano (`/ubicacion/asignar`) también quedó solo para la administradora.
- Descarga «Propuesta sin validar» en Excel, de uso interno.

## Versión 2.9

- **Orden de las cajas:** periodo, serie y subserie en el orden de la tabla de valoración y, dentro de cada subserie, cronológico. La propuesta abre una caja nueva en cada cambio de subserie. Asignar una carpeta de otra subserie a una caja que ya tiene una se bloquea, salvo que la administradora marque «Permitir mezclar subseries».
- **Decide la administradora si cabe o no:** puede cambiar el límite de llenado (10 cm por defecto), pedir una carpeta por caja, filtrar por periodo, mover las carpetas marcadas a una caja indicada o a una caja nueva, y abrir cuantas cajas necesite en un periodo.
- **Un FUID por periodo:** la propuesta se descarga por periodo, igual que el FUID oficial (filtro de periodo).
- **Consulta en pantalla:** la entidad ve el FUID, la base ISAD(G) y cada hoja de control en la pantalla, solo lo publicado y sin errores, y puede descargarlos.

## Versión 2.9.1

- **Imágenes para la entidad sin metadatos.** Al ver las imágenes desde Consulta se entrega una copia temporal sin información del documento, sin XMP, sin datos privados de programas ni miniaturas, y sin los Exif/XMP/IPTC/comentarios de las imágenes JPEG incrustadas (los píxeles no se tocan). Si no se puede limpiar, no se entrega el original: responde 503. El archivo original del almacén no se modifica, para conservar su huella de no alteración.

## Versión 2.9.2

- **Hoja de control:** el tipo documental y las observaciones ahora son cuadros que crecen y se ven completos (antes se cortaban).
- **Foliación que reinicia:** cuando el papel vuelve a empezar en 1, el error trae el botón «Continuar desde el folio N», que sigue la cuenta corrida desde ese trámite hasta el final, conserva cuántos folios tiene cada uno y deja constancia en observaciones.

## Versión 2.9.3

- **Pantalla de Hojas de control:** se corrigió el montaje del bloque superior; los botones «Traer datos», «Levantar con el modelo» y «Descargar F-GDM-007» ya no se pisan con el cuadro de serie y subserie.
- **Imágenes JPG, PNG y TIFF:** además de PDF se pueden cargar imágenes. Las que se seleccionan juntas son las páginas de un documento: se unen en un solo PDF en el orden natural de sus nombres (1, 2, 10) sin recomprimir. El sistema pide el código de carpeta (y la parte, si la hay). Si la imagen no trae resolución escrita, la ficha técnica lo dice en lugar de suponerla.
- **Foliación continua entre partes y bloques:** el papel de un tomo está foliado de corrido. Si la lectura reinicia en 1 al empezar otra parte o bloque, el sistema corre los folios para que sigan donde terminó el anterior y deja el aviso en la bitácora. Si el papel realmente reinicia, queda el botón «Continuar desde el folio N».
- **Parte del tomo en la hoja:** el primer trámite de cada parte lleva en observaciones «Inicia la parte N del tomo».
- **Modo riguroso para tomos extensos (RIGOR_TOMOS=1):** los archivos de más de 60 páginas los lee solo Claude, en bloques de 40 páginas, tomando el folio escrito en el papel. Si Claude no tiene cuota el tomo espera; no pasa a otro modelo. Requiere ANTHROPIC_API_KEY. La hoja siempre queda como propuesta para revisión de una persona.

## Versión 2.9.4

- **Fechas:** en la hoja de control solo vale la fecha completa (día, mes y año). Si falta cualquiera de las tres, o es ilegible, el trámite queda en SF; no se completa ni se deduce. Aplica a la lectura del modelo, a la hoja diligenciada a mano y a la verificación.
- **Proveedor de los tomos extensos:** `RIGOR_PROVEEDOR` (claude o gemini) define quién los lee en modo riguroso.

## Versión 2.9.5

- **Reemplazar imágenes conservando la hoja:** en Cargue, la casilla «Reemplazar las imágenes ya cargadas» cambia las imágenes de una carpeta (o solo de la parte indicada) por las nuevas, por ejemplo las fotos de cámara por las del escáner definitivo. La hoja de control no se vuelve a leer ni pierde ediciones; queda constancia en la trazabilidad con la huella de lo que se retiró, y la validación contrasta de inmediato páginas y folios. Sin la casilla, una carpeta que ya tiene imágenes ya no acepta otro archivo entero.
- **Radicado y contenido:** la instrucción al modelo exige copiar el radicado literal del sello (N/A si no se lee con certeza) y leer primero encabezado, asunto, remitente, destinatario y firma antes de describir el trámite.
- **Control de folios por bloque:** el modelo informa el primer y último folio ESCRITOS que ve en cada bloque; si el primero no coincide con la cuenta, la bitácora trae «REVISAR FOLIACIÓN» con las páginas exactas.

## Versión 2.9.6

- **Un solo PDF por libro o tomo para la entidad:** las partes en que se digitalizó (AC-CP-00808_1, _2, _3…) entran por separado, pero Consulta entrega el tomo completo en un solo PDF (AC-CP-00808.pdf), en el orden de las partes, sin recomprimir y sin metadatos. La entidad no puede pedir partes sueltas. Si falta alguna parte de la secuencia, no se entrega y se dice cuál falta. La administradora conserva `?parte=N` para revisar una parte.

## Versión 2.9.7

- **Control de calidad de la digitalización** (criterios de la guía GU-SAD-ODA-001 y de la Memoria descriptiva): resolución mínima de 300 ppp (`CALIDAD_DPI_MINIMO`), escala de grises de 8 bits o color de 24 bits, formato PDF/A, texto buscable, y revisión al 100 % de las páginas en exposición (muy oscura o muy clara), foco (borrosa), alineación (torcida) y páginas en blanco. Las páginas sospechosas se documentan con su número y motivo; no se descartan. Es una prueba automática: señala qué mirar frente al papel, no la reemplaza.
- **Dónde se ve:** en Cargue, botón «Calidad de la imagen» con informe en Excel (resumen y detalle por página). La entidad ve el resumen en el visor del tomo.
- **PDF unificado de la entidad:** lleva los metadatos descriptivos de archivo (título, productor, serie y subserie, código de dependencia) y ningún dato de procesamiento. Conserva la declaración PDF/A de las partes de origen cuando todas la traen; la conformidad real se certifica con un validador externo (veraPDF).
- **Tomos extensos:** `RIGOR_PROVEEDOR=gemini` por defecto, en bloques de 60 páginas.

## Versión 2.9.8

- **Paquete de entrega** (Instrumentos, «Paquete de entrega de la digitalización», solo administradora): genera un zip con la copia de CONSULTA (un PDF por libro o tomo), la copia MAESTRA (una imagen por página, TIFF sin pérdida), la estructura SGC / periodo / dependencia / serie / subserie / expediente con nombres sin espacios ni tildes (`CódigoDependencia_CódigoSerie_Año_Expediente`), el INDICE_ELECTRONICO en CSV y XML (identificador único, formato, tamaño, huella SHA-256, fecha de creación, creador y orden), el índice de documentos de cada expediente, HASHES_SHA256.txt, el informe de calidad por expediente y el ACTA_CIERRE_DIGITALIZACION en Word.
- **Copia maestra:** si la imagen de origen es JPEG ya perdió información al capturarse; no se convierte a TIFF (solo se agrandaría el archivo). Se entrega tal cual y queda marcada «NO, JPEG con pérdida» en el índice y en el acta. Para una maestra conforme hay que capturar en TIFF (o JPEG 2000) en el escáner y cargar esas imágenes; el sistema las une en PDF sin recomprimir y las devuelve como TIFF.
- **Acta:** trae folios físicos frente a imágenes, resultado de la prueba automática de calidad, formato de la copia maestra y estado de conservación registrado (3.4.4). Lo que solo afirma quien revisó el papel (legibilidad, orientación, páginas completas, sin daño por escaneo) queda como casilla para marcar y firmar. Máximo de expedientes por entrega: `MAX_EXPEDIENTES_POR_ENTREGA` (40).
- **Entran solo** expedientes con descripción validada, publicables y con el tomo completo; los demás se listan con el motivo.

## Versión 2.9.9

- **Sección y subsección en el paquete de entrega:** el árbol queda Fondo / Periodo / Sección (código y unidad administrativa de la tabla de valoración) / Subsección (oficina productora) / Serie / Subserie / Expediente.
- **Imágenes de trabajo e imágenes definitivas:** en Cargue, la casilla «Son las imágenes definitivas del escáner». Sin marcar, las imágenes son de trabajo (cámara) y sirven para avanzar la hoja de control; con la casilla de reemplazo y la de definitivas se cambian por las del escáner conservando la hoja. El paquete de entrega solo incluye expedientes cuyas imágenes son todas definitivas.
- **PDF/A en el cargue:** se aceptan archivos `.pdf` y `.pdfa`, con o sin la marca en el nombre (`AC-CP-00808_PDFA.pdf`, `-PDF-A`, `PDF/A`). La ficha técnica muestra el formato declarado (por ejemplo PDF/A-2b). Un archivo que ya viene en PDF/A del escáner se conserva tal cual como matriz de preservación, sin volver a convertirlo.

## Versión 2.9.10

- **Validación real de PDF/A con veraPDF.** Antes la plataforma solo leía lo que el archivo declaraba. Ahora ejecuta veraPDF, el validador de referencia del estándar ISO 19005, y solo da por conforme lo que veraPDF aprueba. Se probó que un archivo que declaraba PDF/A-2b no cumplía (imágenes RGB sin perfil de color).
- **En el paquete de entrega:** cada PDF de consulta se valida; si no cumple, se convierte a PDF/A sin alterar las imágenes y sin dejar rastro del programa que lo produjo, conservando los metadatos descriptivos de archivo, y se vuelve a validar. Si aun así no cumple, se le quita la declaración PDF/A y el índice y el acta lo dicen con el número de reglas incumplidas. Si veraPDF no está instalado, queda «NO VERIFICADO».
- **En el informe de calidad:** el criterio de formato muestra «verificado» o «no conforme» con las reglas que fallan, no la simple declaración.
- **Instalación:** el Dockerfile instala Java y veraPDF. Fuera de Docker, `sh scripts/instalar_verapdf.sh` y `VERAPDF_BIN` en el `.env`. `PDFA_PERFIL` (2b por defecto) es el perfil para archivos que no declaran ninguno.

## Versión 2.9.11

- **Perfil PDF/A exigido: PDF/A-1b por defecto**, porque así lo pide la guía GU-SAD-ODA-001 del Servicio Geológico (ISO 19005-1). El perfil se EXIGE: un PDF/A-2b se convierte a PDF/A-1b. Para exigir otro, `PDFA_PERFIL` en el `.env` (por ejemplo `2b`).
- **Informe de calidad:** un archivo cargado como PDF común (por ejemplo, la foto o el escaneo de trabajo) ya no aparece como falla alarmante: dice que la copia de entrega se convierte a PDF/A al generar el paquete. Solo marca «declara PDF/A pero no cumple» cuando el archivo dice serlo y no lo es, con las reglas que fallan.

## Versión 2.9.12 · Cuota de los modelos controlada desde la plataforma

En Avance, sección «Modelos de lenguaje», la administradora tiene dos botones nuevos:

- **Cambiar tope diario**: fija cuántas peticiones por día y por modelo se le permiten a un
  proveedor (claude, gemini u openai). Se guarda en `deposito/ajustes_cuota.json` y manda sobre
  `CUOTA_GEMINI` del `.env`; no hace falta reiniciar ni tocar el servidor.
- **Reactivar agotados**: quita la marca «agotado» del día. Úsese después de recargar la cuenta
  del proveedor o cuando el proveedor devolvió un límite pasajero (por minuto) que la plataforma
  tomó como límite del día.

El límite real lo pone el proveedor (saldo y límites de la cuenta). El tope de la plataforma
solo evita gastar de más: conviene dejarlo alto y vigilar el gasto en la consola del proveedor.

## Versión 2.9.13 · Panel de modelos solo para la administradora y respaldo entre modelos

- El panel «Modelos de lenguaje» (cuota, llaves, errores del proveedor) solo lo ve la
  administradora, y el servidor rechaza la consulta de cualquier otro perfil.
- Si al proveedor del modo riguroso (Gemini) se le acaba la cuota en medio de un tomo, los
  bloques que faltan los lee otro modelo (Claude o ChatGPT) y la hoja sigue desde donde iba, sin
  perder lo ya leído. Qué páginas se leyeron con otro modelo queda escrito solo en la bitácora del
  expediente (visible para el equipo, nunca para la entidad), no en la hoja de control. Se apaga con `RIGOR_RESPALDO=0` en el `.env`.

## Versión 2.9.14 · La hoja de control sale sin marcas

Ninguna hoja de control descargada, por ninguna ruta, lleva la marca «[PROPUESTA DEL MODELO,
PENDIENTE DE REVISIÓN]» ni observaciones sobre qué modelo leyó. El aviso de pendiente de revisión
sigue en la pantalla de trabajo; el formato oficial sale limpio.

## Versión 2.9.15 · Casilla «sin límites» para cubrir una ausencia

En Cuentas, la administradora ve junto a cada persona del equipo (rol equipo o líder) la casilla
**Sin límites (cubre una ausencia)**. Prendida, esa persona puede hacer todo el trabajo del flujo:
elaborar la descripción, validar, aprobar, devolver y retirar. Se apaga con la misma casilla cuando
la ausencia termina.

- Todo lo que haga queda en la bitácora con su nombre.
- Sigue valiendo la regla de que nadie aprueba su propio trabajo; la excepción es solo de la administradora.
- Siguen siendo solo de la administradora: administrar cuentas, la entrega formal, validar y agregar
  cajas definitivas, y la cuota de los modelos.
- No aplica a la administradora, a la consulta interna ni a la entidad.

## Versión 2.10.0 · Seguimiento: asignación de carpetas, cronograma y tablero de control

Pestaña nueva **Seguimiento**.

**Quién ve qué.** La administradora asigna, define metas y ve todo. La líder ve el tablero y el cronograma. Cada persona del equipo ve solo sus carpetas asignadas. Consulta y entidad no entran.

**Asignar carpetas.** Se filtran las carpetas sin responsable por etapa (hoja de control o descripción), periodo, caja y estado; se marcan y se asignan a una persona con fecha límite y nota. También se puede repartir en bloques: se marca a las personas, se dice cuántas carpetas por persona, y cada una recibe un bloque seguido de la misma caja. Cada asignación se puede reasignar o quitar. Asignar no bloquea a nadie: otra persona puede trabajar esa carpeta si cubre una ausencia.

**Cronograma.** Cada meta dice cuántas carpetas (por defecto, todas las del periodo) deben llegar a qué estado entre dos fechas. El tablero compara el plan lineal por días hábiles con lo realmente hecho, muestra cuánto falta, el ritmo diario que se requiere, el ritmo de los últimos 7 días, la fecha de terminación proyectada y un semáforo (al día, en riesgo, atrasada). Los días hábiles son de lunes a viernes; los festivos no se descuentan.

**Tablero.** Indicadores generales, una gráfica de plan contra real por meta, y una tabla por persona con su carga (hechas, en curso, pendientes, devueltas), carpetas vencidas y colgadas, última actividad y un gráfico de barras de sus últimos 14 días. Una carpeta está **colgada** cuando está abierta y lleva 3 días o más sin ningún movimiento; **vencida** cuando pasó su fecha límite sin terminarse. Una persona aparece en rojo si tiene carpetas abiertas y lleva 4 o más días hábiles sin actividad. Se descarga todo en Excel.

**Cómo se mide.** No hay contadores que se escriban a mano. El avance sale del estado real de cada carpeta y de la bitácora, que registra quién hizo cada movimiento. Una asignación de hoja de control se da por hecha cuando la hoja llega a «por revisar» o más; una de descripción, cuando llega a «descripción por validar» o más.

Se agregan dos tablas (`asignacion` e `hito_cronograma`); el sistema las crea solo al arrancar. La etiqueta de versión de `/estado` pasa a 2.10.0.

### Aprueba lo propio (cuentas)

En Cuentas, la administradora puede marcar «Aprueba lo propio» a quien quiera (equipo o líder). Esa persona puede aprobar una descripción que ella misma elaboró, pero la carpeta sigue pasando por todos los estados y módulos (hoja de control, descripción por validar, descripción validada): si el estado no corresponde, el sistema responde 409 y no la deja saltarse nada. Sin la casilla, nadie aprueba su propio trabajo; solo la administradora tiene esa excepción por defecto. La bitácora deja constancia: «Aprobación propia… con la autorización de la administradora». Sigue aplicando el control de calidad de la ficha. Se agrega la columna `aprueba_lo_propio` en las cuentas (se crea sola al arrancar).

## Versión 2.10.1 · Llave paga de reserva y alcance para las 1.020 cajas

1. La llave paga de Gemini se identifica de dos maneras: escribiéndola en el archivo `.env` como `GEMINI_API_KEY_PAGA`, o desde Centro de control, botón «Marcar la llave paga» (se elige por número; la plataforma solo muestra los últimos 4 caracteres y guarda una huella, nunca la llave).
2. Las llaves gratuitas se usan primero. La paga queda de reserva y entra solo cuando no queda ninguna gratuita con cuota, para terminar lo que falte sin que la producción se cuelgue.
3. Cada tipo de llave tiene su propio tope diario: `CUOTA_GEMINI` para las gratuitas y `CUOTA_GEMINI_PAGA` para la paga. Ambos se cambian desde «Cambiar tope diario» sin tocar el servidor.
4. Centro de control muestra «¿Alcanzan las llaves para las 1.020 cajas?»: cuenta las carpetas que faltan por pasar a hoja de control, estima las peticiones, las compara con lo que dan las llaves por día hasta el 31 de diciembre y dice si las gratuitas alcanzan solas, si la paga tiene que aportar o si no alcanza. Es una estimación según los topes configurados; el límite real lo fija Google. Variables: `META_CAJAS` (1020), `FECHA_FIN_CONTRATO` (2026-12-31), `PETICIONES_EXTRA_POR_CARPETA` (1).

## Versión 2.11.0 · Contrato 733: tablero, informes, fichas técnicas y eliminación documental

Nueva pestaña **Contrato** (administradora edita; líder lee; el resto y la entidad no la ven).

1. **Resumen**: metros lineales intervenidos (una carpeta cuenta desde el estado «Hoja de control elaborada», ajustable), plan a hoy según los lotes, atraso, ritmo necesario por día hábil, cobrable estimado, multa diaria (2 por mil, tope 20 %), cláusula penal y garantías.
2. **Lotes**: seis lotes del plan (30/50/53/51/51/20 ML = 255 ML). Se registra el recibo a satisfacción y la factura de cada uno. Botón para pasarlos al cronograma de Seguimiento.
3. **Obligaciones**: las 19 de la cláusula décima segunda, con estado, evidencia e indicador automático cuando la plataforma lo conoce.
4. **Observaciones de la supervisión**: cada petición corre 5 días hábiles; alerta si vence.
5. **Informes y fichas**: informe mensual, informe de lote, nueve fichas técnicas por lote (FT-733-ACT-Ln) e informe técnico final. Todos se arman con datos reales, quedan como borrador y se abren en un **visor donde la administradora puede editar cualquier título, párrafo, lista o tabla** (agregar, quitar, mover bloques, filas y columnas), guardar versiones, marcar como firmado y descargar en Word, PowerPoint o Excel. Lo que la plataforma no sabe queda como «[Completar: …]».
6. **Eliminación documental** (PR-GDM-001 v3, Acuerdo 001 de 2024): la plataforma busca candidatas, **la persona decide carpeta por carpeta** (las de posible derechos humanos no se confirman en bloque), y genera FUID de eliminación (también en la plantilla oficial F-GDM-003), informe técnico, presentación para el Comité y borrador del acta. El estado se calcula a partir de las fechas de los hitos; la publicación de 60 días hábiles y el concepto del AGN de 30 días hábiles se calculan solos. Nada se elimina desde la plataforma.

Notas: los festivos de la cuenta de días hábiles son una aproximación; el acta es un borrador que debe ajustarse al formato oficial vigente del Servicio Geológico; los metros lineales del Contrato salen de cajas X-200 (0,25 ML por caja), mientras que el panel de producción usa la equivalencia del proyecto de 10.000 folios por metro lineal: son medidas distintas y no deben compararse. Las cifras del contrato se corrigen en «Datos del contrato».

## Versión 2.12.0 · Cobro por metros lineales, acta de eliminación en formato oficial y testigo documental

1. **Base de pago.** El contrato paga 175 metros lineales a $1.797.582,78 cada uno, IVA incluido ($314.576.987). Los 80 metros lineales adicionales son valor agregado sin costo y se entregan al final. El tablero y los informes ya no dividen el valor entre 255.
2. **Cobro y pagos** (Contrato > Cobro y pagos). Los cuatro pagos mensuales vencidos de la proyección del Servicio Geológico (30, 40, 40 y 65 metros lineales). Para cada uno la plataforma sugiere los metros lineales con las cajas completas intervenidas al cierre del periodo, descontando lo ya cobrado y con tope en 175; la administradora puede fijar otra cantidad. Genera la cuenta de cobro (prefactura, con valor en letras), la relación de metros lineales por caja, los informes mensuales que falten y el formato F-FIN-007 prellenado (con el Anexo 1 de facturación). Lleva las fechas del trámite (prefactura, recibo a satisfacción, factura, radicación, pago) y la lista de documentos para radicar.
3. **Acta de eliminación en formato oficial.** El acta tiene la estructura del F-GDM-004 versión 2 y se descarga en la plantilla oficial («Formato oficial F-GDM-004»), con las ediciones que se hayan hecho en el visor.
4. **Testigo documental (F-GDM-009).** Cuando alguien revisa una hoja de control, la plataforma avisa si los trámites, el asunto del inventario o las características físicas mencionan documentos que pueden estar fuera de la carpeta: planos y mapas, fotografías, discos, cintas, medios magnéticos, documentos electrónicos, muestras, o un documento retirado o faltante. Muestra el aviso en la ficha y antes de aprobar la hoja, y entrega el F-GDM-009 ya diligenciado con los datos del expediente. La plataforma solo avisa: coloca el testigo y decide la persona.

Plantillas nuevas en `datos/formatos_sgc`: F-GDM-004, F-GDM-009 y F-FIN-007 (copiar solo si no existen).


## Versión 2.13.0 · Avisos de edición simultánea, registro de descargas e inventario de documentos de apoyo

1. **Edición simultánea.** Cuando alguien abre una hoja de control o una ficha de descripción para editarla, la plataforma lo anota y lo renueva cada 30 segundos. Si otra persona la abre mientras la primera sigue ahí, aparece un aviso rojo en la pantalla de las dos y se genera una alerta (campana de la cabecera) para cada una, para la líder y para la administradora. Al guardar, si otra persona guardó después de que usted la abrió, no se guarda nada: se le dice quién fue y a qué hora, y puede recargar o confirmar «guardar de todos modos». En ese caso queda la alerta para quien había guardado y para la dirección. La plataforma nunca decide cuál versión gana.
2. **Registro de descargas.** Toda descarga (instrumentos, hojas de control, FUID, base ISAD(G), rótulos, paquetes, informes, F-FIN-007, actas) y toda imagen digitalizada que abre la entidad queda registrada con la persona, el rol, el instrumento, el nombre del archivo, los filtros, el tamaño y la dirección de red. Lo consulta la administradora en Cuentas > Registro de descargas, con filtros por fecha y persona, y lo descarga en Excel. Solo se agrega; no se edita ni se borra. El registro lo hace una capa general de la aplicación, de modo que una descarga nueva queda anotada sin tocar nada.
3. **Inventario de documentos de apoyo (obligación 9).** Al revisar una hoja de control, la plataforma propone como documentos facilitativos, de apoyo o duplicados los trámites cuyo tipo documental u observaciones hablan de copias, duplicados, borradores, folletos, invitaciones, publicaciones, formatos en blanco y similares. La persona confirma o descarta cada propuesta (en la ventana previa a aprobar la hoja, o en la ficha), y puede agregar a mano lo que la plataforma no vio. El inventario se descarga en el formato FUID F-GDM-003 desde Contrato > Informes y fichas. Confirmar solo incluye el documento en el inventario: no saca ni elimina nada de la carpeta. La regla de detección sale de la práctica archivística y del anexo técnico; conviene validarla con la supervisión.
4. **Corrección.** Guardar un avance de la hoja de control con más de un trámite fallaba (error 500) porque los trámites quedaban todos con el número 0. Ahora se numeran y se leen los folios al guardar el avance.

Tablas nuevas, vacías y sin tocar las existentes: `sesion_edicion`, `alerta`, `descarga_registro`, `documento_apoyo`. Pruebas en `tests/test_2_13.py`.
