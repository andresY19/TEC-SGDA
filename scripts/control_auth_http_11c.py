"""Control only new 11B services while HTTP tests retain secrets in memory."""
from pathlib import Path
import json
import re
import subprocess
import time

import certify_candidate_distribution_11c as c
ROOT=Path(__file__).resolve().parents[1]


def main():
    state=json.loads((ROOT/'phase11c-environment.json').read_text());c.STATE.update(state)
    assert state['project'].startswith('geology-cand11c-')
    assert state['stage']=='CERTIFIED_PENDING_ORIGINAL_FINAL_COMPARISON'
    runner=c.cid('runner');out=Path(state['directory'])/'results'
    code=(ROOT/'scripts/http_sessions_11c.py').read_text(encoding='utf-8')
    events=[]
    with (out/'auth-http-stdout.txt').open('x',encoding='utf-8') as stdout, \
         (out/'auth-http-stderr.txt').open('x',encoding='utf-8') as stderr:
        p=subprocess.Popen(['docker','exec','-i',runner,'python','-B','-'],stdin=subprocess.PIPE,
                           stdout=stdout,stderr=stderr,text=True,encoding='utf-8')
        p.stdin.write(code);p.stdin.close()
        deadline=time.monotonic()+900
        while p.poll() is None and time.monotonic()<deadline:
            query="from pathlib import Path;import json;print(json.dumps([json.loads(p.read_text()) for p in Path('/cert/auth-control').glob('*.request.json') if not p.with_name(p.name.replace('.request.json','.answer.json')).exists()]))"
            r=subprocess.run(['docker','exec',runner,'python','-B','-c',query],capture_output=True,text=True)
            if r.returncode:raise RuntimeError('Cannot read isolated test control state')
            for request in json.loads(r.stdout):
                operation=request['operation'];answer={'status':'ok'}
                if operation=='stop_redis':
                    c.compose('stop','redis')
                elif operation=='start_redis':
                    c.compose('start','redis');c.ready('redis');c.ready('web')
                elif operation=='restart_apps':
                    c.compose('stop','worker','web');c.compose('start','web');c.ready('web')
                    c.compose('start','worker');c.ready('worker',True)
                elif operation=='audit_logs':
                    matches=0
                    for name in ['web','worker']:
                        log=subprocess.run(['docker','logs',c.cid(name)],capture_output=True,text=True,encoding='utf-8',errors='replace')
                        matches+=len(re.findall(r'\bg1\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{43}\b',log.stdout+log.stderr))
                    answer['token_matches']=matches
                else:raise RuntimeError('Unexpected test control operation')
                ident=request['id'];assert re.fullmatch('[a-f0-9]{32}',ident)
                reply="from pathlib import Path;import json,os;p=Path('/cert/auth-control')/"+repr(ident+'.answer.json')+";t=p.with_suffix('.tmp');t.write_text("+repr(json.dumps(answer))+");os.link(t,p)"
                c.cmd(['docker','exec',runner,'python','-B','-c',reply]);events.append({'operation':operation,**answer})
                (ROOT/'phase11c-auth-control.json').write_text(json.dumps(events,indent=2),encoding='utf-8')
            time.sleep(.4)
        if p.poll() is None:raise RuntimeError('HTTP session test timeout; retained process requires diagnosis')
    result={'returncode':p.returncode,'control_events':events,
            'stdout':str(out/'auth-http-stdout.txt'),'stderr':str(out/'auth-http-stderr.txt')}
    (ROOT/'phase11c-auth-http.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print((out/'auth-http-stderr.txt').read_text(encoding='utf-8')[-4500:])
    assert p.returncode==0,'HTTP session suite failed; no production changes'


if __name__=='__main__':main()
