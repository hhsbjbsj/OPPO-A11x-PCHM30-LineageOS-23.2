"""Generate readable source patches matching the tested legacy bring-up behavior."""
from pathlib import Path
import difflib,hashlib,json,re,shutil,sys
BASE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BASE/'tools'));from inspect_java import methods,walk,PARSER
UP=BASE/'upstream';OUT=BASE/'patched';CONNECT='packages/modules/Connectivity'
if OUT.exists():
    assert OUT.resolve().parent==BASE.resolve() and OUT.name=='patched'
    attempt=BASE/('attempt-%02d'%(len(list(BASE.glob('attempt-*')))+1))
    assert attempt.resolve().parent==BASE.resolve() and not attempt.exists()
    OUT.rename(attempt)
shutil.copytree(UP,OUT)
changes=[];guard_audit={}
def edit(project,path,fn):
    p=OUT/project/path;old=p.read_text(encoding='utf-8');new=fn(old);assert new!=old,(project,path)
    p.write_text(new,encoding='utf-8',newline='\n')
    a=(UP/project/path).read_bytes();b=p.read_bytes()
    changes.append({'project':project,'path':path,'before_sha256':hashlib.sha256(a).hexdigest(),
        'after_sha256':hashlib.sha256(b).hexdigest(),'patch':''.join(difflib.unified_diff(
        a.decode().splitlines(True),b.decode().splitlines(True),fromfile='a/'+path,tofile='b/'+path))})
def replace(old,new):
    def fn(s):assert s.count(old)==1,old;return s.replace(old,new,1)
    return fn
def java_edit(s,fn):
    b=s.encode();edits=[]
    for m in methods(b):
        if m['body_start'] is None:continue
        body=b[m['body_start']:m['body_end']].decode();new=fn(m,body)
        if new!=body:edits.append((m['body_start'],m['body_end'],new.encode()))
    for start,end,new in sorted(edits,reverse=True):b=b[:start]+new+b[end:]
    assert not PARSER.parse(b).root_node.has_error
    return b.decode()
def enter(body,code):return '{\n'+code+'\n'+body[1:]
def fallback(typ,name):
    if name=='getUidsMatchEnabled':return 'return java.util.Collections.emptySet();'
    if name=='getUidRule':return 'return FIREWALL_RULE_ALLOW;'
    if name=='getNetPermForUid':return 'return TRAFFIC_PERMISSION_INTERNET;'
    if name=='pullBpfMapInfoAtom':return 'return StatsManager.PULL_SKIP;'
    if typ=='void':return 'return;'
    if typ=='boolean':return 'return false;'
    if typ in ('int','long'):return 'return 0;'
    return 'return null;'
def guards_from_smali(filename):
    reference=json.loads((BASE/'GUARD-REFERENCE.json').read_text())
    name=Path(filename).stem
    return set(reference[name])
# Native/init equivalents of Stage1 diagnostic policy, Stage2-6 and Stage12.
edit(CONNECT,'bpf/loader/netbpfload.35rc',replace('    reboot_on_failure reboot,bpfloader-failed',
    '    # PCHM30 legacy bring-up: keep the real loader failure visible without rebooting.\n    # reboot_on_failure reboot,bpfloader-failed'))
edit('system/netd','server/netd.rc',lambda s:s.replace('    onrestart restart zygote','    # PCHM30 legacy bring-up: onrestart restart zygote'))
edit(CONNECT,'bpf/netd/NetdUpdatable.cpp',replace('        abort();',
    '        // PCHM30 legacy bring-up: preserve the failure log; BPF is unavailable.\n        // Continue netd startup rather than treating missing maps as process-fatal.'))
controllers=(OUT/'system/netd/server/Controllers.cpp').read_text()
mark='''        // A failure to init almost definitely means that iptables failed to load
        // our static ruleset, which then basically means network accounting will not work.
        // As such simply exit netd.  This may crash loop the system, but by failing
        // to bootup we will trigger rollback and thus this offers us protection against
        // a mainline update breaking things.
        exit(1);'''
edit('system/netd','server/Controllers.cpp',replace(mark,
    '        // PCHM30 legacy bring-up: retain this error and later Route/Xfrm checks.\n        // BPF bandwidth accounting and policy remain degraded.'))
edit('packages/modules/DnsResolver','DnsProxyListener.cpp',replace(
    '        LOG(ERROR) << __func__ << ": ADnsHelper_init failed " << strerror(-ret);\n        abort();',
    '        LOG(ERROR) << __func__ << ": ADnsHelper_init failed " << strerror(-ret);\n        // PCHM30: use the existing null-callback DNS path, not fake BPF success.\n        return nullptr;'))
edit(CONNECT,'service/jni/com_android_server_connectivity_ClatCoordinator.cpp',replace(
    '    if (fatal) abort();',
    '    if (fatal) {\n        ALOGE("PCHM30: CLAT BPF unavailable; continuing real JNI registration");\n    }'))
edit('system/memory/lmkd','lmkd.cpp',replace(
    '    if (memevent_listener) return true;\n\n    // Make sure bpf programs are loaded, else we\'ll wait until they are loaded',
    '    if (memevent_listener) return true;\n\n    // PCHM30 legacy kernel: use the caller\'s vmstats fallback without blocking.\n    // Ordinary PSI/memory-pressure monitoring, socket and OOM-score handling remain.\n    constexpr bool kLegacyKernelWithoutBpfMemevents = true;\n    if (kLegacyKernelWithoutBpfMemevents) return false;\n\n    // Make sure bpf programs are loaded, else we\'ll wait until they are loaded'))
# Stage7 BpfNetMaps: preserve initialization state and guard every tested access.
expected=guards_from_smali('android/net/connectivity/com/android/server/BpfNetMaps.smali')
actual=[]
def bpf(s):
    def fn(m,b):
        if m['owner']!='BpfNetMaps':return b
        if m['name']=='BpfNetMaps' and 'ensureInitialized(context);' in b:
            return b.replace('            ensureInitialized(context);','''            try {
                ensureInitialized(context);
            } catch (IllegalStateException e) {
                Log.e(TAG, "PCHM30: BPF maps unavailable; policy/statistics degraded", e);
            }''')
        if m['name']=='getMapSize':return enter(b,'        if (map == null) return 0;')
        if m['name'] in expected:
            # The three-argument overload delegates to the guarded addRule overload.
            if m['name']=='addRule' and len(m['parameters'])==3:return b
            actual.append(m['name'])
            return enter(b,'        if (!isBpfAvailable()) { '+fallback(m['type'],m['name'])+' }')
        return b
    s=java_edit(s,fn)
    return s[:s.rfind('}')]+'''    /** Complete initialization succeeded; false does not mean real zero usage. */
    public static boolean isBpfAvailable() {
        return sInitialized;
    }
'''+s[s.rfind('}'):]
edit(CONNECT,'service/src/com/android/server/BpfNetMaps.java',bpf)
assert set(actual)==expected,(set(actual)^expected)
guard_audit['BpfNetMaps']=sorted(expected)
# Nullable framework maps: no accidental Map dereference, keep normal-map logic.
def utils(s):
    guarded={'isChainEnabled':['configurationMap'],'getUidRule':['uidOwnerMap'],
      'getUidNetworkingBlockedReasons':['configurationMap','uidOwnerMap','dataSaverEnabledMap'],
      'isUidNetworkingBlocked':['configurationMap','uidOwnerMap','dataSaverEnabledMap'],
      'getDataSaverEnabled':['dataSaverEnabledMap']}
    seen=[]
    def fn(m,b):
        if m['name'] not in guarded:return b
        args=guarded[m['name']];assert all(a in m['parameters'] for a in args),(m,args)
        seen.append(m['name'])
        return enter(b,'        if ('+' || '.join(a+' == null' for a in args)+') { '+fallback(m['type'],m['name'])+' }')
    out=java_edit(s,fn);assert set(seen)==set(guarded)
    return out
edit(CONNECT,'framework/src/android/net/BpfNetMapsUtils.java',utils)
def null_map_catches(m,b):
    if not m['type'].startswith('IBpfMap<'):return b
    at=b.index('catch (ErrnoException e)');prefix=b[:at]
    return prefix+'''catch (ErrnoException e) {
                Log.w("PCHM30LegacyBpf", "BPF map unavailable", e);
                return null;
            }
        }'''
def stack_maps(s):
    if 'import android.util.Log;' not in s:s=s.replace('import android.', 'import android.util.Log;\n\nimport android.',1)
    return java_edit(s,lambda m,b:null_map_catches(m,b) if m['owner']=='Dependencies' else b)
edit(CONNECT,'framework/src/android/net/NetworkStackBpfNetMaps.java',stack_maps)
# Stage7+10 factory: timestamped empty snapshots only on the unsupported path.
def factory(s):
    def fn(m,b):
        if m['owner']=='Dependencies' and m['name'] in ('getNetworkStatsDetail','getNetworkStatsDev'):
            return enter(b,'''            if (!BpfNetMaps.isBpfAvailable()) {
                Log.w("PCHM30LegacyBpf", "Traffic statistics unavailable; empty snapshot is NOT measured zero usage");
                return new NetworkStats(SystemClock.elapsedRealtime(), 0);
            }''')
        return b
    return java_edit(s,fn)
edit(CONNECT,'service-t/src/com/android/server/net/NetworkStatsFactory.java',factory)
# Stage7+10 service: guards, nullable dependency maps, safe iface registration.
expected_stats=guards_from_smali('android/net/connectivity/com/android/server/net/NetworkStatsService.smali')
source_names={n for n in expected_stats if not n.startswith('lambda$') and n!='pchm30RegisterIface'}
seen=[]
def stats(s):
    if 'import com.android.server.BpfNetMaps;' not in s:
        s=s.replace('import com.android.', 'import com.android.server.BpfNetMaps;\n\nimport com.android.',1)
    def fn(m,b):
        if m['owner']=='Dependencies':
            if m['type'].startswith('IBpfMap<'):return null_map_catches(m,b)
            if m['name'] in ('nativeGetIfaceStat','nativeGetTotalStat','nativeGetUidStat'):
                return enter(b,'            if (!BpfNetMaps.isBpfAvailable()) return null;')
        if m['owner']!='NetworkStatsService':return b
        if m['name'] in source_names:
            assert m['type']=='void',m
            seen.append(m['name']);b=enter(b,'        if (!BpfNetMaps.isBpfAvailable()) return;')
        if m['name']=='NetworkStatsService':
            marker='mDeps.makeSkDestroyListener((message) -> {'
            assert marker in b
            b=b.replace(marker,marker+'\n            if (!BpfNetMaps.isBpfAvailable()) return;',1)
        if m['name']=='readNetworkStatsUidDetail':
            at='        } catch (IOException e) {\n            throw new IllegalStateException(e);'
            assert at in b
            b=b.replace(at,'''        } catch (IOException e) {
            if (!BpfNetMaps.isBpfAvailable()) {
                Log.w("PCHM30LegacyBpf", "UID traffic statistics unavailable; empty diagnostic snapshot", e);
                return new NetworkStats(SystemClock.elapsedRealtime(), 0);
            }
            throw new IllegalStateException(e);''',1)
        if m['name'] in ('deleteStatsMapTagData','dumpRawMap','dumpStatsMapLocked'):
            args=[p for p in m['parameters'] if p.lower().endswith('map') or p=='map']
            assert len(args)==1,m
            b=enter(b,'        if ('+args[0]+' == null) return;')
        if m['name']!='nativeRegisterIface':b=b.replace('nativeRegisterIface(', 'pchm30RegisterIface(')
        return b
    s=java_edit(s,fn)
    return s[:s.rfind('}')]+'''    private static void pchm30RegisterIface(String iface) {
        if (BpfNetMaps.isBpfAvailable()) nativeRegisterIface(iface);
    }
'''+s[s.rfind('}'):]
edit(CONNECT,'service-t/src/com/android/server/net/NetworkStatsService.java',stats)
assert set(seen)==source_names,(set(seen)^source_names)
guard_audit['NetworkStatsService']=sorted(expected_stats)
def iface(s):
    return java_edit(s,lambda m,b:enter(b,'        if (mIndexToIfaceBpfMap == null) return null;') if m['name']=='getIfNameByIndex' else b)
edit(CONNECT,'service-t/src/com/android/server/net/BpfInterfaceMapHelper.java',iface)
# Stage9 and Stage11 source equivalents on the actual frozen framework commit.
def appop(s):
    pattern=r'(?ms)^                    val permission =\n                        checkNotNull\(permissions\[permissionName\]\) \{.*?^                        \}'
    m=re.search(pattern,s);assert m
    new='''                    val permission = permissions[permissionName]
                    if (permission == null) {
                        Slog.w("AppOpService", "PCHM30: missing permission definition for " +
                            "$permissionName associated with app op $appOpCode; skipping mapping")
                        return@let
                    }'''
    return s[:m.start()]+new+s[m.end():]
edit('frameworks/base','services/permission/java/com/android/server/permission/access/appop/AppOpService.kt',appop)
def manifest(s):
    for name in ('MANAGE_SECURE_LOCK_DEVICE','ENTER_TRADE_IN_MODE','ACCESS_TEXT_CLASSIFIER_BY_TYPE'):
        m=re.search(r'<permission\b[^>]*android:name="android.permission\.'+name+r'"[^>]*/>',s);assert m,name
        e=m.group();new,n=re.subn(r'\s+android:featureFlag="[^"]+"','',e);assert n==1
        s=s[:m.start()]+new+s[m.end():]
    return s
edit('frameworks/base','core/res/AndroidManifest.xml',manifest)
# PCHM30: prevent factory overlays from re-enabling software cutout fill.
edit('frameworks/base','packages/SystemUI/src/com/android/systemui/ScreenDecorations.java',replace(
    '        return DisplayCutout.getFillBuiltInDisplayCutout(\n                context.getResources(), context.getDisplay().getUniqueId());',
    '        // PCHM30: ignore vendor cutout-fill overlays. Keep cutout layout unchanged.\n        return false;'))

def cutout_base(s):
    s=replace('import android.view.DisplayCutout\n','')(s)
    s=replace('    private var shouldDrawCutout: Boolean = DisplayCutout.getFillBuiltInDisplayCutout(\n        context.resources, context.display?.uniqueId\n    )',
        '    // PCHM30: never fill the cutout, including after display configuration changes.\n    private val shouldDrawCutout: Boolean = false')(s)
    return replace('            shouldDrawCutout = DisplayCutout.getFillBuiltInDisplayCutout(\n                    context.resources, displayUniqueId\n            )\n','')(s)
edit('frameworks/base','packages/SystemUI/src/com/android/systemui/DisplayCutoutBaseView.kt',cutout_base)

def cutout_factory(s):
    s=replace('import android.view.DisplayCutout\n','')(s)
    return replace('            return DisplayCutout.getFillBuiltInDisplayCutout(res, displayInfo.uniqueId)',
        '            // PCHM30: do not create software cutout-fill providers.\n            return false')(s)
edit('frameworks/base','packages/SystemUI/src/com/android/systemui/decor/CutoutDecorProviderFactory.kt',cutout_factory)
edit('packages/modules/vndk','apex/Android.bp',lambda s:s+'''
// PCHM30: retain the factory Android 11 vendor's VNDK 30 runtime.
apex_vndk {
    name: "com.android.vndk.v30",
    defaults: ["vndk-apex-defaults"],
    vndk_version: "30",
    system_ext_specific: true,
}
''')
for p in OUT.rglob('*.java'):assert not PARSER.parse(p.read_bytes()).root_node.has_error,p
projects=[]
for project in sorted({c['project'] for c in changes}):
    subset=[c for c in changes if c['project']==project]
    filename=project.replace('/','__')+'.patch';path=BASE/'patches'/filename;path.parent.mkdir(exist_ok=True)
    path.write_text(''.join(c['patch'] for c in subset),encoding='utf-8',newline='\n')
    projects.append({'project':project,'patch':'patches/'+filename,'patch_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'files':[{k:v for k,v in c.items() if k!='patch' and k!='project'} for c in subset]})
(BASE/'PATCHSET.json').write_text(json.dumps({'projects':projects,'java_map_guard_coverage':guard_audit,
    'all_runtime_core_fixes_expressed_as_source':True,'binary_offset_or_smali_patches_required':False,
    'android_compile_and_new_build_device_test':'See TESTED-SOURCE-V2.json for the exact user-tested package; future builds require validation'},indent=2)+'\n')
print(json.dumps({'projects':len(projects),'changed_files':len(changes),'java_ast_parsing':'passed'},indent=2))
