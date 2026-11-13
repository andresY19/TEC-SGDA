"""Runs HTTP document/security tests and restarts only the new candidate project."""
from pathlib import Path
import json,re,subprocess,time
import certify_autonomous_11e as c

ROOT=Path(__file__).resolve().parents[1]
OUT='/srv/geology/expedidos/pruebas_sinteticas_11c'


def main():
    state=json.loads((ROOT/'phase11e-environment.json').read_text());c.STATE.update(state)
    assert state['project'].startswith('geology-auto11e-')
    assert json.loads((ROOT/'phase11e-auth-http.json').read_text())['returncode']==0
    runner=c.cid('runner');directory=Path(state['directory'])/'results'
    code=(ROOT/'scripts/document_security_workflow_11e.py').read_text(encoding='utf-8')
    actions=[];restarted=False
    with (directory/'document-security-stdout.txt').open('x',encoding='utf-8') as stdout, \
         (directory/'document-security-stderr.txt').open('x',encoding='utf-8') as stderr:
        process=subprocess.Popen(['docker','exec','-e','GEOLOGY_DOCUMENT_E2E=local-approved',
            '-e','GEOLOGY_E2E_HTTP_BASE=http://web:8080','-i',runner,'python','-B','-'],
            stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,text=True,encoding='utf-8')
        process.stdin.write(code);process.stdin.close()
        deadline=time.monotonic()+1200
        while process.poll() is None and time.monotonic()<deadline:
            query="from pathlib import Path;import json;print(json.dumps({'restart_ready':Path("+repr(OUT+'/ready-for-restart.json')+").exists(),'requests':[json.loads(p.read_text()) for p in Path('/cert/auth-control').glob('*.request.json') if not p.with_name(p.name.replace('.request.json','.answer.json')).exists()]}))"
            result=subprocess.run(['docker','exec',runner,'python','-B','-c',query],capture_output=True,text=True)
            assert result.returncode==0
            status=json.loads(result.stdout)
            if status['restart_ready'] and not restarted:
                ids={name:c.cid(name) for name in ['pg','redis','web','worker']}
                c.compose('stop','worker','web','redis','pg')
                for name in ['pg','redis','web','worker']:
                    c.compose('start',name);c.ready(name,name=='worker');assert c.cid(name)==ids[name]
                reply="from pathlib import Path;import json;Path("+repr(OUT+'/restart-complete.json')+").write_text(json.dumps({'status':'ok','same_containers':True}))"
                c.cmd(['docker','exec',runner,'python','-B','-c',reply]);restarted=True
                actions.append({'action':'restart_candidate_services','container_ids':ids})
            for request in status['requests']:
                operation=request['operation'];assert operation in ['stop_redis','start_redis']
                if operation=='stop_redis':c.compose('stop','redis')
                else:c.compose('start','redis');c.ready('redis');c.ready('web')
                ident=request['id'];assert re.fullmatch('[a-f0-9]{32}',ident)
                reply="from pathlib import Path;import os;p=Path('/cert/auth-control')/"+repr(ident+'.answer.json')+";t=p.with_suffix('.tmp');t.write_text('{\"status\":\"ok\"}');os.link(t,p)"
                c.cmd(['docker','exec',runner,'python','-B','-c',reply]);actions.append({'action':operation})
            (ROOT/'phase11e-document-control.json').write_text(json.dumps(actions,indent=2))
            time.sleep(.7)
        if process.poll() is None:raise RuntimeError('Document workflow timeout: inspect retained process')
    evidence={'returncode':process.returncode,'restarted':restarted,'actions':actions,
        'stdout':str(directory/'document-security-stdout.txt'),'stderr':str(directory/'document-security-stderr.txt')}
    (ROOT/'phase11e-document-tests.json').write_text(json.dumps(evidence,indent=2))
    print((directory/'document-security-stderr.txt').read_text(encoding='utf-8')[-5000:])
    assert process.returncode==0,'Document/security tests failed; no original changes'


if __name__=='__main__':main()
