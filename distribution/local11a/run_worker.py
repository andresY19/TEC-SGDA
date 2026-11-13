"""No shell interpolation; queue ownership is additionally validated by cola.py."""
import os
import re

queue = os.environ.get('GEOLOGY_COLA', '')
project = os.environ.get('GEOLOGY_LOCAL_PROJECT', '')
if not queue.startswith(project+'-') or not re.fullmatch(r'[A-Za-z0-9_.-]{1,149}', queue):
    raise RuntimeError('Exclusive local queue required')
os.execvp('celery', ['celery','-A','geology.nucleo.cola.celery_app','worker',
                     '--loglevel=INFO','--concurrency=1','-Q',queue])
