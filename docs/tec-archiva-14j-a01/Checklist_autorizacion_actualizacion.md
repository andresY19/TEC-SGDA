# Checklist de autorización para la actualización local

**UPGRADE_DECISION=NO_GO** · **UPGRADE_AUTHORIZATION=NOT_GRANTED**

| Orden | Control | Evidencia para cerrar | Estado |
|---|---|---|---|
| 1 | Destino e integridad de la candidata | IDs completos, digests y huellas cotejados. Repetir el cotejo al abrir la ventana. | Verificado en 14J |
| 2 | Validación del custodio | Resultado PASS conforme a Procedimiento_validacion_custodio.md. Si el destino sigue detenido y debe arrancar, autorización específica previa. | PENDING_CUSTODIAN |
| 3 | Aprobación de la política | Decisión registrada, versión, huella, alcance, responsables y condiciones. | Pendiente |
| 4 | Autorización expresa de actualización | Aprobador, ventana, destino, digests, acciones autorizadas, responsables, criterios de suspensión y autoridad de rollback. | NOT_GRANTED |
| 5 | Respaldo al corte dentro de la ventana | Captura protegida y restauración aislada verificadas según 14F. Cotejar catálogo, huellas y referencias. Completar antes de aplicar el cambio. | Pendiente de ventana |
| 6 | Comprobaciones antes de reabrir | Política operativa cotejada con identidades efectivas, Redis ACL/AOF, rol SQL restringido, validación administrativa, sesiones, salud y flujos documentales según 14I. | Pendiente |
| 7 | Permiso de conciliación, si procede | Aprobación específica de una operación y verificación de evidencias antes de emitir su permiso de un solo uso. | Sin emitir |
| 8 | Aceptación o rollback | Decisión registrada tras las comprobaciones y, si procede, reversión según el plan 14I. | Pendiente |

Mantener NO_GO si faltan el acceso histórico, la aprobación de la política o la autorización expresa. En la ventana, suspender antes de aplicar cambios si falla el respaldo al corte o cambia la identidad verificada. Mantener el acceso cerrado ante pérdida de acceso administrativo, reactivación de pases antiguos o diferencias documentales inexplicadas. La autorización debe distinguir las comprobaciones previas, el cambio efectivo y la reapertura.

Referencias: [Plan de actualización 14I](../tec-archiva-14i-a01/Plan_actualizacion_local.md), [Plan de rollback 14I](../tec-archiva-14i-a01/Plan_rollback_local.md) y [Respaldo al corte 14F](../tec-archiva-14f-a01/Procedimiento_respaldo_al_corte.md).
