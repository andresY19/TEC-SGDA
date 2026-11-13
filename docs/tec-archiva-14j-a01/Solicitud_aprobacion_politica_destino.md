# Solicitud de aprobación de la política del destino

**Borrador para revisión del responsable del proyecto y del responsable de seguridad u operación.** Estado PENDING_APPROVAL.

Se solicita aprobar el alcance de la política de conciliación para el proyecto protegido `geology-local-20261106-57a99a` y la candidata `2.13.0-rc.3-14h`. El borrador y su procedimiento están en 14I. La evidencia de 14J fija la huella del borrador, la del manifiesto y la identidad de los recursos originales.

La política futura se aprovisionará con propósito `operation`, limitada al worker aprobado y a una sola operación de conciliación bajo `/srv/geology/deposito`. El permiso será firmado, de un solo consumo y con vigencia máxima de 300 segundos. La atestación del proceso tendrá hasta 30 segundos. Las claves privadas y el registro de consumo quedan en el anfitrión bajo custodia. La política pública se monta en solo lectura. La activación depende de cotejar la fotografía efectiva de los cuatro servicios de la candidata, sus redes, montajes, volúmenes y testigos PostgreSQL y Redis.

Se solicita una decisión **APROBADA**, **APROBADA CON CONDICIONES** o **RECHAZADA**, con nombre y rol del aprobador, fecha, referencia de la decisión, huellas revisadas y condiciones de vigencia. Registrar el responsable de aprovisionamiento y el de revisión de identidad. Un cambio en las identidades o en el alcance requiere nueva comprobación antes de operar.

La aprobación solicitada se limita al diseño y alcance de la política. El aprovisionamiento depende de la ventana aprobada. El arranque para validar al custodio, la actualización y la emisión de un permiso para una operación concreta requieren sus propias aprobaciones. El borrador de 14I conserva `max_seconds=0` y carece de recursos operativos.
