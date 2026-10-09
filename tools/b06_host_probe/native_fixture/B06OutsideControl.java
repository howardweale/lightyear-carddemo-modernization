package org.idempiere.test;
public final class B06OutsideControl {
 public static int target(int n) { return JourneySupport.target(n); }
 public static java.util.function.IntUnaryOperator factory() { return B06OutsideControl::target; }
}
