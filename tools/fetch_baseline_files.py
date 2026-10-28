"""Fetch only exact source files required for an auditable source patchset."""
from pathlib import Path
import base64,concurrent.futures,hashlib,json,urllib.request,xml.etree.ElementTree as ET
BASE=Path(__file__).resolve().parent.parent
PROJECTS={
 'packages/modules/Connectivity':('LineageOS/android_packages_modules_Connectivity','c9f3e7795256bd4a3f99d02e604e24fd1552c2b3','github'),
 'frameworks/base':('LineageOS/android_frameworks_base','958afcc3d647d57571650cee4172afe0da619171','github'),
 'system/netd':('LineageOS/android_system_netd','796eaca5ab9dfdd87751c51bb71fa3f26c87d034','github'),
 'packages/modules/DnsResolver':('platform/packages/modules/DnsResolver','278cc346b4a2afd88e9b1155b716ebcb50dff8ca','aosp'),
 'system/memory/lmkd':('platform/system/memory/lmkd','5352c3c8c9e26cadaf31a80b1223019b2898a385','aosp'),
}
FILES={
 'packages/modules/Connectivity':[
  'service/src/com/android/server/BpfNetMaps.java','service-t/src/com/android/server/net/NetworkStatsFactory.java',
  'service-t/src/com/android/server/net/NetworkStatsService.java','service-t/src/com/android/server/net/BpfInterfaceMapHelper.java',
  'framework/src/android/net/BpfNetMapsUtils.java','framework/src/android/net/NetworkStackBpfNetMaps.java',
  'bpf/netd/NetdUpdatable.cpp','service/jni/com_android_server_connectivity_ClatCoordinator.cpp',
  'bpf/loader/netbpfload.35rc','bpf/loader/NetBpfLoad.cpp','bpf/loader/Android.bp'],
 'frameworks/base':['services/permission/java/com/android/server/permission/access/appop/AppOpService.kt','core/res/AndroidManifest.xml',
  'packages/SystemUI/src/com/android/systemui/ScreenDecorations.java',
  'packages/SystemUI/src/com/android/systemui/DisplayCutoutBaseView.kt',
  'packages/SystemUI/src/com/android/systemui/decor/CutoutDecorProviderFactory.kt'],
 'system/netd':['server/Controllers.cpp','server/netd.rc'],
 'packages/modules/DnsResolver':['DnsProxyListener.cpp'],
 'system/memory/lmkd':['lmkd.cpp'],
}
manifest=BASE/'default.xml'
project=next(p for p in ET.parse(manifest).getroot().findall('project') if p.get('path')=='packages/modules/vndk')
PROJECTS['packages/modules/vndk']=(project.get('name'),project.get('revision'),'aosp')
FILES['packages/modules/vndk']=['apex/Android.bp']
def fetch(task):
    project,path=task;repo,revision,provider=PROJECTS[project]
    if provider=='github':url=f'https://raw.githubusercontent.com/{repo}/{revision}/{path}'
    else:url=f'https://android.googlesource.com/{repo}/+/{revision}/{path}?format=TEXT'
    dst=BASE/'upstream'/project/path
    if dst.exists():b=dst.read_bytes()
    else:
        b=urllib.request.urlopen(url,timeout=45).read()
        if provider=='aosp':b=base64.b64decode(b)
        assert b and b'<!DOCTYPE html' not in b[:100]
        dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b)
    return {'project':project,'path':path,'revision':revision,'url':url,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
results=[];errors=[]
with concurrent.futures.ThreadPoolExecutor(6) as pool:
    jobs={pool.submit(fetch,(project,path)):(project,path) for project,paths in FILES.items() for path in paths}
    for job in concurrent.futures.as_completed(jobs):
        try:results.append(job.result())
        except Exception as e:errors.append({'file':jobs[job],'error':str(e)})
(BASE/'SOURCE-INPUTS.json').write_text(json.dumps({'projects':PROJECTS,'files':sorted(results,key=lambda x:(x['project'],x['path'])),'errors':errors},indent=2)+'\n')
print(json.dumps({'files_downloaded':len(results),'errors':errors},indent=2))
if errors:raise SystemExit(1)
