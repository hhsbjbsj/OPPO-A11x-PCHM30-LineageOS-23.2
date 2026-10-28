#!/usr/bin/env python3
"""Apply exact source patches after a complete read-only preflight.

No binary replacement, source sync, clean/reset, Git commit or phone action.
Default mode is --check. Use --apply to modify the verified source files.
"""
from pathlib import Path
import argparse,datetime,hashlib,json,shutil,subprocess,sys
from backup_paths import prepare_backup_base
BASE=Path(__file__).resolve().parent.parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True)
    action=ap.add_mutually_exclusive_group();action.add_argument('--check',action='store_true');action.add_argument('--apply',action='store_true')
    ap.add_argument('--accept-file-identical-head',action='store_true',help='Allow different project HEAD only when every touched file is still byte-identical to a known before/after state')
    args=ap.parse_args();root=args.root.resolve();assert root.is_dir()
    meta=json.loads((BASE/'SOURCE-INPUTS.json').read_text());patchset=json.loads((BASE/'PATCHSET.json').read_text())
    plans=[];checked=[]
    for project in patchset['projects']:
        folder=(root/project['project']).resolve();assert folder.is_relative_to(root) and folder.is_dir(),folder
        expected=meta['projects'][project['project']][1]
        result=subprocess.run(['git','-C',str(folder),'rev-parse','HEAD'],capture_output=True,text=True)
        assert result.returncode==0,'Not a readable Git project: '+str(folder)
        actual=result.stdout.strip()
        assert actual==expected or args.accept_file_identical_head,'Project revision differs: '+project['project']+'; expected '+expected+' got '+actual
        states=[]
        for entry in project['files']:
            path=folder/entry['path'];assert path.resolve().is_relative_to(folder) and path.is_file() and not path.is_symlink(),path
            digest=sha(path.read_bytes())
            assert digest in (entry['before_sha256'],entry['after_sha256']),'Source differs; no patch applied: '+str(path)
            states.append('before' if digest==entry['before_sha256'] else 'after')
        assert len(set(states))==1,'Mixed partial patch state; inspect project before proceeding: '+project['project']
        patch=BASE/project['patch'];assert sha(patch.read_bytes())==project['patch_sha256'],'Patch file hash mismatch'
        if states[0]=='before':
            result=subprocess.run(['git','-c','core.autocrlf=false','-C',str(folder),'apply','--check',str(patch)],capture_output=True,text=True)
            assert result.returncode==0,result.stderr
            plans.append((folder,project,patch))
        checked.append({'project':project['project'],'expected_head':expected,'observed_head':actual,'state':states[0]})
    print(json.dumps({'projects_checked':len(checked),'projects_to_apply':len(plans),'files':sum(len(p['files']) for p in patchset['projects']),'details':checked},indent=2))
    if not args.apply:print('SOURCE PREFLIGHT PASSED. No files changed.');return
    backup_root=prepare_backup_base(root)
    if not plans:print('SOURCE PATCHES ALREADY APPLIED. Nothing changed.');return
    backup=backup_root/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True);saved=[]
    for folder,project,_ in plans:
        for entry in project['files']:
            src=folder/entry['path'];dst=backup/project['project']/entry['path'];dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,dst);assert sha(dst.read_bytes())==entry['before_sha256'];saved.append((src,dst,entry))
    try:
        for folder,project,patch in plans:
            result=subprocess.run(['git','-c','core.autocrlf=false','-C',str(folder),'apply',str(patch)],capture_output=True,text=True)
            assert result.returncode==0,result.stderr
            for entry in project['files']:assert sha((folder/entry['path']).read_bytes())==entry['after_sha256']
    except BaseException:
        conflicts=[]
        for src,dst,entry in saved:
            if src.is_file() and sha(src.read_bytes()) in (entry['before_sha256'],entry['after_sha256']):shutil.copy2(dst,src)
            else:conflicts.append(str(src))
        if conflicts:print('Concurrent edits preserved; inspect these paths: '+str(conflicts),file=sys.stderr)
        raise
    report={'patched_projects':[p['project'] for _,p,_ in plans],'backup':str(backup),'phone_modified':False,'binary_payloads_installed':False}
    (backup/'APPLY-REPORT.json').write_text(json.dumps(report,indent=2)+'\n')
    print('SOURCE PATCHES APPLIED. Original files verified and backed up at '+str(backup))
if __name__=='__main__':main()
