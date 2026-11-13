"""Offline PDF/A-1b experiment. New outputs on C:, existing PDFs read-only.

Does not import GEOLOGY, connect to data services, or change configuration.
Keeps the experiment directory; no input/output file is deleted or replaced.
"""
from pathlib import Path
import subprocess,tempfile,json,hashlib,shutil,os

ROOT=Path(__file__).resolve().parents[1]

def main():
    old=json.loads((ROOT/'phase9a-final-verification.json').read_text())
    source=old['synthetic_files'];assert len(source)==3
    for n,h in old['depot_hashes'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    tempbase=Path(tempfile.gettempdir());assert tempbase.drive.lower()=='c:'
    # Conservative illustrative upper working set: all 254 synthetic pages as
    # two uncompressed A4 RGB raster sets at 300 dpi, although text is skipped.
    reserve=254*2481*3507*3*2
    free=shutil.disk_usage(tempbase).free;assert free>reserve
    out=Path(tempfile.mkdtemp(prefix='geology-9c-pdfa1b-',dir=tempbase))
    code='''import json,subprocess,hashlib,re,os,xml.etree.ElementTree as ET
from pathlib import Path
import pikepdf
from pdfminer.high_level import extract_text
items=ITEMS
out=Path('/output');results=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def text(p):return re.sub(r'\\s+',' ',extract_text(p)).strip()
versions={'gs':subprocess.check_output(['gs','--version'],text=True).strip(),'veraPDF':subprocess.check_output(['/opt/verapdf/verapdf','--version'],text=True).strip(),'ocrmypdf':subprocess.check_output(['ocrmypdf','--version'],text=True).strip()}
for item in items:
 source=Path('/input')/Path(item['path']).relative_to('/srv/geology/deposito')
 before=sha(source);assert before==item['sha256']
 with pikepdf.open(source) as pdf:pages=len(pdf.pages)
 expected=text(source)
 for kind,key in [('matrix','matrix'),('consultation','consultation')]:
  target=out/f"archivo-{item['id']}-{kind}-pdfa1b.pdf";assert not target.exists()
  args=['ocrmypdf','--output-type','pdfa-1','--skip-text','--jobs','1','--quiet']
  if kind=='matrix':args+=['--optimize','0']
  else:args+=['--deskew','--clean-final','--rotate-pages','--tesseract-timeout','0']
  p=subprocess.run(args+[str(source),str(target)],capture_output=True,text=True,timeout=240)
  (out/(target.stem+'-conversion.log')).write_text(p.stdout+p.stderr)
  assert p.returncode==0,(target.name,p.stderr[-1000:])
  v=subprocess.run(['/opt/verapdf/verapdf','--flavour','1b','--format','xml','--addlogs','--loglevel','2',str(target)],capture_output=True,text=True,timeout=180)
  (out/(target.stem+'-verapdf.xml')).write_text(v.stdout)
  (out/(target.stem+'-verapdf.stderr.txt')).write_text(v.stderr)
  report=ET.fromstring(v.stdout).find('.//validationReport');assert report is not None
  with pikepdf.open(target) as pdf:
   n=len(pdf.pages);syntax=pdf.check_pdf_syntax()
   with pdf.open_metadata() as meta:profile=str(meta.get('pdfaid:part'))+str(meta.get('pdfaid:conformance')).lower()
  previous=Path('/input')/Path(item[key]).relative_to('/srv/geology/deposito')
  entry={'source':item['path'],'source_sha256':before,'kind':kind,'output':target.name,'output_bytes':target.stat().st_size,'output_sha256':sha(target),'old_2b_path':item[key],'old_2b_sha256':sha(previous),'old_2b_bytes':previous.stat().st_size,'profile':profile,'pages':n,'page_count_equal':n==pages,'text_and_order_equal':text(target)==expected,'syntax_messages':syntax,'validation':report.attrib,'details':report.find('details').attrib,'validation_returncode':v.returncode,'validation_stderr':v.stderr,'conversion_returncode':p.returncode}
  assert entry['page_count_equal'] and entry['text_and_order_equal'] and not syntax
  assert profile=='1b' and entry['validation']['isCompliant']=='true' and entry['details']['failedChecks']=='0'
  assert sha(source)==before
  results.append(entry)
result={'versions':versions,'results':results,'all_pass':len(results)==6,'network':'none','documents_read_only':True,'application_environment_not_supplied':True}
(out/'experiment-results.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'all_pass':result['all_pass'],'outputs':len(results)}))
'''.replace('ITEMS',repr(source))
    p=subprocess.run(['docker','run','--rm','-i','--network','none','--read-only','--tmpfs','/tmp:rw,size=512m',
        '--memory','1g','--cpus','2','--cap-drop','ALL','--security-opt','no-new-privileges','-e','HOME=/tmp',
        '-v',str(ROOT/'deposito')+':/input:ro','-v',str(out)+':/output','--entrypoint','python',
        'geology-local-20261106-57a99a:2.13.0-9a','-B','-'],input=code,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=900)
    for n,h in old['depot_hashes'].items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    data={'directory':str(out),'free_C_before_bytes':free,'conservative_working_set_bytes':reserve,
        'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr,'existing_depot_unchanged':True,
        'experiment':json.loads((out/'experiment-results.json').read_text()) if (out/'experiment-results.json').exists() else None}
    (ROOT/'phase9c-pdfa-experiment.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k!='experiment'},indent=2))

if __name__=='__main__':main()
