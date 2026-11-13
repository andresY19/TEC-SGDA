# Candidata derivada 14F

Identificación 2.13.0-rc.1+14f.2. Los identificadores técnicos y la versión API se conservan. El manifiesto identifica por digest las imágenes efectivamente ensayadas.

Los Dockerfiles usan como contexto exclusivo el directorio build, que contiene únicamente la CLI y su prueba. Ejemplo de construcción desde este directorio, con una etiqueta nueva y previa verificación del digest del padre: `docker build --pull=false --network=none -f Dockerfile.fastapi -t <etiqueta-nueva> build`. El contexto excluye los archivos privados del entorno.

Para ejecutar la CLI en un proyecto local distinto del namespace heredado, usar `python -B /opt/geology-distribution/reconcile_documents.py --operation <directorio-de-operacion> --storage-root /srv/geology/deposito --local-project <proyecto-local>`. La confirmación debe coincidir con GEOLOGY_LOCAL_PROJECT y GEOLOGY_ENTORNO debe ser local, test, testing o pruebas. LEVANTAR_AL_CARGAR debe ser no.

La confirmación del operador complementa la comprobación externa de IDs, imágenes, redes, montajes y credenciales. Por sí sola no prueba aislamiento. El proyecto original está bloqueado explícitamente.
