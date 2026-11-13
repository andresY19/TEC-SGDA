# Lista para el custodio de la cuenta histórica

Estado inicial PENDING_CUSTODIAN. La cuenta original permanece intacta. El operador técnico debe contar con la aprobación de la ventana antes de iniciar el entorno original.

| Paso | Comprobación | Resultado a completar |
|---|---|---|
| 1 | Confirmar por ID, digest, red y volumen el destino autorizado y la ventana. | PENDIENTE |
| 2 | Ingresar con la credencial custodiada por el canal autorizado. Evitar su registro en capturas, logs, URL y documentos. | PENDIENTE |
| 3 | Confirmar identidad, rol administradora, estado activo y obligación de cambiar contraseña cuando corresponda. | PENDIENTE |
| 4 | Si hay contraseña provisional, completar el cambio mediante el mecanismo existente. Comprobar el bloqueo de funciones normales antes del cambio. | PENDIENTE |
| 5 | Comprobar acceso a las funciones permitidas y rechazo de las ajenas al perfil. | PENDIENTE |
| 6 | Verificar logout y rechazo del pase revocado en la candidata, y nuevo ingreso. | PENDIENTE |
| 7 | Ante un fallo, registrar código HTTP y mensaje saneado. Mantener la ventana cerrada y utilizar un procedimiento de recuperación aprobado. | PENDIENTE |
| 8 | Registrar fecha, destino, ejecutor, custodio, resultado y referencia de evidencia sin credenciales. | PENDIENTE |

La recuperación sintética utiliza una cuenta de ensayo nueva, el hashing PBKDF2 existente y el endpoint administrativo de restablecimiento. Se comprueban el rechazo de la contraseña anterior, el cambio obligatorio y la recuperación de las funciones administrativas. Su aprobación no demuestra acceso a la cuenta histórica. Esta fase no intenta deducir ni cambiar su contraseña.
