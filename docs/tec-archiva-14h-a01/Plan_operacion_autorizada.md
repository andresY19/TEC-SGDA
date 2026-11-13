# Plan de operación futura autorizada

La actualización y la operación sobre el destino protegido permanecen NOT_GRANTED. El acceso histórico continúa PENDING_CUSTODIAN.

1. Validar al custodio y obtener aprobación expresa de ventana, destino y operación. Verificar los IDs completos de servicios, volúmenes y redes y los digests de imágenes. Excluir auxiliares con etiquetas heredadas.
2. Ejecutar y verificar el respaldo al corte según el procedimiento aprobado. Probar restauración y compatibilidad en copia. Mantener la política de cierre general de sesiones, firma nueva, registro limpio y Redis ACL/AOF. Preparar otra rotación si se revierte.
3. Provisionar para la operación autorizada una política pública de propósito operation con las identidades reales y claves públicas custodiadas. Custodiar las claves privadas fuera de aplicación, imágenes y repositorio. El ensayo rehearsal tiene claves y recursos propios.
4. Confirmar UID/GID, raíz de solo lectura, almacenamiento autorizado, conectividad privada y rol SQL restringido. La aplicación no recibe el socket Docker. Comprobar DNS e IP y la identidad PostgreSQL antes de acceder a los datos.
5. Seleccionar una sola operación y verificar sus evidencias. Emitir el permiso con el ejecutor del anfitrión, plazo limitado y archivo nuevo. Revisar el destino y el alcance antes de consumirlo.
6. Ejecutar el permiso mediante operar_conciliacion.py run. El proceso valida el desafío, consume el permiso y registra el resultado. Código 0 significa observación conciliada; 2 exige revisión; 77 indica rechazo de autorización o identidad.
7. Verificar recibo, ledger y hashes. Conservar los archivos y diarios. Ante incertidumbre, suspender, revisar y solicitar un permiso nuevo para un reintento idempotente. No reutilizar el permiso consumido.

Comandos de referencia, con rutas a los archivos protegidos de la ventana aprobada:

```text
python operar_conciliacion.py issue --policy <politica-protegida> --authority-key <clave-custodiada> --target worker --operation <operacion> --storage-root /srv/geology/deposito --output <permiso-nuevo>
python operar_conciliacion.py run --policy <politica-protegida> --runner-key <clave-del-ejecutor> --authorization <permiso>
```

La CLI de aplicación no acepta una ruta alternativa a la política de confianza montada. No se imprimen claves privadas, credenciales ni permisos firmados en informes. El plan queda suspendido ante recursos distintos, autorización inválida, evidencia ausente, pérdida de acceso administrativo o modificación de esquema inesperada. La reversión conserva archivos, rechaza pases antiguos y requiere acceso administrativo custodiado.

Para aprovisionar la política en la ventana aprobada, el operador debe utilizar las funciones snapshot e initialize_ledger del módulo anfitrión con los cuatro IDs Docker completos, un directorio de auditoría nuevo bajo ACL privada y dos pares de claves independientes. El documento público de política fija version, purpose, authority_public_key, runner_public_key, max_seconds, node_binary, node_sha256, host_ledger_path, protected_resources, resources, target_services y storage_roots. resources debe contener el resultado observado de snapshot. Usar el mismo archivo público en el ejecutor y en el montaje de solo lectura de los contenedores. La prueba de alias de 14H conservó el propósito rehearsal. El propósito operation se reserva para la política futura autorizada.

Los Dockerfiles de rc.3 se construyen desde el directorio de la candidata con codigo como contexto. Verificar antes los IDs de las imágenes padre contra el manifiesto de rc.2. Ejemplo de reconstrucción con una etiqueta nueva:

```text
docker build --pull=false --network=none -f Dockerfile.fastapi -t <etiqueta-nueva> codigo
```
