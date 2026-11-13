"""Orquesta una única corrida sintética y reinicio de servidor/worker propios.

No inicia infraestructura, no construye imágenes ni limpia fixtures anteriores.
--resume-owned-setup solo recupera el setup 9A anterior a cualquier cargue.
"""
from pathlib import Path
import subprocess,json,time,sys

ROOT=Path(__file__).resolve().parents[1]
PROJECT='geology-local-20261106-57a99a'
OUT=ROOT/'expedidos/pruebas_sinteticas_9a'


def main():
    assert not (OUT/'ready-for-restart.json').exists(),'Checkpoint previo: revisar antes de repetir'
    cmd=['docker','compose','--env-file','.env','-f','compose.local.yml','-p',PROJECT,'--profile','application',
        'run','--rm','--no-deps','-T','-e','GEOLOGY_DOCUMENT_E2E=local-approved',
        '-e','GEOLOGY_E2E_HTTP_BASE=http://servidor:8080']
    if '--resume-owned-setup' in sys.argv:cmd+=['-e','GEOLOGY_E2E_RESUME=owned-fixture']
    recovery='--recovery' in sys.argv
    test='integration_documental_recovery_local.py' if recovery else 'integration_documental_local.py'
    cmd+=['--volume',str(ROOT/'tests')+':/work/tests:ro','--entrypoint','python','servidor',
        '-B','/work/tests/'+test,'-v']
    p=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    restarted=False;start=time.monotonic();last=0
    while p.poll() is None:
        if (OUT/'ready-for-restart.json').exists() and not restarted:
            print('Flow ready for controlled restart.',flush=True)
            for service in ('servidor','procesador'):
                name=PROJECT+'-'+service+'-1'
                old=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
                assert old['Config']['Labels']['com.docker.compose.project']==PROJECT
                subprocess.run(['docker','restart','--time','10',name],capture_output=True,check=True)
                for _ in range(40):
                    c=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
                    assert c['Id']==old['Id']
                    if service=='servidor':ready=c['State'].get('Health',{}).get('Status')=='healthy'
                    else:
                        log=subprocess.run(['docker','logs','--since',c['State']['StartedAt'],name],capture_output=True,text=True)
                        ready=' ready.' in log.stdout+log.stderr
                    if ready:break
                    time.sleep(1)
                else:raise RuntimeError('Controlled restart failed: '+service)
            (OUT/'restart-complete.json').write_text(json.dumps({'services':['servidor','procesador'],'same_containers':True}),encoding='utf-8')
            restarted=True
        elapsed=int(time.monotonic()-start)
        if elapsed-last>=30:print('Synthetic E2E running, seconds:',elapsed,flush=True);last=elapsed
        if elapsed>540:raise RuntimeError('E2E execution timeout; inspect before continuing')
        time.sleep(1)
    a,b=p.communicate();f=ROOT/('phase9a-recovery-results.json' if recovery else 'phase9a-functional-results.json')
    data={'returncode':p.returncode,'stdout':a,'stderr':b,'restart_performed':restarted}
    if f.exists():data['previous_attempt']=json.loads(f.read_text(encoding='utf-8'))
    f.write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(b[-8500:] if p.returncode else b[-2200:],flush=True)
    return p.returncode


if __name__=='__main__':sys.exit(main())
