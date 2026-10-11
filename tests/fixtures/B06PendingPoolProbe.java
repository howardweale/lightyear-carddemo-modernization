import java.util.*;
public class B06PendingPoolProbe {
  public static void main(String[] args)throws Exception {
    Class<?> cls=Class.forName("lightyear.observer.PostingObserver$PendingPool");
    var ctor=cls.getDeclaredConstructor();ctor.setAccessible(true);Object pool=ctor.newInstance();
    var retain=cls.getDeclaredMethod("retain",Map.class);retain.setAccessible(true);
    var release=cls.getDeclaredMethod("release",Map.class);release.setAccessible(true);
    List<Map<String,Object>> entries=new ArrayList<>();
    Map<String,Object> first=null,snapshot=null;
    for(int i=0;i<512;i++){
      Map<String,Object> input=Map.of("kind","generation","thread_id",7L,"generation_id",1000L+i,
        "entry_depth",103,"entry_method","selected.method()V","entry_event_index",4000L+i);
      @SuppressWarnings("unchecked") Map<String,Object> entry=(Map<String,Object>)retain.invoke(pool,input);
      if(!entry.equals(input))throw new AssertionError("exact fields changed");entries.add(entry);
      if(i==0){first=entry;snapshot=new LinkedHashMap<>(entry);}
    }
    Set<Object> identities=Collections.newSetFromMap(new IdentityHashMap<>());identities.addAll(entries);
    if(identities.size()!=512)throw new AssertionError("active slot reused");
    try{retain.invoke(pool,snapshot);throw new AssertionError("capacity bypass");}
    catch(java.lang.reflect.InvocationTargetException expected){if(!(expected.getCause() instanceof IllegalStateException))throw expected;}
    Class<?> snapshotClass=Class.forName("lightyear.observer.PostingObserver$PendingSnapshot");
    var sc=snapshotClass.getDeclaredConstructor();sc.setAccessible(true);Object witness=sc.newInstance();
    var capture=snapshotClass.getDeclaredMethod("capture",Collection.class);capture.setAccessible(true);capture.invoke(witness,entries);
    release.invoke(pool,first);
    try{release.invoke(pool,first);throw new AssertionError("double release");}
    catch(java.lang.reflect.InvocationTargetException expected){}
    Object reused=retain.invoke(pool,Map.of("kind","generation","thread_id",9L,"generation_id",9000L,
      "entry_depth",200,"entry_method","selected.other()V","entry_event_index",9999L));
    if(reused!=first || !snapshot.get("generation_id").equals(1000L))throw new AssertionError("snapshot or reuse changed");
    Map<?,?> before=(Map<?,?>)((List<?>)witness).get(0);
    if(!before.equals(Map.of("generation_id",1000L,"depth",103,"method","selected.method()V")))throw new AssertionError("pre-dispatch witness mutated");
    capture.invoke(witness,List.of());if(!((List<?>)witness).isEmpty())throw new AssertionError("witness stale");
    Object foreign=ctor.newInstance();
    try{release.invoke(foreign,reused);throw new AssertionError("foreign release");}
    catch(java.lang.reflect.InvocationTargetException expected){}
    for(String name:List.of("thread","generation","age","depth"))
      if(!reused.getClass().getDeclaredField(name).getType().isPrimitive())throw new AssertionError("retained boxed ID");
    System.out.println("fixed_slots=512; exact_fields=true; identity=true; snapshot=true; guards=true");
  }
}
