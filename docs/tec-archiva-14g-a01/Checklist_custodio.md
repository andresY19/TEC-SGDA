# Lista de validación del custodio · 14G

ADMIN_HISTORICAL_ACCESS=PENDING_CUSTODIAN.

No se recibió participación del custodio ni evidencia de un ingreso histórico autorizado durante 14G. Los cuatro contenedores originales están detenidos. El inicio del destino exige una autorización independiente. No se solicita ni registra la contraseña.

| Orden | Comprobación del custodio | Estado | Evidencia requerida |
|---|---|---|---|
| 1 | Confirmar persona autorizada, identidad de cuenta y destino por su inventario de contenedores. | PENDIENTE | Nombre o identificador del custodio, cuenta autorizada y aprobación del procedimiento. |
| 2 | Obtener autorización independiente de arranque si el destino sigue detenido. | PENDIENTE | Aprobación que especifique los IDs y el alcance. |
| 3 | Ingresar personalmente por el canal autorizado. | PENDIENTE | Resultado y fecha. Excluir contraseña, pase, cabeceras de autorización y capturas que los revelen. |
| 4 | Confirmar identidad, rol administradora, estado activo y obligación de cambio cuando corresponda. | PENDIENTE | Resultado saneado de identidad autenticada y rol. |
| 5 | Si aplica cambio obligatorio, ejecutarlo únicamente según el alcance autorizado. | PENDIENTE | Cambio completado y acceso posterior. Esta fase no autoriza modificar credenciales. |
| 6 | Comprobar acceso a las funciones administrativas permitidas. | PENDIENTE | Acciones de consulta autorizadas y resultados HTTP saneados. |
| 7 | Confirmar el procedimiento de recuperación documentado y sus responsables. | PENDIENTE | Procedimiento aprobado y referencia a la prueba sintética de 14F. |
| 8 | Registrar aceptación o fallo del acceso histórico. | PENDIENTE | Fecha, custodio, operador, destino, resultado PASS/FAIL y referencia de evidencia sin secretos. |

Ante un fallo de acceso, mantener NO_GO. No deducir ni restablecer la contraseña histórica durante este preflight. La recuperación sintética aprobada en 14F no sustituye la validación de esta cuenta.
