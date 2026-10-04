// Trusted host launcher/probe. No models, network capabilities or shell in child.
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

class B06BuilderContainer {
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct STARTUPINFO {
  public int cb; public string reserved, desktop, title; public int x,y,xs,ys,xc,yc,fill,flags;
  public short show,reserved2; public IntPtr reservedPtr,input,output,error;
 }
 [StructLayout(LayoutKind.Sequential)] struct STARTUPINFOEX { public STARTUPINFO StartupInfo; public IntPtr list; }
 [StructLayout(LayoutKind.Sequential)] struct PROCESS_INFORMATION {public IntPtr process,thread; public uint pid,tid;}
 [StructLayout(LayoutKind.Sequential)] struct SECURITY_CAPABILITIES {public IntPtr sid,capabilities;public uint count,reserved;}
 [DllImport("userenv.dll",CharSet=CharSet.Unicode)] static extern int CreateAppContainerProfile(string n,string d,string desc,IntPtr caps,uint count,out IntPtr sid);
 [DllImport("userenv.dll",CharSet=CharSet.Unicode)] static extern int DeriveAppContainerSidFromAppContainerName(string n,out IntPtr sid);
 [DllImport("advapi32.dll")] static extern IntPtr FreeSid(IntPtr sid);
 [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool ConvertSidToStringSid(IntPtr sid,out IntPtr str);
 [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr p);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,int flags,ref IntPtr size);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr attribute,IntPtr value,IntPtr size,IntPtr old,IntPtr returned);
 [DllImport("kernel32.dll")] static extern void DeleteProcThreadAttributeList(IntPtr list);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(string app,StringBuilder cmd,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr env,string cwd,ref STARTUPINFOEX si,out PROCESS_INFORMATION pi);
 [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr h,uint ms);
 [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr h,out uint code);
 [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr h,uint code);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr h,uint access,out IntPtr token);
 [DllImport("advapi32.dll",SetLastError=true)] static extern bool GetTokenInformation(IntPtr token,int kind,out int value,int len,out int returned);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr CreateFile(string p,uint access,uint share,IntPtr sa,uint disposition,uint flags,IntPtr template);
 static string Quote(string s) {if(s.Contains("\"") || s.EndsWith("\\")) throw new Exception("invalid argument");return "\""+s+"\"";}
 static IntPtr Profile(string name) {
  if(name!="Lightyear.B06.Builder.r3") throw new Exception("unexpected builder profile");
  IntPtr sid; int hr=CreateAppContainerProfile(name,name,"B06 no-capability builder identity",IntPtr.Zero,0,out sid);
  if(hr<0 && DeriveAppContainerSidFromAppContainerName(name,out sid)<0) throw new Exception("AppContainer profile unavailable");
  return sid;
 }
 static int Probe(string target,string allowed) {
  IntPtr token; if(!OpenProcessToken(GetCurrentProcess(),8,out token)) return 21;
  int value,len; bool ok=GetTokenInformation(token,29,out value,4,out len);CloseHandle(token);
  if(!ok || value!=1) return 22;
  var h=CreateFile(allowed,0x80000000,7,IntPtr.Zero,3,0,IntPtr.Zero);
  if(h==new IntPtr(-1)) return 23;CloseHandle(h);
  h=CreateFile(target,0x80000000,7,IntPtr.Zero,3,0,IntPtr.Zero);
  if(h!=new IntPtr(-1)) {CloseHandle(h);return 24;}
  return Marshal.GetLastWin32Error()==5 ? 0 : 25;
 }
 static int Main(string[] args) {
  try {
   if(args.Length==3 && args[0]=="--probe") return Probe(args[1],args[2]);
   if(args.Length!=2 && args.Length!=4) return 10;
   IntPtr sid=Profile(args[1]), str;
   try {
    if(!ConvertSidToStringSid(sid,out str)) throw new Win32Exception();
    string identity=Marshal.PtrToStringUni(str);LocalFree(str);
    if(args[0]=="--identity" && args.Length==2) {Console.WriteLine(identity);return 0;}
    if(args[0]!="--launch-probe" || args.Length!=4) return 11;
    string exe=System.Reflection.Assembly.GetExecutingAssembly().Location;
    IntPtr size=IntPtr.Zero;InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref size);
    IntPtr list=Marshal.AllocHGlobal(size), caps=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(SECURITY_CAPABILITIES)));
    bool initialized=false;
    try {
     if(!InitializeProcThreadAttributeList(list,1,0,ref size)) throw new Win32Exception();initialized=true;
     Marshal.StructureToPtr(new SECURITY_CAPABILITIES {sid=sid},caps,false);
     if(!UpdateProcThreadAttribute(list,0,new IntPtr(0x20009),caps,new IntPtr(Marshal.SizeOf(typeof(SECURITY_CAPABILITIES))),IntPtr.Zero,IntPtr.Zero)) throw new Win32Exception();
     STARTUPINFOEX si=new STARTUPINFOEX();si.StartupInfo.cb=Marshal.SizeOf(si);si.list=list;
     PROCESS_INFORMATION pi;
     var cmd=new StringBuilder(Quote(exe)+" --probe "+Quote(args[2])+" "+Quote(args[3]));
     if(!CreateProcess(exe,cmd,IntPtr.Zero,IntPtr.Zero,false,0x08080000,IntPtr.Zero,Environment.GetFolderPath(Environment.SpecialFolder.Windows),ref si,out pi)) throw new Win32Exception();
     uint code;
     try {if(WaitForSingleObject(pi.process,30000)!=0) {TerminateProcess(pi.process,26);WaitForSingleObject(pi.process,5000);code=26;}
          else if(!GetExitCodeProcess(pi.process,out code)) throw new Win32Exception();}
     finally {CloseHandle(pi.thread);CloseHandle(pi.process);}
     Console.WriteLine("{\"appcontainer_sid\":\""+identity+"\",\"child_exit_code\":"+code+",\"capabilities\":[],\"inherited_handles\":false}");
     return code==0 ? 0 : 1;
    } finally {if(initialized) DeleteProcThreadAttributeList(list);Marshal.FreeHGlobal(list);Marshal.FreeHGlobal(caps);}
   } finally {FreeSid(sid);}
  } catch(Exception e) {Console.Error.WriteLine(e.GetType().Name+": "+e.Message);return 99;}
 }
}
