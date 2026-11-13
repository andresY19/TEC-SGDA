# Actualización local pendiente de aprobación

1. Verificar IDs completos, red, montajes, imágenes y estado. Excluir el auxiliar 14D. Renovar el respaldo si el destino cambió y comprobar la restauración lógica, los hashes y las referencias.
2. Acordar ventana, custodio y verificación de la cuenta administrativa histórica. El ensayo 14E usó solo una cuenta sintética. Si el acceso o la recuperación custodiada falla, mantener la ventana cerrada.
3. Preparar Redis privado con ACL, AOF y un registro de sesiones vacío. Generar llave y credenciales nuevas en almacenamiento protegido. Aplicar al rol de aplicación los GRANT revisados. No elevar a superusuario.
4. Congelar escrituras y verificar que la cola esté drenada. Arrancar las imágenes verificadas con raíz de solo lectura y UID/GID 10001:10001. Validar catálogo, almacenamiento, login, RBAC, rechazo de pases antiguos y Celery antes de abrir.
5. Resolver la operación autorizada de conciliación para el destino. Si falla el acceso, aparecen diferencias inexplicadas o se reactiva un pase, suspender y ejecutar el procedimiento de reversión aprobado.
