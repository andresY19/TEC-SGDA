"""Add a transactional receipt hook to the runtime's existing advance handler."""
from pathlib import Path
import sys

path = Path(sys.argv[1])
code = path.read_text(encoding='utf-8')
start = code.index('def cargar_hoja(')
end = code.index('    resultado = verificar_hoja(', start)
block = code[start:end]
signature = '                quien: Usuario = Depends(usuario_actual)) -> dict:\n'
assert block.count(signature) == 1
block = block.replace(signature, signature + '''    return guardar_hoja(hoja, db, quien)


def guardar_hoja(hoja, db, quien, *, sync_commit=None):
''')
marker = '        db.commit()\n'
assert block.count(marker) == 1
block = block.replace(marker, '        if sync_commit is not None:\n            sync_commit()\n' + marker)
path.write_text(code[:start]+block+code[end:], encoding='utf-8')
