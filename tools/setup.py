#!/usr/bin/env python3
"""Install owned device configuration and verified firmware into the source tree."""
from pathlib import Path
import argparse,datetime,hashlib,json,shutil,subprocess,zipfile
from backup_paths import prepare_backup_base
BASE=Path(__file__).resolve().parent.parent
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(8*1024**2):h.update(b)
    return h.hexdigest()
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--firmware',type=Path,required=True);args=ap.parse_args()
root=args.root.resolve();assert (root/'build/envsetup.sh').is_file()
subprocess.run(['python3',str(BASE/'tools/apply.py'),'--root',str(root),'--check'],check=True)
device=root/'device/oppo/PCHM30';firmware=root/'vendor/oppo/pchm30-tested-firmware'
assert not device.is_symlink() and not firmware.is_symlink()
if device.exists():
    known=['.pchm30-source-baseline-owned','.pchm30-native-full-test1','.pchm30-config-pass.json']
    assert any((device/k).exists() for k in known),'Unrecognized device tree; preserve it and use an isolated checkout'
meta=json.loads((BASE/'FIRMWARE.json').read_text())
with zipfile.ZipFile(args.firmware) as z:
    assert len(z.namelist())==len(set(z.namelist()))
    for name,entry in meta['images'].items():
        member='images/'+name+'.img';info=z.getinfo(member);assert info.file_size==entry['bytes']
        h=hashlib.sha256()
        with z.open(member) as f:
            while b:=f.read(8*1024**2):h.update(b)
        assert h.hexdigest()==entry['sha256'],'Firmware differs: '+name
    firmware.mkdir(parents=True,exist_ok=True)
    for name,entry in meta['images'].items():
        dst=firmware/(name+'.img');assert not dst.is_symlink()
        if dst.is_file() and digest(dst)==entry['sha256']:continue
        temporary=firmware/(name+'.img.partial');assert not temporary.exists()
        with z.open('images/'+name+'.img') as src,temporary.open('xb') as out:shutil.copyfileobj(src,out,8*1024**2)
        assert digest(temporary)==entry['sha256'];temporary.replace(dst)
backup=prepare_backup_base(root)/('device-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
if device.exists():shutil.copytree(device,backup,symlinks=True)
for src in (BASE/'device/oppo/PCHM30').rglob('*'):
    if src.is_file():
        dst=device/src.relative_to(BASE/'device/oppo/PCHM30');assert not dst.is_symlink();dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
(device/'.pchm30-source-baseline-owned').write_text('PCHM30 source baseline v1\n')
subprocess.run(['python3',str(BASE/'tools/apply.py'),'--root',str(root),'--apply'],check=True)
print('SOURCE BASELINE READY: native source fixes + device tree + verified firmware. No phone flashed.')
