# Plan de actualización local

**NO_GO. Autorización NOT_GRANTED.** Las etapas de ejecución requieren una aprobación expresa posterior. El arranque del original para comprobar al custodio, si se requiere, debe quedar autorizado por separado.

| Etapa | Acción | Condición de suspensión |
|---|---|---|
| 1 | Validar al custodio y acordar la ventana, alcance, responsables, digests de rc.3 y criterios de aceptación. | Falta acceso histórico verificado o aprobación expresa. |
| 2 | Cotejar IDs, imágenes, redes, montajes y volúmenes. Verificar capacidad, cerrar entradas y confirmar ausencia de escritores y cola sin trabajo desconocido. | Diferencia inexplicada, escritor activo, tarea desconocida o capacidad insuficiente. |
| 3 | Generar el respaldo al corte y restaurarlo en copia según el procedimiento 14F. Incluir PostgreSQL, Redis, depósito, expedidos, hojas auxiliares, configuración y metadatos. | Respaldo incompleto, restauración fallida, huella distinta o referencia rota. El respaldo 14E sirve de referencia previa. |
| 4 | Preparar Redis autenticado con ACL y AOF y el rol PostgreSQL restringido. Preparar secretos nuevos, registro de sesiones limpio y cierre general. | Permisos excesivos, Redis público, fallo de durabilidad o imposibilidad de invalidar pases antiguos. |
| 5 | Arrancar los servicios rc.3 aprobados bajo control de ingreso. Verificar los endpoints, Celery, no-root, raíz de solo lectura, IA deshabilitada y ausencia de DDL inesperado. | Digest, montaje, rol, aislamiento o esquema distintos del plan aprobado. |
| 6 | Capturar la identidad efectiva y verificar la política pública para la CLI según Politica_autorizacion_destino.md. | Identidades, hash de política, montaje o roles incompatibles. Mantener la denegación de la CLI hasta el cierre. |
| 7 | Validar el ingreso del custodio, los permisos administrativos y la revocación. Ejecutar pruebas sintéticas aprobadas de consulta, cargue, división, Celery, PDF/A, trazabilidad y conciliación. La conciliación exige permiso específico para una sola operación. | Pérdida de acceso, sesión reactivada, error documental, alteración de huellas o fallo de conciliación. |
| 8 | Documentar resultados y decidir aceptación o rollback antes de reabrir. | Cualquier condición pendiente mantiene cerrado el acceso. Aplicar el plan de rollback si corresponde. |

Evidencia de entrada: 14G y 14H, Evidencias_14I.json y el procedimiento de respaldo al corte de 14F. La decisión futura debe registrar quién aprueba el cambio, quién custodia la cuenta y quién autoriza la conciliación concreta.
