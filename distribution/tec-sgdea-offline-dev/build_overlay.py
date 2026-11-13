"""Build a narrow overlay on the certified web, preserving routes and styles."""
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('target', type=Path)
args = parser.parse_args()
root = args.source / 'geology'
target = args.target / 'geology'
for relative in ['main.py', 'rutas/cargue.py', 'interfaz/index.html', 'interfaz/tec-archiva.css']:
    source = (root / relative).read_text(encoding='utf-8-sig')
    if relative == 'main.py':
        marker = 'aplicacion.include_router(cuentas.router)'
        assert source.count(marker) == 1
        source = source.replace(marker, 'from geology.rutas import offline_sync\n\n' + marker +
                                '\naplicacion.include_router(offline_sync.router)')
    elif relative == 'rutas/cargue.py':
        marker = '    if not quien.edita_hoja_control:'
        position = source.index(marker, source.index('async def cargar('))
        source = source[:position] + '''    return await cargar_documento(archivo, db, quien, reemplazar, definitiva)


async def cargar_documento(archivo, db, quien, reemplazar=False, definitiva=False, *, sync_commit=None):
''' + source[position:]
        marker = '        commit_intentado = True\n        db.commit()'
        assert source.count(marker) == 1
        source = source.replace(marker, '''        if sync_commit is not None:
            sync_commit(exp, sha)
''' + marker)
    else:
        source = source.replace('TEC-ARCHIVA', 'TEC-SGDEA').replace('>TA</span>', '>TS</span>')
    path = target / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
