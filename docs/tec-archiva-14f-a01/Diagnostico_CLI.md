# Diagnóstico de la CLI de conciliación

El bloqueo era una validación del nombre del proyecto en el punto de entrada. La CLI original exigía el prefijo geology-auto11e-. El módulo de dominio no aplica esa condición, por lo que la llamada directa de 14E podía conciliar mientras la CLI terminaba antes de consultar SQL.

## Reproducción

Contexto sintético GEOLOGY_LOCAL_PROJECT=geology-restore14f-cli, GEOLOGY_ENTORNO=test y LEVANTAR_AL_CARGAR=no. La configuración PostgreSQL y Redis se suministró desde archivos privados nuevos.

```bash
python -B /opt/geology-distribution/reconcile_documents.py --operation /cert/cases/commit_uncertain/preservacion/versiones/2a17128d058241e1863f48a503dafed6 --storage-root /cert
```

La imagen anterior fue sha256:bab12d1eaadd16fe9592a7751b1e22503709b60370f337d73ce7a8510cff8db0. El proceso terminó con código 1 y el mensaje `BLOCKED: isolated 11E certification only`. La reproducción se ejecutó sin red en un contenedor nuevo y no accedió a la base original.

## Corrección y comando certificado

La candidata derivada 2.13.0-rc.1+14f.2 permite confirmar otro proyecto local mediante --local-project. Exige coincidencia con GEOLOGY_LOCAL_PROJECT, formato válido y GEOLOGY_ENTORNO local/test/testing/pruebas. El proyecto original sigue bloqueado explícitamente. El comportamiento sin la opción se conserva para el namespace de certificación anterior. LEVANTAR_AL_CARGAR debe seguir en no.

```bash
python -B /opt/geology-distribution/reconcile_documents.py --operation /cert/cases/commit_uncertain/preservacion/versiones/2a17128d058241e1863f48a503dafed6 --storage-root /cert --local-project geology-restore14f-cli
```

En el despliegue autorizado, el almacenamiento documental corresponde a /srv/geology/deposito y el identificador debe ser el proyecto local aprobado. La confirmación no reemplaza la inspección externa de contenedores, redes, volúmenes y conexiones. El ensayo amplió el contexto del proceso CLI sobre el almacenamiento y PostgreSQL sintéticos de 14F. No alteró el contexto del worker que consume la cola.

Las dos copias del punto de entrada, /srv/geology/reconcile_documents.py y /opt/geology-distribution/reconcile_documents.py, contienen la corrección. Las imágenes de FastAPI, Celery y certificación incorporan el archivo sin montaje del código fuente. La lógica de geology/dominio/conciliacion.py conserva el hash de la RC original.

## Dependencias y permisos

La CLI usa Python, SQLAlchemy, psycopg2 y la configuración DATABASE_URL para abrir una sesión. El bloqueo de archivos usa fcntl de Linux. Necesita leer archivos y diarios y escribir el archivo de bloqueo y los recibos en la operación. La raíz se valida y se rechazan rutas inseguras. El rol geology_runtime dispone de SELECT y del permiso de columna requerido para el bloqueo de filas. No requiere privilegios DDL, propiedad de tablas ni superusuario.

Redis no participa directamente en la conciliación. Broker, resultados y sesiones conservan sus usuarios ACL y sus espacios de claves. Las pruebas verificaron que conciliar no cambia el registro de sesiones ni publica tareas.

## Resultados

La CLI devolvió 0 para conciliación demostrada y 2 para revisión pendiente. Pasaron nueve comprobaciones específicas. En la ejecución concurrente los códigos fueron [2, 0]. Un bloqueo exclusivo retenido de forma explícita produjo rechazo seguro; después de liberarlo, el reintento pasó. El archivo incompleto permaneció conservado y marcado para revisión. Los reintentos mantuvieron un único recibo y las huellas de los archivos.

Las pruebas afectadas de conciliación incluyen 24 casos del mecanismo, un caso con Redis caído y seis casos contra las imágenes autónomas. El rollback SQL, el commit aceptado con respuesta perdida, los recibos, el reinicio y la exclusión concurrente se verificaron sin modificar reglas archivísticas.
