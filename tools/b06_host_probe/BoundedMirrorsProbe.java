import com.sun.jdi.*;
import com.sun.jdi.connect.*;
import com.sun.jdi.event.*;
import com.sun.jdi.request.*;
import java.lang.reflect.Field;
import java.util.*;
import lightyear.observer.BoundedJdiMirrors;

/** Real host JDI tests against the same pinned implementation as the adapter. */
public final class BoundedMirrorsProbe {
    static Field field(Object object,String name)throws Exception{
        Field f=object.getClass().getDeclaredField(name);f.setAccessible(true);return f;
    }
    @SuppressWarnings("unchecked") static Map<Long,ReferenceType> ids(VirtualMachine vm)throws Exception{
        return (Map<Long,ReferenceType>)field(vm,"typesByID").get(vm);
    }
    static void require(boolean value,String message){if(!value)throw new AssertionError(message);}
    public static void main(String[] args)throws Exception {
        VirtualMachine fake=(VirtualMachine)java.lang.reflect.Proxy.newProxyInstance(
            BoundedMirrorsProbe.class.getClassLoader(),new Class<?>[]{VirtualMachine.class},(o,m,a)->null);
        try{new BoundedJdiMirrors(fake);throw new AssertionError("unknown implementation accepted");}
        catch(IllegalStateException expected){require(expected.getMessage().equals("unsupported-jdi-mirror-implementation"),expected.toString());}
        var pin=BoundedJdiMirrors.class.getDeclaredMethod("verifyClass",Class.class,String.class,String.class);pin.setAccessible(true);
        try{pin.invoke(null,Class.forName("com.sun.tools.jdi.VirtualMachineImpl"),"/com/sun/tools/jdi/VirtualMachineImpl.class","0".repeat(64));throw new AssertionError("wrong bytecode accepted");}
        catch(java.lang.reflect.InvocationTargetException expected){require(expected.getCause().getMessage().startsWith("unsupported-jdi-mirror-bytecode:"),expected.toString());}
        LaunchingConnector connector=Bootstrap.virtualMachineManager().defaultConnector();
        var options=connector.defaultArguments();options.get("main").setValue("BoundedMirrorsTarget");
        options.get("options").setValue("-Xmx96m -cp \""+args[0]+"\"");
        VirtualMachine vm=connector.launch(options);
        try {
            if(args.length>1 && args[1].equals("no-opens")){
                try {new BoundedJdiMirrors(vm);throw new AssertionError("missing opens accepted");}
                catch(IllegalStateException expected){require(expected.getMessage().equals("jdi-mirror-adapter-opens-required"),expected.toString());}
                System.out.println("missing-opens-refused");return;
            }
            BoundedJdiMirrors cache=new BoundedJdiMirrors(vm);
            ClassPrepareRequest prepared=vm.eventRequestManager().createClassPrepareRequest();
            prepared.addClassFilter("BoundedMirrorsTarget*");prepared.setSuspendPolicy(EventRequest.SUSPEND_ALL);prepared.enable();
            ClassUnloadRequest unloaded=vm.eventRequestManager().createClassUnloadRequest();
            unloaded.addClassFilter("BoundedMirrorsTarget$Payload");unloaded.enable();
            List<ReferenceType> old=new ArrayList<>();int checkpoints=0,unloads=0;
            Set<Long> oldIds=new HashSet<>();
            while(true){
                EventSet events=vm.eventQueue().remove(30000);require(events!=null,"event timeout");
                boolean ending=false;
                for(Event event:events){
                    if(event instanceof ClassPrepareEvent cp){
                        ReferenceType type=cp.referenceType();
                        if(type.name().equals("BoundedMirrorsTarget")){
                            cache.pin(type);
                            BreakpointRequest b=vm.eventRequestManager().createBreakpointRequest(type.methodsByName("checkpoint").get(0).location());
                            b.setSuspendPolicy(EventRequest.SUSPEND_ALL);b.enable();
                        }else if(type.name().equals("BoundedMirrorsTarget$Payload"))old.add(type);
                    }else if(event instanceof ClassUnloadEvent){unloads++;}
                    else if(event instanceof BreakpointEvent){
                        checkpoints++;
                        if(checkpoints==1){
                            cache.prune(List.of());
                            ReferenceType target=vm.classesByName("BoundedMirrorsTarget").get(0);
                            ArrayReference objects=(ArrayReference)target.getValue(target.fieldByName("CLASSES"));
                            int unknownCount=0;
                            Field status=Class.forName("com.sun.tools.jdi.ReferenceTypeImpl").getDeclaredField("status");status.setAccessible(true);
                            for(int repeat=0;repeat<2;repeat++){
                                for(Value object:objects.getValues()){
                                    ReferenceType mirror=((ClassObjectReference)object).reflectedType();
                                    if(status.getInt(mirror)==0)unknownCount++;
                                }
                                cache.prune(List.of());
                            }
                            require(unknownCount>0,"fixture did not recreate unknown-status mirrors");
                            require(((Number)cache.telemetry().get("jdi_mirror_status_queries")).longValue()>0,"unknown statuses not resolved");
                            require(ids(vm).size()<=BoundedJdiMirrors.HIGH_WATER,"unknown mirrors caused false pins");
                            require(old.size()==1300,"concurrent prepare events missing: "+old.size());
                            require(((Number)cache.telemetry().get("jdi_mirror_evictions")).longValue()>0,"no eviction");
                            ReferenceType evicted=old.stream().filter(t->{try{return !ids(vm).containsValue(t);}catch(Exception e){throw new RuntimeException(e);}}).findFirst().orElseThrow();
                            com.sun.jdi.Method previous=evicted.methodsByName("value").get(0);
                            List<ReferenceType> found=vm.classesByName("BoundedMirrorsTarget$Payload");
                            require(found.size()==1300,"exact-name query lost dual-loader classes");
                            ReferenceType revisited=found.stream().filter(evicted::equals).findFirst().orElseThrow();
                            require(revisited!=evicted,"mirror was not recreated");
                            require(previous.equals(revisited.methodsByName("value").get(0)),"method identity changed");
                            require(previous.location().equals(revisited.methodsByName("value").get(0).location()),"location identity changed");
                            int countBeforePinRefusal=ids(vm).size();
                            try{cache.prune(found);throw new AssertionError("over-cap active pins accepted");}
                            catch(IllegalStateException expected){require(expected.getMessage().equals("jdi-mirror-pins-limit"),expected.toString());}
                            require(ids(vm).size()==countBeforePinRefusal,"pin refusal mutated cache");
                            @SuppressWarnings("unchecked") Set<ReferenceType> signatures=(Set<ReferenceType>)field(vm,"typesBySignature").get(vm);
                            synchronized(vm){
                                signatures.remove(revisited);
                                try{cache.prune(List.of());throw new AssertionError("inconsistent caches accepted");}
                                catch(IllegalStateException expected){require(expected.getMessage().equals("jdi-mirror-cache-inconsistent"),expected.toString());}
                                require(ids(vm).size()==countBeforePinRefusal,"inconsistency refusal mutated cache");
                                signatures.add(revisited);
                            }
                            cache.prune(List.of(revisited));
                            require(ids(vm).containsValue(revisited),"active mirror evicted");
                            require(ids(vm).size()<=BoundedJdiMirrors.HIGH_WATER,"cache not bounded");
                            // Force a conservative unprepared mirror, the state an
                            // internal prepare event can transiently expose.
                            Field state=Class.forName("com.sun.tools.jdi.ReferenceTypeImpl").getDeclaredField("isPrepared");state.setAccessible(true);
                            state.setBoolean(revisited,false);vm.classesByName("BoundedMirrorsTarget$Payload");
                            // The exact query refreshed the old mirror; restore false.
                            state.setBoolean(revisited,false);cache.prune(List.of());
                            require(ids(vm).containsValue(revisited),"unprepared mirror evicted");state.setBoolean(revisited,true);
                            for(var entry:ids(vm).entrySet())if(entry.getValue().name().equals("BoundedMirrorsTarget$Payload"))oldIds.add(entry.getKey());
                            old.clear();
                        }else{
                            List<ReferenceType> reloaded=vm.classesByName("BoundedMirrorsTarget$Payload");
                            require(!reloaded.isEmpty(),"reload missing");
                            require(unloads>0,"no unload observed");
                            require(ids(vm).entrySet().stream().anyMatch(e->e.getValue().name().equals("BoundedMirrorsTarget$Payload")&&!oldIds.contains(e.getKey())),"reload identity reused");
                            // A caller must never be able to silently use a partial
                            // complete-type cache. Refuse before making any edits.
                            vm.allClasses();int before=ids(vm).size();
                            try{cache.prune(List.of());throw new AssertionError("full enumeration accepted");}
                            catch(IllegalStateException expected){require(expected.getMessage().equals("jdi-full-enumeration-prohibited"),expected.toString());}
                            require(ids(vm).size()==before,"refusal mutated cache");
                            System.out.println("host-mirror-lifecycle-passed "+cache.telemetry());ending=true;
                        }
                    }else if(event instanceof VMDeathEvent || event instanceof VMDisconnectEvent){ending=true;}
                }
                if(ending){require(checkpoints==2,"target ended early");break;}
                cache.prune(List.of());events.resume();
            }
        }finally{try{vm.exit(0);}catch(VMDisconnectedException ignored){} }
    }
}
