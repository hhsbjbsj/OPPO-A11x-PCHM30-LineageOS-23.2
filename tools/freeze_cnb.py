#!/usr/bin/env python3
"""Freeze the exact tested source ROM on CNB without rebuilding or touching a phone."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

from cnb_release import Client, sha256

BASE = Path(__file__).resolve().parent.parent
TAG = 'pchm30-los23.2-source-v2-cutout-fixed'
PREFIX = 'stable/pchm30-los23.2-source-v2'
ORIGIN_URLS = {'https://cnb.cool/Anyin123f/recovery','https://cnb.cool/Anyin123f/recovery.git'}


def git(workspace, *args):
    return subprocess.check_output(['git','-C',str(workspace),*map(str,args)],text=True).strip()


def check_archive(archive, tested):
    if not archive.is_file() or archive.stat().st_size != tested['archive_bytes']:
        raise RuntimeError('Missing or wrong-size tested ROM: '+str(archive))
    print('Checking the exact device-tested ZIP (about 1.8 GiB).',flush=True)
    if sha256(archive) != tested['archive_sha256']:
        raise RuntimeError('ROM SHA256 does not match the user-tested cutout-fixed build')
    with zipfile.ZipFile(archive) as z:
        report = json.loads(z.read('BUILD-REPORT.json'))
        if report['images'] != tested['images'] or report['core_binary_overlay_used']:
            raise RuntimeError('ROM image metadata differs from the tested source build')


def check_built_files(root, tested):
    product = root/'out-pchm30-source-baseline/target/product/PCHM30'
    for entry in tested['critical_files']:
        path = entry['path']
        candidates = [product/path, product/path.removeprefix('system/')]
        found = [p for p in candidates if p.is_file() and p.stat().st_size == entry['bytes'] and sha256(p) == entry['sha256']]
        if not found:
            raise RuntimeError('Current built file differs from tested ZIP; preserve outputs and inspect: '+path)
    print('Nine built core files, including SystemUI, match the tested ZIP.',flush=True)


def publish_code(workspace, archived):
    if git(workspace,'remote','get-url','origin') not in ORIGIN_URLS:
        raise RuntimeError('Unexpected CNB origin; no branch/tag pushed')
    tag_refs = git(workspace,'ls-remote','origin','refs/tags/'+TAG,'refs/tags/'+TAG+'^{}')
    if tag_refs:
        git(workspace,'fetch','origin','refs/tags/'+TAG)
        commit = git(workspace,'rev-parse','FETCH_HEAD^{commit}')
        # Require the complete stable tree to match, not just its version name.
        expected_files = json.loads((archived/'FILES.json').read_text(encoding='utf-8'))
        for relative, expected in expected_files.items():
            result = subprocess.run(['git','-C',str(workspace),'show',commit+':'+PREFIX+'/'+relative],capture_output=True,check=True)
            if hashlib.sha256(result.stdout).hexdigest() != expected:
                raise RuntimeError('Existing immutable stable tag differs; not overwritten: '+relative)
        print('Existing source stable tag verified; reusing it.',flush=True)
        return commit, None
    git(workspace,'fetch','origin','los')
    parent = git(workspace,'rev-parse','FETCH_HEAD')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    publish = workspace/'artifacts'/('pchm30-source-freeze-publish-'+stamp)
    git(workspace,'worktree','add','--detach',str(publish),parent)
    destination = publish/PREFIX
    if destination.exists():
        for relative,expected in json.loads((archived/'FILES.json').read_text(encoding='utf-8')).items():
            path=destination/relative
            if not path.is_file() or sha256(path)!=expected:
                raise RuntimeError('Stable destination exists with different contents; preserving it for inspection')
        print('Stable source commit already pushed; completing tag publication.',flush=True)
    else:
        shutil.copytree(archived,destination)
        git(publish,'add','--force','--',PREFIX)
        git(publish,'-c','core.autocrlf=false','commit','--only','-m',
            'Freeze device-tested PCHM30 LOS23.2 native source V2 with SystemUI cutout fix','--',PREFIX)
    commit = git(publish,'rev-parse','HEAD')
    # Deliberately no force/rebase/reset or changes to the user's current branch/index.
    git(publish,'push','origin','HEAD:los')
    existing_tag=subprocess.run(['git','-C',str(publish),'rev-parse','--verify','refs/tags/'+TAG+'^{commit}'],capture_output=True,text=True)
    if existing_tag.returncode==0:
        if existing_tag.stdout.strip()!=commit:raise RuntimeError('Local stable tag points elsewhere; not overwritten')
    else:
        git(publish,'tag','-a',TAG,'-m','User-tested LOS23.2 source build including cutout fix; exact ZIP and source locks archived')
    git(publish,'push','origin','refs/tags/'+TAG)
    remote = git(publish,'ls-remote','origin','refs/heads/los','refs/tags/'+TAG+'^{}')
    values = {line.split()[1]:line.split()[0] for line in remote.splitlines()}
    if values.get('refs/heads/los') != commit or values.get('refs/tags/'+TAG+'^{}') != commit:
        raise RuntimeError('Remote commit/tag could not be verified; preserve local publish worktree')
    return commit,publish


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace',type=Path,default=Path('/workspace'))
    parser.add_argument('--root',type=Path,default=Path('/opt/lineage'))
    parser.add_argument('--archive',type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve(); root = args.root.resolve()
    tested = json.loads((BASE/'TESTED-SOURCE-V2.json').read_text(encoding='utf-8'))
    candidates = [args.archive] if args.archive else [workspace/'DOWNLOAD-ROM-SOURCE-BASELINE'/tested['archive'],workspace/tested['archive']]
    archive = next((p for p in candidates if p is not None and p.is_file()),None)
    if archive is None:
        raise RuntimeError('Keep/upload the tested ZIP in DOWNLOAD-ROM-SOURCE-BASELINE or /workspace: '+tested['archive'])
    check_archive(archive,tested)
    subprocess.run([sys.executable,str(BASE/'tools/apply.py'),'--root',str(root),'--check'],check=True)
    check_built_files(root,tested)
    firmware = workspace/'PCHM30-LOS23.2-TESTED-FIRMWARE-V1.zip'
    if not firmware.is_file(): raise RuntimeError('Keep the existing tested firmware ZIP at '+str(firmware))
    firmware_meta = json.loads((BASE/'FIRMWARE.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(firmware) as z:
        for name,entry in firmware_meta['images'].items():
            h=hashlib.sha256()
            with z.open('images/'+name+'.img') as f:
                while b:=f.read(8*1024**2):h.update(b)
            if h.hexdigest()!=entry['sha256']:raise RuntimeError('Firmware input differs: '+name)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run = workspace/'artifacts'/('pchm30-source-v2-freeze-'+stamp)
    archived = run/'archive'; archived.mkdir(parents=True)
    # Only explicitly packaged source files are copied. No .git, logs, Data or caches.
    source_files = json.loads((BASE/'SOURCE-FILES.json').read_text(encoding='utf-8'))
    for relative,expected in source_files.items():
        src = BASE/relative
        if sha256(src)!=expected:raise RuntimeError('Freeze source package modified: '+relative)
        dst=archived/'source'/relative;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    shutil.copyfile(BASE/'SOURCE-FILES.json',archived/'source/SOURCE-FILES.json')
    shutil.copyfile(BASE/'TESTED-SOURCE-V2.json',archived/'TESTED-SOURCE-V2.json')
    locks=archived/'locks';locks.mkdir()
    subprocess.run(['repo','manifest','-r','-o',str(locks/'manifest.xml')],cwd=root,check=True)
    def revisions(path):
        return {p.get('path') or p.get('name'):(p.get('name'),p.get('revision')) for p in ET.parse(path).getroot().findall('project')}
    if revisions(locks/'manifest.xml') != revisions(BASE/'default.xml'):
        raise RuntimeError('Current full manifest differs from the locked rebuild baseline; live manifest preserved at '+str(locks/'manifest.xml'))
    patchset=json.loads((BASE/'PATCHSET.json').read_text(encoding='utf-8'))
    for project in patchset['projects']:
        relative=project['project'];name=relative.replace('/','__')
        with (locks/(name+'.patch')).open('wb') as f:
            subprocess.run(['git','-C',str(root/relative),'diff','HEAD','--'],stdout=f,check=True)
    # Current device inputs must be identical to the archived rebuild recipe.
    device=root/'device/oppo/PCHM30'
    for src in (BASE/'device/oppo/PCHM30').rglob('*'):
        if src.is_file():
            relative=src.relative_to(BASE/'device/oppo/PCHM30')
            if not (device/relative).is_file() or sha256(src)!=sha256(device/relative):
                raise RuntimeError('Active device configuration differs: '+str(relative))
    # Freeze the LOS branch's environment config even when a different branch is open.
    git(workspace,'fetch','origin','los')
    los=git(workspace,'rev-parse','FETCH_HEAD')
    (locks/'cnb.yml').write_bytes(subprocess.check_output(['git','-C',str(workspace),'show',los+':.cnb.yml']))
    for relative in ['.ide/los23.2/Dockerfile','.ide/Dockerfile']:
        result=subprocess.run(['git','-C',str(workspace),'show',los+':'+relative],capture_output=True)
        if result.returncode==0:(locks/(relative.replace('/','__'))).write_bytes(result.stdout)
    files={str(p.relative_to(archived)).replace('\\','/'):sha256(p) for p in sorted(archived.rglob('*')) if p.is_file()}
    (archived/'FILES.json').write_text(json.dumps(files,indent=2)+'\n',encoding='utf-8')
    release_source=run/'PCHM30-LOS23.2-SOURCE-STABLE-V2.zip'
    with zipfile.ZipFile(release_source,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(archived.rglob('*')):
            if p.is_file():
                info=zipfile.ZipInfo(PREFIX+'/'+str(p.relative_to(archived)).replace('\\','/'),date_time=(1980,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3;info.external_attr=0o100644<<16
                z.writestr(info,p.read_bytes())
    assets=[archive,firmware,release_source]
    sums=run/'SHA256SUMS'
    sums.write_text(''.join(sha256(p)+'  '+p.name+'\n' for p in assets),encoding='utf-8')
    assets.append(sums)
    commit,publish=publish_code(workspace,archived)
    print('CNB SOURCE AND TAG PUSH VERIFIED:',commit,TAG,flush=True)
    receipt={'tag':TAG,'commit':commit,'source_and_tag_pushed':True,'release_assets_uploaded':False,'archive_sha256':tested['archive_sha256']}
    receipt_path=run/'CNB-FREEZE-RECEIPT.json'
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    client=Client()
    description='User-tested OPPO PCHM30 LOS23.2 native source build, including SystemUI cutout-fill fix.\n\nROM SHA256: '+tested['archive_sha256']+'\n\nSource: 6 projects / 19 files; locked manifest, device config and firmware inputs retained. Existing legacy BPF limitations and strict kernel FCM exception remain. No personal userdata. Original stable tags preserved.'
    release=client.release(TAG,commit,description)
    for asset in assets:client.upload(release,TAG,asset)
    receipt['release_assets_uploaded']=True
    receipt['url']='https://cnb.cool/Anyin123f/recovery/-/releases/tag/'+TAG
    receipt['assets']=[p.name for p in assets]
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print('CNB SOURCE, TESTED ROM AND FIRMWARE RELEASE FROZEN:',TAG,flush=True)
    print('Receipt:',receipt_path,flush=True)
    print('No source sync, rebuild, phone action, branch switch or workspace shutdown was performed.',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('FREEZE NOT COMPLETE:',str(error),file=sys.stderr,flush=True)
        print('Keep this workspace and rerun after correcting the reported step. Existing source/tag/assets were not overwritten.',file=sys.stderr,flush=True)
        raise SystemExit(1)
