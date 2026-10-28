"""Compile and execute ACTUAL patched Java method bodies with API doubles."""
from pathlib import Path
import json,os,shutil,subprocess,sys
BASE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BASE/'tools'));from inspect_java import methods
def extract(path,name,owner):
    b=(BASE/'patched/packages/modules/Connectivity'/path).read_bytes()
    matches=[m for m in methods(b) if m['name']==name and m['owner']==owner];assert len(matches)==1
    m=matches[0];return b[m['start']:m['end']].decode()
deps='\n'.join(extract('service-t/src/com/android/server/net/NetworkStatsFactory.java',name,'Dependencies') for name in ('getNetworkStatsDetail','getNetworkStatsDev'))
uid=extract('service-t/src/com/android/server/net/NetworkStatsService.java','readNetworkStatsUidDetail','NetworkStatsService')
source='''import java.io.IOException;
public class SourceRuntimeGuardsTest {
 @interface NonNull {}
 static class BpfNetMaps { static boolean available; static boolean isBpfAvailable(){return available;} }
 static class SystemClock {static long now;static long elapsedRealtime(){return now;}}
 static class NetworkStats {long stamp;int count;NetworkStats(long t,int n){stamp=t;count=n;}}
 static class Log {static int warnings;static int w(String t,String s){warnings++;return 0;} static int w(String t,String s,Throwable e){warnings++;return 0;}}
 static int nativeCalls,nativeResult;
 static int nativeReadNetworkStatsDetail(NetworkStats n){nativeCalls++;return nativeResult;}
 static int nativeReadNetworkStatsDev(NetworkStats n){nativeCalls++;return nativeResult;}
 static class FactoryDeps { REPLACE_DEPS }
 static class Factory { boolean error; NetworkStats result=new NetworkStats(99,3); IOException cause=new IOException("real I/O error");
  NetworkStats readNetworkStatsDetail(int uid,String[] ifaces,int tag)throws IOException{if(error)throw cause;return result;}}
 static class StatsService { Factory mStatsFactory=new Factory(); REPLACE_UID }
 static void check(boolean v){if(!v)throw new AssertionError();}
 public static void main(String[]args)throws Exception{
  int cases=0;
  for(boolean available:new boolean[]{false,true}) for(int error:new int[]{0,-5}) for(long clock:new long[]{0,123456789}){
   BpfNetMaps.available=available;SystemClock.now=clock;nativeResult=error;
   for(boolean dev:new boolean[]{false,true}){
    nativeCalls=0;Log.warnings=0;
    try{
     NetworkStats stats=dev?new FactoryDeps().getNetworkStatsDev():new FactoryDeps().getNetworkStatsDetail();
     check(!available||error==0);check(stats.stamp==clock);
     if(!available){check(stats.count==0&&nativeCalls==0&&Log.warnings==1);}else check(nativeCalls==1&&Log.warnings==0);
    }catch(IOException e){check(available&&error!=0&&nativeCalls==1);}cases++;
   }
   StatsService service=new StatsService();service.mStatsFactory.error=error!=0;Log.warnings=0;
   try{
    NetworkStats stats=service.readNetworkStatsUidDetail(42,null,0);
    if(error==0)check(stats==service.mStatsFactory.result);else check(!available&&stats.count==0&&stats.stamp==clock&&Log.warnings==1);
   }catch(IllegalStateException e){check(available&&error!=0&&e.getCause()==service.mStatsFactory.cause);}cases++;
  }
  check(cases==24);System.out.println("PASS: 24 cases executed from the actual three patched Java method bodies; unsupported paths avoid native reads, normal paths and real I/O errors remain.");
 }
}'''.replace('REPLACE_DEPS',deps).replace('REPLACE_UID',uid)
folder=BASE/'.smoke-build';folder.mkdir(exist_ok=True);file=folder/'SourceRuntimeGuardsTest.java';file.write_text(source,encoding='utf-8',newline='\n')
java_bin=os.environ.get('PCHM30_JAVA_BIN')
javac=str(Path(java_bin)/('javac.exe' if os.name=='nt' else 'javac')) if java_bin else shutil.which('javac')
java=str(Path(java_bin)/('java.exe' if os.name=='nt' else 'java')) if java_bin else shutil.which('java')
assert java and javac,'Install a JDK, or set PCHM30_JAVA_BIN'
for command in [[javac,str(file)],[java,'-cp',str(folder),'SourceRuntimeGuardsTest']]:
    p=subprocess.run(command,capture_output=True);assert p.returncode==0,p.stderr.decode(errors='replace')
    if p.stdout:print(p.stdout.decode())
report=json.loads((BASE/'VALIDATION.json').read_text());report['actual_java_method_body_javac_and_execution_cases']=24
report['compile_scope']='Three actual Java method bodies with modeled Android APIs; not complete Android module compilation'
(BASE/'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n')
