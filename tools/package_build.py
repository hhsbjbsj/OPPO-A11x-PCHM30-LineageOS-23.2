#!/usr/bin/env python3
"""Package a NEW SOURCE-BUILT System plus explicitly verified firmware inputs."""
from pathlib import Path
import argparse,datetime,hashlib,json,shutil,struct,subprocess,zipfile
BASE=Path(__file__).resolve().parent.parent
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
root=args.root.resolve();output=args.out.resolve();product=output/'target/product/PCHM30';tools=output/'host/linux-x86/bin'
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
destination=Path('/workspace/DOWNLOAD-ROM-SOURCE-BASELINE');destination.mkdir(parents=True,exist_ok=True)
run=destination/('work-'+stamp);run.mkdir()
raw=run/'system.img';src=product/'system.img';assert src.is_file()
with src.open('rb') as f:sparse=f.read(4)==bytes.fromhex('3aff26ed')
if sparse:subprocess.run([str(tools/'simg2img'),str(src),str(raw)],check=True)
else:shutil.copyfile(src,raw)
assert raw.stat().st_size==5473566720,'System size differs from the physical partition; do not repartition'
firmware=root/'vendor/oppo/pchm30-tested-firmware';meta=json.loads((BASE/'FIRMWARE.json').read_text())
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(8*1024**2):h.update(b)
    return h.hexdigest()
images={'system':raw}
for name,entry in meta['images'].items():
    p=firmware/(name+'.img');assert p.stat().st_size==entry['bytes'] and digest(p)==entry['sha256'];images[name]=p
critical=[]
for path in ['system/bin/netd','system/bin/lmkd','system/etc/init/netd.rc','system/framework/services.jar','system/framework/framework-res.apk','system/product/etc/build.prop',
             'system/apex/com.android.tethering.apex','system/apex/com.android.resolv.apex',
             'system/system_ext/priv-app/SystemUI/SystemUI.apk']:
    candidates=[path] if not path.endswith('.apex') else [path,path[:-5]+'.capex']
    found=[]
    for candidate in candidates:
        dst=run/(candidate.replace('/','_'))
        result=subprocess.run([str(tools/'debugfs'),'-R','dump /'+candidate+' '+str(dst),str(raw)],capture_output=True)
        if dst.is_file() and dst.stat().st_size>0:found.append((candidate,dst))
    assert len(found)==1,'Missing or ambiguous generated core file: '+path
    candidate,dst=found[0];critical.append((digest(dst),candidate))
    if path.endswith('build.prop'):assert 'ro.bpf.kver_override=5.10.239' in dst.read_text()
order=['system','vendor','dtbo','boot','vbmeta'];nodes={'system':'sda7','vendor':'sde16','dtbo':'sde18','boot':'sde11','vbmeta':'sde17'}
chunks=[];full={};archive=destination/('PCHM30-LOS23.2-SOURCE-CANDIDATE-V1-'+stamp+'.zip')
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
    for name in order:
        print('Packaging native source output:',name,flush=True)
        with images[name].open('rb') as f:
            offset=0;index=0;whole=hashlib.sha256()
            while offset<images[name].stat().st_size:
                size=min(512*1024**2,images[name].stat().st_size-offset);member=f'images/{name}.{index:03d}.raw'
                h=hashlib.sha256();left=size
                info=zipfile.ZipInfo(member);info.file_size=size;info.compress_type=zipfile.ZIP_DEFLATED;info._compresslevel=1
                with z.open(info,'w') as dst:
                    while left:
                        b=f.read(min(8*1024**2,left));assert b;dst.write(b);h.update(b);whole.update(b);left-=len(b)
                chunks.append((name,offset//4096,size//4096,h.hexdigest(),member));offset+=size;index+=1
        full[name]={'bytes':offset,'sha256':whole.hexdigest()}
    z.writestr('chunks.list',''.join(f'{n} {o} {b} {h} {m}\n' for n,o,b,h,m in chunks))
    z.writestr('partition-sizes.list',''.join(f'{n} {images[n].stat().st_size} {nodes[n]}\n' for n in order))
    z.writestr('final-files.list',''.join(h+' '+p+'\n' for h,p in critical))
    script=(BASE/'tools/update-binary.sh').read_text().replace('FROZEN V1','SOURCE CANDIDATE V1').replace('Frozen images','Source-built images')
    info=zipfile.ZipInfo('META-INF/com/google/android/update-binary');info.create_system=3;info.external_attr=0o100755<<16;z.writestr(info,script)
    z.writestr('META-INF/com/google/android/updater-script','# Uses packaged guarded shell updater.\n')
    z.writestr('BUILD-REPORT.json',json.dumps({'origin':'Native source-built System; tested firmware inputs','images':full,'core_binary_overlay_used':False,'new_device_tested':False,'vbmeta_flags':3,'strict_kernel_fcm_passed':False},indent=2))
with zipfile.ZipFile(archive) as z:
    assert len(z.namelist())==len(set(z.namelist()))
    for name,offset,blocks,expected,member in chunks:
        h=hashlib.sha256();size=0
        with z.open(member) as f:
            while b:=f.read(8*1024**2):h.update(b);size+=len(b)
        assert h.hexdigest()==expected and size==blocks*4096
archive.with_suffix('.zip.sha256').write_text(digest(archive)+'  '+archive.name+'\n')
print('SOURCE CANDIDATE CREATED AND CHUNK VERIFIED:',archive)
print('No phone flashing performed. This new source build still needs device testing.')
