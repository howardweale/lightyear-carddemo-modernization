import com.sun.jdi.*;
import com.sun.jdi.event.*;
import java.lang.reflect.*;
import java.util.*;
/** Executes the production atReturn guard with structural operands from the signed capture. */
public class CapturedReturnProbe {
 static Object proxy(Class<?> type,java.util.function.BiFunction<String,Object[],Object> f) {
  return Proxy.newProxyInstance(CapturedReturnProbe.class.getClassLoader(),new Class<?>[]{type},(o,m,a)->{
   if(m.getName().equals("equals"))return o==a[0];
   if(m.getName().equals("hashCode"))return System.identityHashCode(o);
   return f.apply(m.getName(),a);
  });
 }
 public static void main(String[] a)throws Exception {
  ReferenceType type=(ReferenceType)proxy(ReferenceType.class,(n,x)->n.equals("name")?a[0]:null);
  com.sun.jdi.Method method=(com.sun.jdi.Method)proxy(com.sun.jdi.Method.class,(n,x)->switch(n){
   case "declaringType"->type;case "name"->a[1];case "signature"->a[2];default->null;});
  Location loc=(Location)proxy(Location.class,(n,x)->switch(n){
   case "method"->method;case "declaringType"->type;case "codeIndex"->Long.parseLong(a[5]);default->null;});
  StackFrame frame=(StackFrame)proxy(StackFrame.class,(n,x)->loc);
  ThreadReference thread=(ThreadReference)proxy(ThreadReference.class,(n,x)->switch(n){
   case "uniqueID"->Long.parseLong(a[3]);case "frameCount"->Integer.parseInt(a[4]);case "frame"->frame;default->null;});
  BreakpointEvent event=(BreakpointEvent)proxy(BreakpointEvent.class,(n,x)->n.equals("thread")?thread:loc);
  VirtualMachine vm=(VirtualMachine)proxy(VirtualMachine.class,(n,x)->{throw new AssertionError("unmatched return must not arm a request");});
  Class<?> c=Class.forName("lightyear.observer.PostingObserver$Generation");
  var ctor=c.getDeclaredConstructor();ctor.setAccessible(true);Object generation=ctor.newInstance();
  var v=c.getDeclaredField("v2");v.setAccessible(true);v.set(generation,true);
  var pending=c.getDeclaredField("pending");pending.setAccessible(true);
  if(!((Map<?,?>)pending.get(generation)).isEmpty())throw new AssertionError("fixture requires empty pending");
  var call=c.getDeclaredMethod("atReturn",VirtualMachine.class,BreakpointEvent.class);call.setAccessible(true);
  try {call.invoke(generation,vm,event);throw new AssertionError("missing entry was accepted");}
  catch(InvocationTargetException failure) {
   if(!(failure.getCause() instanceof IllegalStateException))throw failure;
   System.out.println(failure.getCause().toString());
  }
 }
}
