"""Patch application, idempotency, drift rejection, Java parsing and XML checks."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tempfile,xml.etree.ElementTree as ET
BASE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BASE/'tools'));from inspect_java import PARSER
GIT=shutil.which('git');assert GIT
data=json.loads((BASE/'PATCHSET.json').read_text());fixture=BASE/'validation-fixture'
if fixture.exists():
    assert fixture.resolve().parent==BASE.resolve()
    dst=BASE/('fixture-attempt-%02d'%(len(list(BASE.glob('fixture-attempt-*')))+1))
    assert dst.resolve().parent==BASE.resolve() and not dst.exists();fixture.rename(dst)
fixture.mkdir();tests=[]
def run(args,expected=0):
    p=subprocess.run(args,capture_output=True)
    assert (p.returncode==0)==(expected==0),(args,p.stdout.decode(errors='replace'),p.stderr.decode(errors='replace'))
    return p
for p in data['projects']:
    folder=fixture/p['project'];folder.mkdir(parents=True)
    for entry in p['files']:
        src=BASE/'upstream'/p['project']/entry['path'];dst=folder/entry['path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    run([GIT,'init','-q',str(folder)])
    run([GIT,'-C',str(folder),'add','.'])
    run([GIT,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-C',str(folder),'commit','-qm','Exact source fixture'])
    run([GIT,'-C',str(folder),'apply','--check',str(BASE/p['patch'])])
apply=[sys.executable,str(BASE/'tools/apply.py'),'--root',str(fixture),'--accept-file-identical-head']
run(apply+['--check']);tests.append('all six projects preflight before any mutation')
run(apply+['--apply']);tests.append('all %d exact source files applied and post-hashed'%sum(len(p['files']) for p in data['projects']))
run(apply+['--apply']);tests.append('second apply is idempotent')
for p in data['projects']:
    for entry in p['files']:
        path=fixture/p['project']/entry['path'];b=path.read_bytes()
        assert hashlib.sha256(b).hexdigest()==entry['after_sha256']
        if path.suffix=='.java':assert not PARSER.parse(b).root_node.has_error
tests.append('all modified Java sources parse without syntax errors')
manifest=fixture/'frameworks/base/core/res/AndroidManifest.xml';root=ET.parse(manifest).getroot();ns='{http://schemas.android.com/apk/res/android}'
for name,protection in [('MANAGE_SECURE_LOCK_DEVICE','signature|privileged'),('ENTER_TRADE_IN_MODE','signature|privileged'),('ACCESS_TEXT_CLASSIFIER_BY_TYPE','signature|role|privileged')]:
    p=next(p for p in root.findall('permission') if p.get(ns+'name')=='android.permission.'+name)
    assert p.get(ns+'protectionLevel')==protection and p.get(ns+'featureFlag') is None
tests.append('three permissions retain original protection levels; only their gates removed')
target=fixture/data['projects'][0]['project']/data['projects'][0]['files'][0]['path'];old=target.read_bytes();target.write_bytes(old+b'\n// unexpected source drift\n')
run(apply+['--apply'],expected=1);target.write_bytes(old)
tests.append('unrecognized source drift rejected before modification')
report={'checks':tests,'projects':len(data['projects']),'changed_files':sum(len(p['files']) for p in data['projects']),
    'full_android_compilation_performed':False,'new_source_build_phone_test_performed':False}
(BASE/'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
