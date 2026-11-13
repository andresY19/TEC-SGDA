# Política de autorización para el destino original

Destino previsto: geology-local-20261106-57a99a. Candidata: 2.13.0-rc.3-14h. Estado: borrador verificado, pendiente de aprovisionamiento.

La política operativa usa propósito operation y permite únicamente reconcile en el worker aprobado, bajo /srv/geology/deposito, con una autorización firmada por operación. El permiso admite un consumo, vence como máximo a los 300 segundos y fija la huella de las evidencias. Una segunda firma, con vigencia máxima de 30 segundos, vincula el permiso al proceso que lo ejecuta. El ledger del anfitrión registra el consumo antes de entregar la atestación.

El borrador mantiene los IDs protegidos y deja sin completar la fotografía operativa, las claves y el ledger. max_seconds=0 impide cargarlo. Los IDs históricos identifican el destino y sirven para excluirlo del ensayo. Los IDs efectivos de la futura instalación deben cotejarse con la ventana y sus imágenes aprobadas. El nombre del proyecto es contexto y no concede acceso.

## Aprovisionamiento en la ventana aprobada

1. Registrar la aprobación expresa, los responsables y las imágenes por digest. Cotejar los contenedores actuales con Evidencias_14I.json y los recursos que se crearán con el plan aprobado. Separar la política del ensayo y sus recursos.
2. En un directorio privado del anfitrión, generar dos pares Ed25519 independientes para autoridad y ejecutor, registrar el binario Node y su SHA-256 e inicializar el ledger con initialize_ledger. Las claves privadas permanecen bajo custodia fuera de imágenes y montajes. Preparar el archivo público como borrador inactivo antes de crear los servicios candidatos.
3. Configurar FastAPI y Celery con UID/GID 10001:10001, raíz de solo lectura, capacidades eliminadas y no-new-privileges. Montar el archivo público en /run/secrets/reconciliation-policy.json como solo lectura y comprobar propietario root y que el UID efectivo no pueda escribirlo. Mantener los alias PostgreSQL y Redis internos y el rol SQL restringido. El montaje del socket Docker queda excluido.
4. Con los servicios candidatos ya autorizados y disponibles, ejecutar snapshot con propósito operation y los cuatro IDs completos. Contrastar imágenes y montajes, redes e IP, los volúmenes, la identidad del clúster PostgreSQL, el rol y los testigos de almacenamiento. Incorporar exclusivamente esa fotografía en resources. Fijar un plazo positivo de hasta 300 segundos. Verificar que anfitrión y contenedor leen la misma política pública. Si se usa un montaje directo de archivo, comprobar la huella desde el contenedor tras la escritura, ya que sustituir el archivo puede conservar un montaje sobre la versión anterior.
5. Revisar la política con el responsable de la ventana. Cualquier cambio de imagen, contenedor, red, configuración o almacenamiento exige volver a verificar la identidad. Para conciliar, exigir una autorización específica adicional y aplicar el procedimiento issue y run de 14H. Registrar 0 como conciliación, 2 como revisión humana y 77 como denegación. Una ejecución interrumpida conserva el permiso consumido y exige revisar evidencias antes de un permiso nuevo.

La prueba 14I verificó snapshot en modo operation sobre el clon, con recursos separados y sin emisión de permisos. El propósito operation sobre el destino efectivo y la integridad de su montaje público se comprueban en la ventana autorizada.
