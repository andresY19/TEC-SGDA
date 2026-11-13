#!/bin/sh
# Instala veraPDF (validador de referencia de PDF/A) en /opt/verapdf. Requiere Java 11 o superior.
# Uso: sh scripts/instalar_verapdf.sh   ·   Luego: VERAPDF_BIN=/opt/verapdf/verapdf en el .env
set -e
TMP=$(mktemp -d)
cd "$TMP"
curl -fsSL -o instalador.zip https://software.verapdf.org/releases/verapdf-installer.zip
unzip -q instalador.zip
CARPETA=$(ls -d verapdf-greenfield-* | head -n 1)
cp "$OLDPWD/scripts/verapdf-auto.xml" "$CARPETA/auto.xml" 2>/dev/null || cp "$(dirname "$0")/verapdf-auto.xml" "$CARPETA/auto.xml"
cd "$CARPETA"
java -DINSTALL_PATH=/opt/verapdf -jar verapdf-izpack-installer-*.jar auto.xml
/opt/verapdf/verapdf --version
