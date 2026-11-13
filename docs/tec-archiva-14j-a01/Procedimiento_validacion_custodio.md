# Procedimiento de validación del custodio histórico

Estado PENDING_CUSTODIAN. El custodio deberá realizar personalmente la comprobación y aportar un resultado saneado.

1. El responsable del destino identifica al custodio, la cuenta histórica y el entorno aprobado. Cotejar los IDs con Evidencia_lectura_14J.json.
2. Definir la ventana y el alcance del ingreso. Si se requiere iniciar servicios originales, obtener autorización específica para ese arranque. Antes de aprobar el ingreso, considerar las escrituras propias de autenticación, como contadores, trazas o sesiones.
3. El custodio ingresa por el canal autorizado y confirma identidad, cuenta activa, rol administrativo y acceso a una función de consulta permitida. El operador registra únicamente el resultado, la hora y la referencia de evidencia.
4. Si se solicita un cambio obligatorio de contraseña, el ingreso falla o el rol difiere, suspender la validación. Documentar el motivo y revisar con el custodio el procedimiento de recuperación. Todo cambio de credenciales requiere una autorización aparte.
5. Registrar PASS si el ingreso y los controles de acceso quedaron demostrados, FAIL si un ensayo autorizado falló, o PENDING_CUSTODIAN si aún falta evidencia. La recuperación sintética aporta evidencia del procedimiento de ensayo.

| Campo para completar | Registro |
|---|---|
| Custodio y referencia de cuenta | Pendiente |
| Destino e IDs verificados | Pendiente |
| Aprobación, fecha y alcance | Pendiente |
| Resultado del ingreso, rol y consulta | Pendiente |
| Referencia de evidencia saneada | Pendiente |
| Resultado y conformidad del custodio | PENDING_CUSTODIAN |

Las evidencias deben excluir contraseñas, tokens, cabeceras de autorización y capturas que los revelen.
