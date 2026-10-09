package org.idempiere.test;
import java.lang.invoke.*;
public final class LightyearOperationsTest {
 public static volatile int sink;
 public static int target(int n) { return JourneySupport.target(n); }
 public static void main(String[] args) throws Throwable {
  java.util.function.IntUnaryOperator lambda=n -> target(n);
  sink=lambda.applyAsInt(1); sink=JourneySupport.factory().applyAsInt(2);
  sink=B06OutsideControl.factory().applyAsInt(3);
  MethodHandle handle=MethodHandles.lookup().findStatic(LightyearOperationsTest.class,"target",MethodType.methodType(int.class,int.class));
  sink=(int)handle.invokeExact(4); sink=(Integer)handle.invokeWithArguments(5);
 }
}
