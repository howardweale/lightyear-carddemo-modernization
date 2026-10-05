// Account-scoped WFP policy. No firewall profile or other user's rules change.
// SDK definitions: microsoft/win32metadata, fwpmu.h and fwpmtypes.h.
using System;
using System.Runtime.InteropServices;
using System.ComponentModel;
using System.Security.AccessControl;

public sealed class B06AccountEgress : IDisposable {
    [StructLayout(LayoutKind.Sequential)] struct Display { [MarshalAs(UnmanagedType.LPWStr)] public string name; [MarshalAs(UnmanagedType.LPWStr)] public string description; }
    [StructLayout(LayoutKind.Sequential)] struct Blob { public uint size; public IntPtr data; }
    [StructLayout(LayoutKind.Explicit, Size=16)] struct Value { [FieldOffset(0)] public uint type; [FieldOffset(8)] public IntPtr pointer; [FieldOffset(8)] public byte number; }
    [StructLayout(LayoutKind.Sequential)] struct Condition { public Guid key; public uint match; public Value value; }
    [StructLayout(LayoutKind.Sequential)] struct Action { public uint type; public Guid key; }
    [StructLayout(LayoutKind.Explicit,Size=16)] struct Context { [FieldOffset(0)] public ulong raw; [FieldOffset(0)] public Guid key; }
    [StructLayout(LayoutKind.Sequential)] struct Filter {
        public Guid key; public Display display; public uint flags; public IntPtr provider;
        public Blob data; public Guid layer; public Guid sublayer; public Value weight;
        public uint count; public IntPtr conditions; public Action action; public Context context;
        public IntPtr reserved; public ulong id; public Value effectiveWeight;
    }
    [StructLayout(LayoutKind.Sequential)] struct Sublayer { public Guid key; public Display display; public uint flags; public IntPtr provider; public Blob data; public ushort weight; }
    [DllImport("fwpuclnt.dll", CharSet=CharSet.Unicode)] static extern uint FwpmEngineOpen0(string server,uint auth,IntPtr identity,IntPtr session,out IntPtr engine);
    [DllImport("fwpuclnt.dll")] static extern uint FwpmEngineClose0(IntPtr engine);
    [DllImport("fwpuclnt.dll")] static extern uint FwpmTransactionBegin0(IntPtr engine,uint flags);
    [DllImport("fwpuclnt.dll")] static extern uint FwpmTransactionCommit0(IntPtr engine);
    [DllImport("fwpuclnt.dll")] static extern uint FwpmTransactionAbort0(IntPtr engine);
    [DllImport("fwpuclnt.dll")] static extern uint FwpmSubLayerAdd0(IntPtr engine,ref Sublayer layer,IntPtr sd);
    [DllImport("fwpuclnt.dll")] static extern uint FwpmSubLayerDeleteByKey0(IntPtr engine,ref Guid key);
    [DllImport("fwpuclnt.dll")] static extern uint FwpmSubLayerGetByKey0(IntPtr engine,ref Guid key,out IntPtr layer);
    [DllImport("fwpuclnt.dll")] static extern uint FwpmFilterAdd0(IntPtr engine,ref Filter filter,IntPtr sd,out ulong id);
    [DllImport("fwpuclnt.dll")] static extern uint FwpmFilterDeleteByKey0(IntPtr engine,ref Guid key);
    [DllImport("fwpuclnt.dll")] static extern uint FwpmFilterGetByKey0(IntPtr engine,ref Guid key,out IntPtr filter);
    [DllImport("fwpuclnt.dll",CharSet=CharSet.Unicode)] static extern uint FwpmGetAppIdFromFileName0(string path,out IntPtr id);
    [DllImport("fwpuclnt.dll")] static extern void FwpmFreeMemory0(ref IntPtr memory);
    readonly Guid sublayer; readonly Guid[] keys; IntPtr engine; bool installed;
    readonly byte[] expectedUser, expectedApp;
    static byte[] Bytes(IntPtr pointer) {
        Blob b=(Blob)Marshal.PtrToStructure(pointer,typeof(Blob));
        if(b.size>65536 || b.data==IntPtr.Zero)throw new InvalidOperationException("Invalid WFP blob");
        byte[] result=new byte[b.size];Marshal.Copy(b.data,result,0,result.Length);return result;
    }
    static bool Equal(byte[] a,byte[] b) {
        if(a.Length!=b.Length)return false;
        for(int i=0;i<a.Length;i++)if(a[i]!=b[i])return false;
        return true;
    }
    static readonly Guid User = new Guid("af043a0a-b34d-4f86-979c-c90371af6e66");
    static readonly Guid App = new Guid("d78e1e87-8644-4ea5-9437-d809ecefc971");
    static readonly Guid[] Layers={new Guid("c38d57d1-05a7-4c33-904f-7fbceee60e82"),new Guid("4a72393b-319f-44bc-84c3-ba54dcb3b6b4")};
    public string[] FilterKeys { get {return new[]{keys[0].ToString(),keys[1].ToString()};} }
    public string SublayerKey {get {return sublayer.ToString();}}
    static void Check(uint code) {if(code!=0)throw new Win32Exception(unchecked((int)code));}
    public static int[] LayoutSizes() {return new[]{Marshal.SizeOf(typeof(Value)),Marshal.SizeOf(typeof(Condition)),Marshal.SizeOf(typeof(Filter)),Marshal.SizeOf(typeof(Sublayer))};}
    public static bool Absent(string sublayerKey,string v4Key,string v6Key) {
        IntPtr handle;Check(FwpmEngineOpen0(null,10,IntPtr.Zero,IntPtr.Zero,out handle));
        try {
            foreach(string value in new[]{v4Key,v6Key}) {
                Guid key=new Guid(value);IntPtr p;uint code=FwpmFilterGetByKey0(handle,ref key,out p);
                if(code==0){FwpmFreeMemory0(ref p);return false;}
                if(code!=0x80320003)Check(code); // FWP_E_FILTER_NOT_FOUND
            }
            Guid layer=new Guid(sublayerKey);IntPtr q;uint result=FwpmSubLayerGetByKey0(handle,ref layer,out q);
            if(result==0){FwpmFreeMemory0(ref q);return false;}
            if(result!=0x80320007)Check(result); // FWP_E_SUBLAYER_NOT_FOUND
            return true;
        } finally {FwpmEngineClose0(handle);}
    }
    public B06AccountEgress(string sid,string path,string sublayerKey,string v4Key,string v6Key) {
        if(IntPtr.Size!=8)throw new InvalidOperationException("x64 host required");
        if(!sid.StartsWith("S-1-5-21-") || !System.IO.File.Exists(path))throw new ArgumentException("Account and installed binary required");
        sublayer=new Guid(sublayerKey);keys=new[]{new Guid(v4Key),new Guid(v6Key)};
        Check(FwpmEngineOpen0(null,10,IntPtr.Zero,IntPtr.Zero,out engine));
        IntPtr app=IntPtr.Zero,sd=IntPtr.Zero,blob=IntPtr.Zero,conditions=IntPtr.Zero;
        bool transaction=false;
        try {
            // Persistent filters survive a launcher crash. Operator recovery must
            // disable the account before deleting only these recorded filter GUIDs.
            Check(FwpmTransactionBegin0(engine,0));transaction=true;
            Sublayer layer=new Sublayer {key=sublayer,flags=1,weight=65000,display=new Display{name="Lightyear B06 dedicated account egress"}};
            Check(FwpmSubLayerAdd0(engine,ref layer,IntPtr.Zero));
            Check(FwpmGetAppIdFromFileName0(path,out app));
            RawSecurityDescriptor descriptor=new RawSecurityDescriptor("D:(A;;CC;;;"+sid+")");
            byte[] raw=new byte[descriptor.BinaryLength];descriptor.GetBinaryForm(raw,0);
            expectedUser=raw;expectedApp=Bytes(app);
            sd=Marshal.AllocHGlobal(raw.Length);Marshal.Copy(raw,0,sd,raw.Length);
            blob=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(Blob)));
            Marshal.StructureToPtr(new Blob{size=(uint)raw.Length,data=sd},blob,false);
            Condition[] values={new Condition{key=User,match=0,value=new Value{type=14,pointer=blob}},
                                new Condition{key=App,match=10,value=new Value{type=12,pointer=app}}};
            int size=Marshal.SizeOf(typeof(Condition));conditions=Marshal.AllocHGlobal(size*2);
            for(int i=0;i<2;i++)Marshal.StructureToPtr(values[i],IntPtr.Add(conditions,size*i),false);
            for(int i=0;i<2;i++) {
                Filter filter=new Filter{key=keys[i],flags=1,display=new Display{name="B06 block dedicated account except pinned Codex"},
                    layer=Layers[i],sublayer=sublayer,weight=new Value{type=1,number=15},count=2,conditions=conditions,
                    action=new Action{type=0x1001}};
                ulong id;Check(FwpmFilterAdd0(engine,ref filter,IntPtr.Zero,out id));
            }
            Check(FwpmTransactionCommit0(engine));transaction=false;installed=true;
        } catch {if(transaction)FwpmTransactionAbort0(engine);FwpmEngineClose0(engine);engine=IntPtr.Zero;throw;}
        finally {if(app!=IntPtr.Zero)FwpmFreeMemory0(ref app);foreach(IntPtr p in new[]{sd,blob,conditions})if(p!=IntPtr.Zero)Marshal.FreeHGlobal(p);}
    }
    public bool Verify() {
        if(!installed)return false;
        for(int i=0;i<2;i++) {
            IntPtr p;Guid key=keys[i];Check(FwpmFilterGetByKey0(engine,ref key,out p));
            try {
                Filter f=(Filter)Marshal.PtrToStructure(p,typeof(Filter));
                if(f.layer!=Layers[i] || f.sublayer!=sublayer || f.action.type!=0x1001 || f.count!=2 || f.flags!=1)return false;
                Condition u=(Condition)Marshal.PtrToStructure(f.conditions,typeof(Condition));
                Condition a=(Condition)Marshal.PtrToStructure(IntPtr.Add(f.conditions,Marshal.SizeOf(typeof(Condition))),typeof(Condition));
                if(u.key!=User || u.match!=0 || u.value.type!=14 || a.key!=App || a.match!=10 || a.value.type!=12)return false;
                if(!Equal(Bytes(u.value.pointer),expectedUser) || !Equal(Bytes(a.value.pointer),expectedApp))return false;
            } finally {FwpmFreeMemory0(ref p);}
        }
        return true;
    }
    // Caller must first disable lyb06builder and terminate its owned process tree.
    public void Remove() {
        if(!installed)return;
        Check(FwpmTransactionBegin0(engine,0));
        try {for(int i=0;i<2;i++){Guid key=keys[i];Check(FwpmFilterDeleteByKey0(engine,ref key));}
            Guid s=sublayer;Check(FwpmSubLayerDeleteByKey0(engine,ref s));Check(FwpmTransactionCommit0(engine));installed=false;}
        catch {FwpmTransactionAbort0(engine);throw;}
        if(!Absent(sublayer.ToString(),keys[0].ToString(),keys[1].ToString()))throw new InvalidOperationException("Owned filters remain");
    }
    public void Dispose(){if(engine!=IntPtr.Zero){FwpmEngineClose0(engine);engine=IntPtr.Zero;}}
}
