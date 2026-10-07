# r10 observed class/method catalogue

Every saved stack frame and catch location, grouped by lane. Native names are retained.
BOUND-MATCH means constant-pool and method byte hashes match a frozen class file.
UNBOUND means absent from that catalogue, including frames r10 did not require checking.
Categories inferred from names are inventory labels, not trusted runtime provenance.
Generated names are not attributed to a host merely by stripping a suffix.

## oracle

### JDK

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `java.lang.Class` | `getDeclaredMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;` | UNBOUND | not required | 4 / 0 |
| `java.lang.invoke.DirectMethodHandle$Holder` | `invokeStatic(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `java.lang.invoke.DirectMethodHandle$Holder` | `newInvokeSpecial(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 72 / 0 |
| `java.lang.invoke.Invokers$Holder` | `invokeExact_MT(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 348 / 0 |
| `java.lang.invoke.Invokers$Holder` | `invokeExact_MT(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `java.lang.reflect.Constructor` | `newInstance([Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 105 / 0 |
| `java.lang.reflect.Constructor` | `newInstanceWithCaller([Ljava/lang/Object;ZLjava/lang/Class;)Ljava/lang/Object;` | UNBOUND | not required | 105 / 0 |
| `java.lang.reflect.Method` | `invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 1046 / 0 |
| `java.security.AccessController` | `doPrivileged(Ljava/security/PrivilegedAction;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `java.security.AccessController` | `executePrivileged(Ljava/security/PrivilegedAction;Ljava/security/AccessControlContext;Ljava/lang/Class;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `java.text.DateFormat` | `parse(Ljava/lang/String;)Ljava/util/Date;` | UNBOUND | not required | 8 / 0 |
| `java.util.ArrayList` | `forEach(Ljava/util/function/Consumer;)V` | UNBOUND | not required | 699 / 0 |
| `jdk.internal.reflect.DirectConstructorHandleAccessor` | `invokeImpl([Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 105 / 0 |
| `jdk.internal.reflect.DirectConstructorHandleAccessor` | `newInstance([Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 105 / 0 |
| `jdk.internal.reflect.DirectMethodHandleAccessor` | `invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 1046 / 0 |
| `jdk.internal.reflect.DirectMethodHandleAccessor` | `invokeImpl(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 1046 / 0 |

### OSGi/Tycho/JUnit framework

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `org.apache.maven.surefire.api.util.ReflectionUtils` | `invokeMethodWithArray2(Ljava/lang/Object;Ljava/lang/reflect/Method;[Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `org.apache.maven.surefire.booter.ProviderFactory` | `invokeProvider(Ljava/lang/Object;Ljava/lang/ClassLoader;Ljava/lang/Object;Lorg/apache/maven/surefire/booter/ProviderConfiguration;ZLorg/apache/maven/surefire/booter/StartupConfiguration;Z)Lorg/apache/maven/surefire/api/suite/RunResult;` | UNBOUND | not required | 349 / 0 |
| `org.apache.maven.surefire.booter.ProviderFactory$ProviderProxy` | `invoke(Ljava/lang/Object;)Lorg/apache/maven/surefire/api/suite/RunResult;` | UNBOUND | not required | 349 / 0 |
| `org.apache.maven.surefire.junitplatform.JUnitPlatformProvider` | `execute(Lorg/apache/maven/surefire/api/util/TestsToRun;Lorg/apache/maven/surefire/junitplatform/RunListenerAdapter;)V` | UNBOUND | not required | 349 / 0 |
| `org.apache.maven.surefire.junitplatform.JUnitPlatformProvider` | `invoke(Ljava/lang/Object;)Lorg/apache/maven/surefire/api/suite/RunResult;` | UNBOUND | not required | 349 / 0 |
| `org.apache.maven.surefire.junitplatform.JUnitPlatformProvider` | `invokeAllTests(Lorg/apache/maven/surefire/api/util/TestsToRun;Lorg/apache/maven/surefire/junitplatform/RunListenerAdapter;)V` | UNBOUND | not required | 349 / 0 |
| `org.apache.maven.surefire.junitplatform.LazyLauncher` | `execute(Lorg/junit/platform/launcher/LauncherDiscoveryRequest;[Lorg/junit/platform/launcher/TestExecutionListener;)V` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.core.runtime.adaptor.EclipseStarter` | `run(Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.core.runtime.adaptor.EclipseStarter` | `run([Ljava/lang/String;Ljava/lang/Runnable;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.core.runtime.internal.adaptor.EclipseAppLauncher` | `runApplication(Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.core.runtime.internal.adaptor.EclipseAppLauncher` | `start(Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.equinox.internal.app.EclipseAppHandle` | `run(Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.equinox.launcher.Main` | `basicRun([Ljava/lang/String;)V` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.equinox.launcher.Main` | `invokeFramework([Ljava/lang/String;[Ljava/net/URL;)V` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.equinox.launcher.Main` | `main([Ljava/lang/String;)V` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.equinox.launcher.Main` | `run([Ljava/lang/String;)I` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.osgi.internal.framework.BundleContextImpl` | `getService(Lorg/osgi/framework/ServiceReference;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceConsumer$2` | `getService(Lorg/eclipse/osgi/internal/serviceregistry/ServiceUse;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceFactoryUse` | `factoryGetService()Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceFactoryUse` | `getService()Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceFactoryUse$1` | `run()Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceRegistrationImpl` | `getService(Lorg/eclipse/osgi/internal/framework/BundleContextImpl;Lorg/eclipse/osgi/internal/serviceregistry/ServiceConsumer;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceRegistry` | `getService(Lorg/eclipse/osgi/internal/framework/BundleContextImpl;Lorg/eclipse/osgi/internal/serviceregistry/ServiceReferenceImpl;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.tycho.surefire.osgibooter.HeadlessTestApplication` | `start(Lorg/eclipse/equinox/app/IApplicationContext;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `org.eclipse.tycho.surefire.osgibooter.OsgiSurefireBooter` | `run([Ljava/lang/String;Ljava/util/Properties;)I` | UNBOUND | not required | 349 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor` | `execute(Lorg/junit/jupiter/engine/execution/JupiterEngineExecutionContext;Lorg/junit/platform/engine/support/hierarchical/Node$DynamicTestExecutor;)Lorg/junit/jupiter/engine/execution/JupiterEngineExecutionContext;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor` | `execute(Lorg/junit/platform/engine/support/hierarchical/EngineExecutionContext;Lorg/junit/platform/engine/support/hierarchical/Node$DynamicTestExecutor;)Lorg/junit/platform/engine/support/hierarchical/EngineExecutionContext;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor` | `invokeTestMethod(Lorg/junit/jupiter/engine/execution/JupiterEngineExecutionContext;Lorg/junit/platform/engine/support/hierarchical/Node$DynamicTestExecutor;)V` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor` | `lambda$invokeTestMethod$7(Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/engine/execution/JupiterEngineExecutionContext;)V` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker` | `invoke(Ljava/lang/reflect/Method;Ljava/lang/Object;Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/engine/extension/ExtensionRegistry;Lorg/junit/jupiter/engine/execution/InterceptingExecutableInvoker$ReflectiveInterceptorCall;)Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker` | `invoke(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/engine/extension/ExtensionRegistry;Lorg/junit/jupiter/engine/execution/InterceptingExecutableInvoker$ReflectiveInterceptorCall;)Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker` | `lambda$invoke$0(Lorg/junit/jupiter/engine/execution/InterceptingExecutableInvoker$ReflectiveInterceptorCall;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/api/extension/InvocationInterceptor;Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;)Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker$ReflectiveInterceptorCall` | `lambda$ofVoidMethod$0(Lorg/junit/jupiter/engine/execution/InterceptingExecutableInvoker$ReflectiveInterceptorCall$VoidMethodInterceptorCall;Lorg/junit/jupiter/api/extension/InvocationInterceptor;Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;)Ljava/lang/Void;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InvocationInterceptorChain` | `chainAndInvoke(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/engine/execution/InvocationInterceptorChain$InterceptorCall;Ljava/util/List;)Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InvocationInterceptorChain` | `invoke(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/engine/extension/ExtensionRegistry;Lorg/junit/jupiter/engine/execution/InvocationInterceptorChain$InterceptorCall;)Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InvocationInterceptorChain` | `proceed(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;)Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InvocationInterceptorChain$InterceptedInvocation` | `proceed()Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InvocationInterceptorChain$ValidatingInvocation` | `proceed()Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.MethodInvocation` | `proceed()Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.extension.TimeoutExtension` | `intercept(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/engine/extension/TimeoutDuration;Lorg/junit/jupiter/engine/extension/TimeoutExtension$TimeoutProvider;)Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.extension.TimeoutExtension` | `interceptTestMethod(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;)V` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.jupiter.engine.extension.TimeoutExtension` | `interceptTestableMethod(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/engine/extension/TimeoutExtension$TimeoutProvider;)Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.platform.commons.util.ReflectionUtils` | `invokeMethod(Ljava/lang/reflect/Method;Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;` | BOUND-MATCH | required | 348 / 0 |
| `org.junit.platform.engine.support.hierarchical.HierarchicalTestEngine` | `execute(Lorg/junit/platform/engine/ExecutionRequest;)V` | BOUND-BUT-MISMATCH | required | 349 / 0 |
| `org.junit.platform.engine.support.hierarchical.HierarchicalTestExecutor` | `execute()Ljava/util/concurrent/Future;` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.engine.support.hierarchical.Node` | `around(Lorg/junit/platform/engine/support/hierarchical/EngineExecutionContext;Lorg/junit/platform/engine/support/hierarchical/Node$Invocation;)V` | BOUND-MATCH | required | 1046 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `execute()V` | BOUND-MATCH | required | 1047 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `executeRecursively()V` | BOUND-MATCH | required | 1046 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `lambda$executeRecursively$6()V` | BOUND-MATCH | required | 1046 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `lambda$executeRecursively$8(Lorg/junit/platform/engine/support/hierarchical/EngineExecutionContext;)V` | BOUND-MATCH | required | 1046 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `lambda$executeRecursively$9()V` | BOUND-MATCH | required | 1046 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `reportCompletion()V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.engine.support.hierarchical.SameThreadHierarchicalTestExecutorService` | `invokeAll(Ljava/util/List;)V` | BOUND-MATCH | required | 698 / 0 |
| `org.junit.platform.engine.support.hierarchical.SameThreadHierarchicalTestExecutorService` | `submit(Lorg/junit/platform/engine/support/hierarchical/HierarchicalTestExecutorService$TestTask;)Ljava/util/concurrent/Future;` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.engine.support.hierarchical.ThrowableCollector` | `execute(Lorg/junit/platform/engine/support/hierarchical/ThrowableCollector$Executable;)V` | BOUND-MATCH | required | 2440 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener` | `executionFinished(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener` | `lambda$executionFinished$6(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;Lorg/junit/platform/engine/EngineExecutionListener;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener` | `lambda$notifyEach$11(Ljava/util/function/Consumer;Ljava/util/function/Supplier;Lorg/junit/platform/engine/EngineExecutionListener;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener` | `notifyEach(Ljava/util/List;Ljava/util/function/Consumer;Ljava/util/function/Supplier;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.DefaultLauncher` | `execute(Lorg/junit/platform/launcher/LauncherDiscoveryRequest;[Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.launcher.core.DefaultLauncher` | `execute(Lorg/junit/platform/launcher/core/InternalTestPlan;[Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.launcher.core.DefaultLauncherSession$DelegatingLauncher` | `execute(Lorg/junit/platform/launcher/LauncherDiscoveryRequest;[Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.launcher.core.DelegatingEngineExecutionListener` | `executionFinished(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `execute(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/EngineExecutionListener;Lorg/junit/platform/engine/ConfigurationParameters;Lorg/junit/platform/engine/TestEngine;)V` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `execute(Lorg/junit/platform/launcher/core/InternalTestPlan;Lorg/junit/platform/engine/EngineExecutionListener;Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `execute(Lorg/junit/platform/launcher/core/InternalTestPlan;[Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `execute(Lorg/junit/platform/launcher/core/LauncherDiscoveryResult;Lorg/junit/platform/engine/EngineExecutionListener;)V` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `lambda$execute$0(Lorg/junit/platform/launcher/core/InternalTestPlan;Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `withInterceptedStreams(Lorg/junit/platform/engine/ConfigurationParameters;Lorg/junit/platform/launcher/core/ListenerRegistry;Ljava/util/function/Consumer;)V` | BOUND-MATCH | required | 349 / 0 |
| `org.junit.platform.launcher.core.ExecutionListenerAdapter` | `executionFinished(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.OutcomeDelayingEngineExecutionListener` | `executionFinished(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.osgi.util.tracker.AbstractTracked` | `trackAdding(Ljava/lang/Object;Ljava/lang/Object;)V` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.AbstractTracked` | `trackInitial()V` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.ServiceTracker` | `addingService(Lorg/osgi/framework/ServiceReference;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.ServiceTracker` | `open()V` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.ServiceTracker` | `open(Z)V` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.ServiceTracker$Tracked` | `customizerAdding(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.ServiceTracker$Tracked` | `customizerAdding(Lorg/osgi/framework/ServiceReference;Lorg/osgi/framework/ServiceEvent;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |

### candidate

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `org.idempiere.test.LightyearOperationsTest` | `action(Lorg/compiere/model/PO;Ljava/lang/String;)V` | BOUND-MATCH | required | 256 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `complete(Ljava/lang/String;Lorg/compiere/model/PO;)V` | BOUND-MATCH | required | 165 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `lambda$1(Ljava/util/Properties;Lorg/compiere/model/MBPartner;Ljava/lang/String;)Ljava/lang/Object;` | BOUND-MATCH | required | 1 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `operationsJourney()V` | BOUND-MATCH | required | 348 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `post(Lorg/compiere/model/PO;[Lorg/compiere/model/MAcctSchema;)V` | BOUND-MATCH | required | 25 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `postAllocations(Ljava/util/Properties;ILjava/lang/String;[Lorg/compiere/model/MAcctSchema;)V` | BOUND-MATCH | required | 6 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `recovery(Ljava/util/Properties;Lorg/compiere/model/MBPartner;)V` | BOUND-MATCH | required | 3 / 1 |

### generated/hidden

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `java.lang.invoke.LambdaForm$DMH/0x000076e130000c00` | `invokeVirtual(Ljava/lang/Object;Ljava/lang/Object;)V` | UNBOUND | not required | 348 / 0 |
| `java.lang.invoke.LambdaForm$DMH/0x000076e1301b8800` | `invokeVirtual(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `java.lang.invoke.LambdaForm$DMH/0x000076e130b20000` | `newInvokeSpecial(Ljava/lang/Object;Ljava/lang/Object;ILjava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 33 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x000076e130001400` | `invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x000076e130006800` | `invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 349 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x000076e130006c00` | `invokeExact_MT(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 454 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x000076e1300bc800` | `invoke(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 348 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x000076e1305bd800` | `invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 36 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x000076e130b20c00` | `invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 33 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x000076e130b34c00` | `invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 36 / 0 |
| `org.idempiere.test.LightyearOperationsTest$$Lambda/0x000076e130b23838` | `run(Ljava/lang/String;)Ljava/lang/Object;` | UNBOUND | required | 1 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor$$Lambda/0x000076e1305faa00` | `apply(Lorg/junit/jupiter/api/extension/InvocationInterceptor;Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;)V` | UNBOUND | required | 348 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor$$Lambda/0x000076e130aa2000` | `execute()V` | UNBOUND | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker$$Lambda/0x000076e13062afd0` | `apply(Lorg/junit/jupiter/api/extension/InvocationInterceptor;Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;)Ljava/lang/Object;` | UNBOUND | required | 348 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker$ReflectiveInterceptorCall$$Lambda/0x000076e1305fae20` | `apply(Lorg/junit/jupiter/api/extension/InvocationInterceptor;Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;)Ljava/lang/Object;` | UNBOUND | required | 348 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask$$Lambda/0x000076e130619630` | `execute()V` | UNBOUND | required | 1046 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask$$Lambda/0x000076e130619a58` | `invoke(Lorg/junit/platform/engine/support/hierarchical/EngineExecutionContext;)V` | UNBOUND | required | 1046 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask$$Lambda/0x000076e130619c80` | `execute()V` | UNBOUND | required | 1046 / 0 |
| `org.junit.platform.engine.support.hierarchical.SameThreadHierarchicalTestExecutorService$$Lambda/0x000076e13061a798` | `accept(Ljava/lang/Object;)V` | UNBOUND | required | 698 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener$$Lambda/0x000076e130618000` | `accept(Ljava/lang/Object;)V` | UNBOUND | required | 1 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener$$Lambda/0x000076e130b55c70` | `accept(Ljava/lang/Object;)V` | UNBOUND | required | 1 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator$$Lambda/0x000076e1306077e8` | `accept(Ljava/lang/Object;)V` | UNBOUND | required | 349 / 0 |

### iDempiere application

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `org.adempiere.base.AbstractModelFactory` | `getPO(Ljava/lang/Class;Ljava/lang/String;ILjava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 33 / 0 |
| `org.adempiere.base.AbstractModelFactory` | `getPO(Ljava/lang/Class;Ljava/lang/String;Ljava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 18 / 0 |
| `org.adempiere.base.AnnotationBasedModelFactory` | `getPO(Ljava/lang/String;ILjava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 33 / 0 |
| `org.adempiere.base.AnnotationBasedModelFactory` | `getPO(Ljava/lang/String;Ljava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 18 / 0 |
| `org.adempiere.base.Core` | `getProductPricing()Lorg/adempiere/base/IProductPricing;` | UNBOUND | not required | 2 / 0 |
| `org.adempiere.base.DefaultDocumentFactory` | `getDocument(Lorg/compiere/model/MAcctSchema;ILjava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/acct/Doc;` | UNBOUND | not required | 36 / 0 |
| `org.adempiere.base.ds.DynamicServiceHolder` | `<init>(Lorg/osgi/util/tracker/ServiceTracker;)V` | UNBOUND | not required | 4 / 0 |
| `org.adempiere.base.ds.DynamicServiceLocator` | `list(Ljava/lang/Class;Lorg/adempiere/base/ServiceQuery;)Lorg/adempiere/base/IServicesHolder;` | UNBOUND | not required | 2 / 0 |
| `org.adempiere.base.ds.DynamicServiceLocator` | `locate(Ljava/lang/Class;)Lorg/adempiere/base/IServiceHolder;` | UNBOUND | not required | 2 / 0 |
| `org.adempiere.util.ProcessUtil` | `startWorkFlow(Ljava/util/Properties;Lorg/compiere/process/ProcessInfo;I)Lorg/compiere/wf/MWFProcess;` | UNBOUND | not required | 247 / 0 |
| `org.compiere.acct.Doc` | `<init>(Lorg/compiere/model/MAcctSchema;Ljava/lang/Class;Ljava/sql/ResultSet;Ljava/lang/String;Ljava/lang/String;)V` | BOUND-MATCH | required | 36 / 0 |
| `org.compiere.acct.Doc` | `get(Lorg/compiere/model/MAcctSchema;ILjava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/acct/Doc;` | BOUND-MATCH | required | 38 / 0 |
| `org.compiere.acct.Doc` | `post(ZZZ)Ljava/lang/String;` | BOUND-MATCH | required | 122 / 3 |
| `org.compiere.acct.Doc` | `postImmediate([Lorg/compiere/model/MAcctSchema;IIZLjava/lang/String;)Ljava/lang/String;` | BOUND-MATCH | required | 172 / 0 |
| `org.compiere.acct.Doc` | `postLogic()Ljava/lang/String;` | BOUND-MATCH | required | 27 / 0 |
| `org.compiere.acct.DocManager` | `getDocument(Lorg/compiere/model/MAcctSchema;ILjava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/acct/Doc;` | BOUND-MATCH | required | 38 / 0 |
| `org.compiere.acct.DocManager` | `postDocument([Lorg/compiere/model/MAcctSchema;IIZZZLjava/lang/String;)Ljava/lang/String;` | BOUND-MATCH | required | 172 / 0 |
| `org.compiere.acct.DocManager` | `postDocument([Lorg/compiere/model/MAcctSchema;ILjava/sql/ResultSet;ZZZLjava/lang/String;)Ljava/lang/String;` | BOUND-MATCH | required | 172 / 0 |
| `org.compiere.acct.DocManager` | `startBackDateProcess([Lorg/compiere/model/MAcctSchema;IILjava/lang/String;)Ljava/lang/String;` | BOUND-MATCH | required | 9 / 0 |
| `org.compiere.acct.Doc_AllocationHdr` | `createFacts(Lorg/compiere/model/MAcctSchema;)Ljava/util/ArrayList;` | UNBOUND | not required | 27 / 0 |
| `org.compiere.acct.Doc_AllocationHdr` | `createInvoiceRoundingCorrection(Lorg/compiere/model/MAcctSchema;Lorg/compiere/acct/Fact;Lorg/compiere/model/MAccount;Lorg/compiere/model/MAccount;)Ljava/lang/String;` | UNBOUND | not required | 3 / 0 |
| `org.compiere.acct.Doc_AllocationHdr` | `isInterOrg(Lorg/compiere/model/MAcctSchema;)Z` | UNBOUND | not required | 6 / 0 |
| `org.compiere.acct.Doc_AllocationHdr` | `loadDocumentDetails()Ljava/lang/String;` | UNBOUND | not required | 12 / 0 |
| `org.compiere.acct.Doc_AllocationHdr` | `loadLines(Lorg/compiere/model/MAllocationHdr;)[Lorg/compiere/acct/DocLine;` | UNBOUND | not required | 12 / 0 |
| `org.compiere.acct.Doc_Inventory` | `loadDocumentDetails()Ljava/lang/String;` | UNBOUND | not required | 6 / 0 |
| `org.compiere.acct.Doc_Inventory` | `loadLines(Lorg/compiere/model/MInventory;)[Lorg/compiere/acct/DocLine;` | UNBOUND | not required | 6 / 0 |
| `org.compiere.acct.Doc_Invoice` | `<init>(Lorg/compiere/model/MAcctSchema;Ljava/sql/ResultSet;Ljava/lang/String;)V` | UNBOUND | not required | 36 / 0 |
| `org.compiere.acct.Doc_Invoice` | `loadDocumentDetails()Ljava/lang/String;` | UNBOUND | not required | 6 / 0 |
| `org.compiere.acct.Doc_Invoice` | `loadLines(Lorg/compiere/model/MInvoice;)[Lorg/compiere/acct/DocLine;` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MAllocationHdr` | `prepareIt()Ljava/lang/String;` | UNBOUND | not required | 9 / 0 |
| `org.compiere.model.MAllocationHdr` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 41 / 0 |
| `org.compiere.model.MAllocationLine` | `beforeSave(Z)Z` | UNBOUND | not required | 9 / 0 |
| `org.compiere.model.MAllocationLine` | `getInvoice()Lorg/compiere/model/MInvoice;` | UNBOUND | not required | 18 / 0 |
| `org.compiere.model.MBPGroup` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MBPGroup` | `get(Ljava/util/Properties;ILjava/lang/String;)Lorg/compiere/model/MBPGroup;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MBPGroup` | `getCopy(Ljava/util/Properties;ILjava/lang/String;)Lorg/compiere/model/MBPGroup;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MBPartner` | `beforeSave(Z)Z` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MBPartner` | `getBPGroup()Lorg/compiere/model/MBPGroup;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MCost` | `create(Lorg/compiere/model/MProduct;)V` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.MCost` | `createCostingRecord(Lorg/compiere/model/MProduct;ILorg/compiere/model/MAcctSchema;II)V` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.MCostDetail` | `getDateAcct(IILjava/lang/String;)Ljava/sql/Timestamp;` | UNBOUND | not required | 9 / 0 |
| `org.compiere.model.MDocType` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.MDocType` | `get(I)Lorg/compiere/model/MDocType;` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.MDocType` | `get(Ljava/util/Properties;I)Lorg/compiere/model/MDocType;` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.MInOut` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.MInventory` | `beforeSave(Z)Z` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.MInventory` | `checkMaterialPolicy(Lorg/compiere/model/MInventoryLine;Ljava/math/BigDecimal;)V` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MInventory` | `completeIt()Ljava/lang/String;` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MInventory` | `getLines(Z)[Lorg/compiere/model/MInventoryLine;` | UNBOUND | not required | 18 / 0 |
| `org.compiere.model.MInventory` | `getSummary()Ljava/lang/String;` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.MInventory` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 20 / 0 |
| `org.compiere.model.MInventoryLine` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MInventoryLine` | `<init>(Ljava/util/Properties;ILjava/lang/String;[Ljava/lang/String;)V` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MInventoryLine` | `<init>(Ljava/util/Properties;Ljava/sql/ResultSet;Ljava/lang/String;)V` | UNBOUND | not required | 18 / 0 |
| `org.compiere.model.MInventoryLineMA` | `beforeSave(Z)Z` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MInvoice` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 111 / 0 |
| `org.compiere.model.MInvoice` | `<init>(Ljava/util/Properties;ILjava/lang/String;[Ljava/lang/String;)V` | UNBOUND | not required | 111 / 0 |
| `org.compiere.model.MInvoice` | `<init>(Ljava/util/Properties;Ljava/sql/ResultSet;Ljava/lang/String;)V` | UNBOUND | not required | 18 / 0 |
| `org.compiere.model.MInvoice` | `copyFrom(Lorg/compiere/model/MInvoice;Ljava/sql/Timestamp;Ljava/sql/Timestamp;IZZLjava/lang/String;Z)Lorg/compiere/model/MInvoice;` | UNBOUND | not required | 3 / 0 |
| `org.compiere.model.MInvoice` | `copyFrom(Lorg/compiere/model/MInvoice;Ljava/sql/Timestamp;Ljava/sql/Timestamp;IZZLjava/lang/String;ZLjava/lang/String;)Lorg/compiere/model/MInvoice;` | UNBOUND | not required | 3 / 0 |
| `org.compiere.model.MInvoice` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 157 / 0 |
| `org.compiere.model.MInvoice` | `reverse(Z)Lorg/compiere/model/MInvoice;` | UNBOUND | not required | 82 / 0 |
| `org.compiere.model.MInvoice` | `reverseCorrectIt()Z` | UNBOUND | not required | 82 / 0 |
| `org.compiere.model.MInvoiceLine` | `getParent()Lorg/compiere/model/MInvoice;` | UNBOUND | not required | 3 / 0 |
| `org.compiere.model.MOrder` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 8 / 0 |
| `org.compiere.model.MOrderLine` | `beforeSave(Z)Z` | UNBOUND | not required | 2 / 0 |
| `org.compiere.model.MOrderLine` | `getProductPricing(I)Lorg/adempiere/base/IProductPricing;` | UNBOUND | not required | 2 / 0 |
| `org.compiere.model.MPayment` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 3 / 0 |
| `org.compiere.model.MPayment` | `allocateInvoice()Z` | UNBOUND | not required | 9 / 0 |
| `org.compiere.model.MPayment` | `allocateIt()Z` | UNBOUND | not required | 9 / 0 |
| `org.compiere.model.MPayment` | `beforeSave(Z)Z` | UNBOUND | not required | 3 / 0 |
| `org.compiere.model.MPayment` | `completeIt()Ljava/lang/String;` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.MPayment` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 43 / 0 |
| `org.compiere.model.MProduct` | `afterSave(ZZ)Z` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.MTable` | `getPO(ILjava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 33 / 0 |
| `org.compiere.model.MTable` | `getPO(Ljava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 18 / 0 |
| `org.compiere.model.PO` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | BOUND-MATCH | required | 8 / 0 |
| `org.compiere.model.PO` | `<init>(Ljava/util/Properties;ILjava/lang/String;Ljava/sql/ResultSet;[Ljava/lang/String;)V` | BOUND-MATCH | required | 161 / 0 |
| `org.compiere.model.PO` | `<init>(Ljava/util/Properties;ILjava/lang/String;[Ljava/lang/String;)V` | BOUND-MATCH | required | 117 / 0 |
| `org.compiere.model.PO` | `<init>(Ljava/util/Properties;Ljava/sql/ResultSet;Ljava/lang/String;)V` | BOUND-MATCH | required | 36 / 0 |
| `org.compiere.model.PO` | `checkRecordIDCrossTenant()V` | BOUND-MATCH | required | 3 / 0 |
| `org.compiere.model.PO` | `doInsert(Z)Z` | BOUND-MATCH | required | 27 / 0 |
| `org.compiere.model.PO` | `load(ILjava/lang/String;[Ljava/lang/String;)V` | BOUND-MATCH | required | 117 / 0 |
| `org.compiere.model.PO` | `load(Ljava/lang/String;[Ljava/lang/String;)Z` | BOUND-MATCH | required | 207 / 0 |
| `org.compiere.model.PO` | `load(Ljava/sql/ResultSet;)Z` | BOUND-MATCH | required | 243 / 0 |
| `org.compiere.model.PO` | `loadColumn(Ljava/sql/ResultSet;I)Z` | BOUND-MATCH | required | 243 / 81 |
| `org.compiere.model.PO` | `loadPO(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;)Z` | BOUND-MATCH | required | 207 / 0 |
| `org.compiere.model.PO` | `save()Z` | BOUND-MATCH | required | 67 / 0 |
| `org.compiere.model.PO` | `saveEx()V` | BOUND-MATCH | required | 55 / 0 |
| `org.compiere.model.PO` | `saveEx(Ljava/lang/String;)V` | BOUND-MATCH | required | 6 / 0 |
| `org.compiere.model.PO` | `saveFinish(ZZ)Z` | BOUND-MATCH | required | 12 / 0 |
| `org.compiere.model.PO` | `saveNew()Z` | BOUND-MATCH | required | 39 / 0 |
| `org.compiere.model.POInfo` | `<init>(Ljava/util/Properties;IZLjava/lang/String;)V` | UNBOUND | not required | 8 / 0 |
| `org.compiere.model.POInfo` | `getPOInfo(Ljava/util/Properties;ILjava/lang/String;)Lorg/compiere/model/POInfo;` | UNBOUND | not required | 8 / 0 |
| `org.compiere.model.POInfo` | `loadInfo(ZLjava/lang/String;)V` | UNBOUND | not required | 8 / 0 |
| `org.compiere.model.POInfoColumn` | `<init>(ILjava/lang/String;Ljava/lang/String;IZZLjava/lang/String;Ljava/lang/String;Ljava/lang/String;ZZILjava/lang/String;ILjava/lang/String;Ljava/lang/String;ZZZZ)V` | UNBOUND | not required | 8 / 8 |
| `org.compiere.model.Query` | `getPO(Ljava/sql/ResultSet;)Lorg/compiere/model/PO;` | UNBOUND | not required | 18 / 0 |
| `org.compiere.model.Query` | `list()Ljava/util/List;` | UNBOUND | not required | 18 / 0 |
| `org.compiere.model.X_C_BP_Group` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.X_C_BP_Group` | `initPO(Ljava/util/Properties;)Lorg/compiere/model/POInfo;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.X_C_DocType` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.X_C_DocType` | `initPO(Ljava/util/Properties;)Lorg/compiere/model/POInfo;` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.X_C_Invoice` | `<init>(Ljava/util/Properties;ILjava/lang/String;[Ljava/lang/String;)V` | UNBOUND | not required | 111 / 0 |
| `org.compiere.model.X_C_Invoice` | `<init>(Ljava/util/Properties;Ljava/sql/ResultSet;Ljava/lang/String;)V` | UNBOUND | not required | 18 / 0 |
| `org.compiere.model.X_C_Payment` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 3 / 0 |
| `org.compiere.model.X_C_Payment` | `initPO(Ljava/util/Properties;)Lorg/compiere/model/POInfo;` | UNBOUND | not required | 3 / 0 |
| `org.compiere.model.X_M_InventoryLine` | `<init>(Ljava/util/Properties;ILjava/lang/String;[Ljava/lang/String;)V` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.X_M_InventoryLine` | `<init>(Ljava/util/Properties;Ljava/sql/ResultSet;Ljava/lang/String;)V` | UNBOUND | not required | 18 / 0 |
| `org.compiere.model.credit.CreditManagerPayment` | `checkCreditStatus(Ljava/lang/String;)Lorg/adempiere/base/CreditStatus;` | UNBOUND | not required | 9 / 0 |
| `org.compiere.process.DocumentEngine` | `completeIt()Ljava/lang/String;` | UNBOUND | not required | 18 / 0 |
| `org.compiere.process.DocumentEngine` | `postImmediate(Ljava/util/Properties;IIIZLjava/lang/String;)Ljava/lang/String;` | UNBOUND | not required | 172 / 0 |
| `org.compiere.process.DocumentEngine` | `postIt()Z` | UNBOUND | not required | 149 / 0 |
| `org.compiere.process.DocumentEngine` | `prepareIt()Ljava/lang/String;` | UNBOUND | not required | 9 / 0 |
| `org.compiere.process.DocumentEngine` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 281 / 0 |
| `org.compiere.process.DocumentEngine` | `processIt(Ljava/lang/String;Ljava/lang/String;)Z` | UNBOUND | not required | 281 / 0 |
| `org.compiere.process.DocumentEngine` | `reverseCorrectIt()Z` | UNBOUND | not required | 82 / 0 |
| `org.compiere.process.ServerProcessCtl` | `process(Lorg/compiere/process/ProcessInfo;Lorg/compiere/util/Trx;)Lorg/compiere/process/ServerProcessCtl;` | UNBOUND | not required | 247 / 0 |
| `org.compiere.process.ServerProcessCtl` | `process(Lorg/compiere/process/ProcessInfo;Lorg/compiere/util/Trx;Z)Lorg/compiere/process/ServerProcessCtl;` | UNBOUND | not required | 247 / 0 |
| `org.compiere.process.ServerProcessCtl` | `run()V` | UNBOUND | not required | 247 / 0 |
| `org.compiere.process.ServerProcessCtl` | `startWorkflow(I)Z` | UNBOUND | not required | 247 / 0 |
| `org.compiere.util.DB` | `executeUpdate(Ljava/lang/String;Ljava/lang/String;)I` | BOUND-MATCH | required | 34 / 0 |
| `org.compiere.util.Trx` | `rollback(Ljava/sql/Savepoint;)Z` | UNBOUND | not required | 3 / 0 |
| `org.compiere.wf.MWFActivity` | `getPO(Lorg/compiere/util/Trx;)Lorg/compiere/model/PO;` | UNBOUND | not required | 24 / 0 |
| `org.compiere.wf.MWFActivity` | `getPO_AD_Client_ID()I` | UNBOUND | not required | 24 / 0 |
| `org.compiere.wf.MWFActivity` | `performWork(Lorg/compiere/util/Trx;)Z` | UNBOUND | not required | 217 / 0 |
| `org.compiere.wf.MWFActivity` | `run()V` | UNBOUND | not required | 614 / 0 |
| `org.compiere.wf.MWFActivity` | `setWFState(Ljava/lang/String;)V` | UNBOUND | not required | 397 / 0 |
| `org.compiere.wf.MWFProcess` | `<init>(Lorg/compiere/wf/MWorkflow;Lorg/compiere/process/ProcessInfo;Ljava/lang/String;)V` | UNBOUND | not required | 6 / 0 |
| `org.compiere.wf.MWFProcess` | `checkActivities(Ljava/lang/String;Lorg/compiere/model/PO;)V` | UNBOUND | not required | 397 / 0 |
| `org.compiere.wf.MWFProcess` | `setTextMsg(Lorg/compiere/model/PO;)V` | UNBOUND | not required | 6 / 0 |
| `org.compiere.wf.MWFProcess` | `startNext(Lorg/compiere/wf/MWFActivity;[Lorg/compiere/wf/MWFActivity;Lorg/compiere/model/PO;Ljava/lang/String;)Z` | UNBOUND | not required | 397 / 0 |
| `org.compiere.wf.MWFProcess` | `startWork()Z` | UNBOUND | not required | 241 / 0 |
| `org.compiere.wf.MWorkflow` | `runDocumentActionWorkflow(Lorg/compiere/model/PO;Ljava/lang/String;)Lorg/compiere/process/ProcessInfo;` | UNBOUND | not required | 247 / 0 |
| `org.compiere.wf.MWorkflow` | `start(Lorg/compiere/process/ProcessInfo;Ljava/lang/String;)Lorg/compiere/wf/MWFProcess;` | UNBOUND | not required | 247 / 0 |

### other dependency

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `com.zaxxer.hikari.pool.HikariProxyConnection` | `rollback(Ljava/sql/Savepoint;)V` | UNBOUND | not required | 3 / 0 |
| `com.zaxxer.hikari.pool.HikariProxyResultSet` | `getString(Ljava/lang/String;)Ljava/lang/String;` | UNBOUND | not required | 243 / 81 |
| `com.zaxxer.hikari.pool.ProxyConnection` | `rollback(Ljava/sql/Savepoint;)V` | UNBOUND | not required | 3 / 0 |
| `oracle.jdbc.driver.GeneratedResultSet` | `getString(Ljava/lang/String;)Ljava/lang/String;` | UNBOUND | not required | 162 / 0 |
| `oracle.jdbc.driver.InsensitiveScrollableResultSet` | `findColumn(Ljava/lang/String;)I` | UNBOUND | not required | 162 / 81 |
| `oracle.jdbc.driver.OracleSavepoint` | `getSavepointName()Ljava/lang/String;` | UNBOUND | not required | 3 / 0 |
| `oracle.jdbc.driver.OracleStatement` | `getColumnIndex(Ljava/lang/String;)I` | UNBOUND | not required | 81 / 0 |
| `oracle.jdbc.driver.OracleStatement` | `getColumnIndexPrimitive(Ljava/lang/String;)I` | UNBOUND | not required | 81 / 0 |
| `oracle.jdbc.driver.PhysicalConnection` | `rollback(Ljava/sql/Savepoint;)V` | UNBOUND | not required | 3 / 3 |
| `org.apache.felix.scr.impl.inject.methods.ActivateMethod` | `doFindMethod(Ljava/lang/Class;ZZLorg/apache/felix/scr/impl/logger/ComponentLogger;)Lorg/apache/felix/scr/impl/inject/methods/BaseMethod$MethodInfo;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.ActivateMethod` | `invoke(Ljava/lang/Object;Lorg/apache/felix/scr/impl/inject/ActivatorParameter;Lorg/apache/felix/scr/impl/inject/MethodResult;)Lorg/apache/felix/scr/impl/inject/MethodResult;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.ActivateMethod` | `invoke(Ljava/lang/Object;Lorg/apache/felix/scr/impl/inject/ScrComponentContext;ILorg/apache/felix/scr/impl/inject/MethodResult;)Lorg/apache/felix/scr/impl/inject/MethodResult;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod` | `access$400(Lorg/apache/felix/scr/impl/inject/methods/BaseMethod;Lorg/apache/felix/scr/impl/logger/ComponentLogger;)Lorg/apache/felix/scr/impl/inject/methods/BaseMethod$MethodInfo;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod` | `findMethod(Lorg/apache/felix/scr/impl/logger/ComponentLogger;)Lorg/apache/felix/scr/impl/inject/methods/BaseMethod$MethodInfo;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod` | `getMethod(Ljava/lang/Class;Ljava/lang/String;[Ljava/lang/Class;ZZLorg/apache/felix/scr/impl/logger/ComponentLogger;)Ljava/lang/reflect/Method;` | UNBOUND | not required | 4 / 4 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod` | `methodExists(Lorg/apache/felix/scr/impl/logger/ComponentLogger;)Z` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod$NotResolved` | `methodExists(Lorg/apache/felix/scr/impl/inject/methods/BaseMethod;Lorg/apache/felix/scr/impl/logger/ComponentLogger;)Z` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod$NotResolved` | `resolve(Lorg/apache/felix/scr/impl/inject/methods/BaseMethod;Lorg/apache/felix/scr/impl/logger/ComponentLogger;)V` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.manager.SingleComponentManager` | `createComponent(Lorg/apache/felix/scr/impl/manager/ComponentContextImpl;)Z` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.manager.SingleComponentManager` | `createImplementationObject(Lorg/osgi/framework/Bundle;Lorg/apache/felix/scr/impl/manager/SingleComponentManager$SetImplementationObject;Lorg/apache/felix/scr/impl/manager/ComponentContextImpl;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.manager.SingleComponentManager` | `getService(Lorg/apache/felix/scr/impl/manager/ComponentContextImpl;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.manager.SingleComponentManager` | `getService(Lorg/osgi/framework/Bundle;Lorg/osgi/framework/ServiceRegistration;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.manager.SingleComponentManager` | `getServiceInternal(Lorg/osgi/framework/ServiceRegistration;)Z` | UNBOUND | not required | 4 / 0 |

### support

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `org.idempiere.test.JourneySupport` | `postOnce(Lorg/compiere/model/PO;[Lorg/compiere/model/MAcctSchema;)V` | BOUND-MATCH | required | 25 / 0 |
| `org.idempiere.test.JourneySupport` | `transaction(Ljava/lang/String;Lorg/idempiere/test/JourneySupport$TransactionBody;)Ljava/lang/Object;` | BOUND-MATCH | required | 3 / 2 |

## postgresql

### JDK

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `java.lang.Class` | `getDeclaredMethod(Ljava/lang/String;[Ljava/lang/Class;)Ljava/lang/reflect/Method;` | UNBOUND | not required | 4 / 0 |
| `java.lang.ClassLoader` | `loadClass(Ljava/lang/String;)Ljava/lang/Class;` | UNBOUND | not required | 9 / 0 |
| `java.lang.invoke.DirectMethodHandle$Holder` | `invokeStatic(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `java.lang.invoke.DirectMethodHandle$Holder` | `newInvokeSpecial(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 48 / 0 |
| `java.lang.invoke.Invokers$Holder` | `invokeExact_MT(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 271 / 0 |
| `java.lang.invoke.Invokers$Holder` | `invokeExact_MT(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `java.lang.reflect.Constructor` | `newInstance([Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 70 / 0 |
| `java.lang.reflect.Constructor` | `newInstanceWithCaller([Ljava/lang/Object;ZLjava/lang/Class;)Ljava/lang/Object;` | UNBOUND | not required | 70 / 0 |
| `java.lang.reflect.Method` | `invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 815 / 0 |
| `java.security.AccessController` | `doPrivileged(Ljava/security/PrivilegedAction;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `java.security.AccessController` | `executePrivileged(Ljava/security/PrivilegedAction;Ljava/security/AccessControlContext;Ljava/lang/Class;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `java.text.DateFormat` | `parse(Ljava/lang/String;)Ljava/util/Date;` | UNBOUND | not required | 8 / 0 |
| `java.util.ArrayList` | `forEach(Ljava/util/function/Consumer;)V` | UNBOUND | not required | 545 / 0 |
| `java.util.ResourceBundle` | `findBundle(Ljava/lang/Module;Ljava/lang/Module;Ljava/util/ResourceBundle$CacheKey;Ljava/util/List;Ljava/util/List;ILjava/util/ResourceBundle$Control;Ljava/util/ResourceBundle;)Ljava/util/ResourceBundle;` | UNBOUND | not required | 12 / 0 |
| `java.util.ResourceBundle` | `getBundle(Ljava/lang/String;Ljava/util/Locale;)Ljava/util/ResourceBundle;` | UNBOUND | not required | 7 / 0 |
| `java.util.ResourceBundle` | `getBundleImpl(Ljava/lang/Module;Ljava/lang/Module;Ljava/lang/String;Ljava/util/Locale;Ljava/util/ResourceBundle$Control;)Ljava/util/ResourceBundle;` | UNBOUND | not required | 7 / 0 |
| `java.util.ResourceBundle` | `getBundleImpl(Ljava/lang/String;Ljava/util/Locale;Ljava/lang/Class;Ljava/lang/ClassLoader;Ljava/util/ResourceBundle$Control;)Ljava/util/ResourceBundle;` | UNBOUND | not required | 7 / 0 |
| `java.util.ResourceBundle` | `getBundleImpl(Ljava/lang/String;Ljava/util/Locale;Ljava/lang/Class;Ljava/util/ResourceBundle$Control;)Ljava/util/ResourceBundle;` | UNBOUND | not required | 7 / 0 |
| `java.util.ResourceBundle` | `loadBundle(Ljava/util/ResourceBundle$CacheKey;Ljava/util/List;Ljava/util/ResourceBundle$Control;Z)Ljava/util/ResourceBundle;` | UNBOUND | not required | 6 / 0 |
| `java.util.ResourceBundle` | `throwMissingResourceException(Ljava/lang/String;Ljava/util/Locale;Ljava/lang/Throwable;)V` | UNBOUND | not required | 1 / 0 |
| `java.util.ResourceBundle$Control` | `newBundle(Ljava/lang/String;Ljava/util/Locale;Ljava/lang/String;Ljava/lang/ClassLoader;Z)Ljava/util/ResourceBundle;` | UNBOUND | not required | 6 / 0 |
| `java.util.ResourceBundle$Control` | `newBundle0(Ljava/lang/String;Ljava/lang/String;Ljava/lang/ClassLoader;Z)Ljava/util/ResourceBundle;` | UNBOUND | not required | 6 / 3 |
| `jdk.internal.loader.BuiltinClassLoader` | `loadClass(Ljava/lang/String;Z)Ljava/lang/Class;` | UNBOUND | not required | 3 / 0 |
| `jdk.internal.reflect.DirectConstructorHandleAccessor` | `invokeImpl([Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 70 / 0 |
| `jdk.internal.reflect.DirectConstructorHandleAccessor` | `newInstance([Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 70 / 0 |
| `jdk.internal.reflect.DirectMethodHandleAccessor` | `invoke(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 815 / 0 |
| `jdk.internal.reflect.DirectMethodHandleAccessor` | `invokeImpl(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 815 / 0 |

### OSGi/Tycho/JUnit framework

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `org.apache.maven.surefire.api.util.ReflectionUtils` | `invokeMethodWithArray2(Ljava/lang/Object;Ljava/lang/reflect/Method;[Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `org.apache.maven.surefire.booter.ProviderFactory` | `invokeProvider(Ljava/lang/Object;Ljava/lang/ClassLoader;Ljava/lang/Object;Lorg/apache/maven/surefire/booter/ProviderConfiguration;ZLorg/apache/maven/surefire/booter/StartupConfiguration;Z)Lorg/apache/maven/surefire/api/suite/RunResult;` | UNBOUND | not required | 272 / 0 |
| `org.apache.maven.surefire.booter.ProviderFactory$ProviderProxy` | `invoke(Ljava/lang/Object;)Lorg/apache/maven/surefire/api/suite/RunResult;` | UNBOUND | not required | 272 / 0 |
| `org.apache.maven.surefire.junitplatform.JUnitPlatformProvider` | `execute(Lorg/apache/maven/surefire/api/util/TestsToRun;Lorg/apache/maven/surefire/junitplatform/RunListenerAdapter;)V` | UNBOUND | not required | 272 / 0 |
| `org.apache.maven.surefire.junitplatform.JUnitPlatformProvider` | `invoke(Ljava/lang/Object;)Lorg/apache/maven/surefire/api/suite/RunResult;` | UNBOUND | not required | 272 / 0 |
| `org.apache.maven.surefire.junitplatform.JUnitPlatformProvider` | `invokeAllTests(Lorg/apache/maven/surefire/api/util/TestsToRun;Lorg/apache/maven/surefire/junitplatform/RunListenerAdapter;)V` | UNBOUND | not required | 272 / 0 |
| `org.apache.maven.surefire.junitplatform.LazyLauncher` | `execute(Lorg/junit/platform/launcher/LauncherDiscoveryRequest;[Lorg/junit/platform/launcher/TestExecutionListener;)V` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.core.runtime.adaptor.EclipseStarter` | `run(Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.core.runtime.adaptor.EclipseStarter` | `run([Ljava/lang/String;Ljava/lang/Runnable;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.core.runtime.internal.adaptor.EclipseAppLauncher` | `runApplication(Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.core.runtime.internal.adaptor.EclipseAppLauncher` | `start(Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.equinox.internal.app.EclipseAppHandle` | `run(Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.equinox.launcher.Main` | `basicRun([Ljava/lang/String;)V` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.equinox.launcher.Main` | `invokeFramework([Ljava/lang/String;[Ljava/net/URL;)V` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.equinox.launcher.Main` | `main([Ljava/lang/String;)V` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.equinox.launcher.Main` | `run([Ljava/lang/String;)I` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.osgi.internal.framework.BundleContextImpl` | `getService(Lorg/osgi/framework/ServiceReference;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.loader.BundleLoader` | `findClass(Ljava/lang/String;)Ljava/lang/Class;` | UNBOUND | not required | 6 / 0 |
| `org.eclipse.osgi.internal.loader.BundleLoader` | `findClass0(Ljava/lang/String;ZZ)Ljava/lang/Class;` | UNBOUND | not required | 6 / 3 |
| `org.eclipse.osgi.internal.loader.BundleLoader` | `generateException(Ljava/lang/String;Z)Ljava/lang/Class;` | UNBOUND | not required | 3 / 0 |
| `org.eclipse.osgi.internal.loader.ModuleClassLoader` | `loadClass(Ljava/lang/String;Z)Ljava/lang/Class;` | UNBOUND | not required | 6 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceConsumer$2` | `getService(Lorg/eclipse/osgi/internal/serviceregistry/ServiceUse;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceFactoryUse` | `factoryGetService()Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceFactoryUse` | `getService()Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceFactoryUse$1` | `run()Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceRegistrationImpl` | `getService(Lorg/eclipse/osgi/internal/framework/BundleContextImpl;Lorg/eclipse/osgi/internal/serviceregistry/ServiceConsumer;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.osgi.internal.serviceregistry.ServiceRegistry` | `getService(Lorg/eclipse/osgi/internal/framework/BundleContextImpl;Lorg/eclipse/osgi/internal/serviceregistry/ServiceReferenceImpl;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.eclipse.tycho.surefire.osgibooter.HeadlessTestApplication` | `start(Lorg/eclipse/equinox/app/IApplicationContext;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `org.eclipse.tycho.surefire.osgibooter.OsgiSurefireBooter` | `run([Ljava/lang/String;Ljava/util/Properties;)I` | UNBOUND | not required | 272 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor` | `execute(Lorg/junit/jupiter/engine/execution/JupiterEngineExecutionContext;Lorg/junit/platform/engine/support/hierarchical/Node$DynamicTestExecutor;)Lorg/junit/jupiter/engine/execution/JupiterEngineExecutionContext;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor` | `execute(Lorg/junit/platform/engine/support/hierarchical/EngineExecutionContext;Lorg/junit/platform/engine/support/hierarchical/Node$DynamicTestExecutor;)Lorg/junit/platform/engine/support/hierarchical/EngineExecutionContext;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor` | `invokeTestMethod(Lorg/junit/jupiter/engine/execution/JupiterEngineExecutionContext;Lorg/junit/platform/engine/support/hierarchical/Node$DynamicTestExecutor;)V` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor` | `lambda$invokeTestMethod$7(Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/engine/execution/JupiterEngineExecutionContext;)V` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker` | `invoke(Ljava/lang/reflect/Method;Ljava/lang/Object;Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/engine/extension/ExtensionRegistry;Lorg/junit/jupiter/engine/execution/InterceptingExecutableInvoker$ReflectiveInterceptorCall;)Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker` | `invoke(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/engine/extension/ExtensionRegistry;Lorg/junit/jupiter/engine/execution/InterceptingExecutableInvoker$ReflectiveInterceptorCall;)Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker` | `lambda$invoke$0(Lorg/junit/jupiter/engine/execution/InterceptingExecutableInvoker$ReflectiveInterceptorCall;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/api/extension/InvocationInterceptor;Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;)Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker$ReflectiveInterceptorCall` | `lambda$ofVoidMethod$0(Lorg/junit/jupiter/engine/execution/InterceptingExecutableInvoker$ReflectiveInterceptorCall$VoidMethodInterceptorCall;Lorg/junit/jupiter/api/extension/InvocationInterceptor;Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;)Ljava/lang/Void;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InvocationInterceptorChain` | `chainAndInvoke(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/engine/execution/InvocationInterceptorChain$InterceptorCall;Ljava/util/List;)Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InvocationInterceptorChain` | `invoke(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/engine/extension/ExtensionRegistry;Lorg/junit/jupiter/engine/execution/InvocationInterceptorChain$InterceptorCall;)Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InvocationInterceptorChain` | `proceed(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;)Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InvocationInterceptorChain$InterceptedInvocation` | `proceed()Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InvocationInterceptorChain$ValidatingInvocation` | `proceed()Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.MethodInvocation` | `proceed()Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.extension.TimeoutExtension` | `intercept(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/engine/extension/TimeoutDuration;Lorg/junit/jupiter/engine/extension/TimeoutExtension$TimeoutProvider;)Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.extension.TimeoutExtension` | `interceptTestMethod(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;)V` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.jupiter.engine.extension.TimeoutExtension` | `interceptTestableMethod(Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;Lorg/junit/jupiter/engine/extension/TimeoutExtension$TimeoutProvider;)Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.platform.commons.util.ReflectionUtils` | `invokeMethod(Ljava/lang/reflect/Method;Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;` | BOUND-MATCH | required | 271 / 0 |
| `org.junit.platform.engine.support.hierarchical.HierarchicalTestEngine` | `execute(Lorg/junit/platform/engine/ExecutionRequest;)V` | BOUND-BUT-MISMATCH | required | 272 / 0 |
| `org.junit.platform.engine.support.hierarchical.HierarchicalTestExecutor` | `execute()Ljava/util/concurrent/Future;` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.engine.support.hierarchical.Node` | `around(Lorg/junit/platform/engine/support/hierarchical/EngineExecutionContext;Lorg/junit/platform/engine/support/hierarchical/Node$Invocation;)V` | BOUND-MATCH | required | 815 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `execute()V` | BOUND-MATCH | required | 816 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `executeRecursively()V` | BOUND-MATCH | required | 815 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `lambda$executeRecursively$6()V` | BOUND-MATCH | required | 815 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `lambda$executeRecursively$8(Lorg/junit/platform/engine/support/hierarchical/EngineExecutionContext;)V` | BOUND-MATCH | required | 815 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `lambda$executeRecursively$9()V` | BOUND-MATCH | required | 815 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask` | `reportCompletion()V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.engine.support.hierarchical.SameThreadHierarchicalTestExecutorService` | `invokeAll(Ljava/util/List;)V` | BOUND-MATCH | required | 544 / 0 |
| `org.junit.platform.engine.support.hierarchical.SameThreadHierarchicalTestExecutorService` | `submit(Lorg/junit/platform/engine/support/hierarchical/HierarchicalTestExecutorService$TestTask;)Ljava/util/concurrent/Future;` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.engine.support.hierarchical.ThrowableCollector` | `execute(Lorg/junit/platform/engine/support/hierarchical/ThrowableCollector$Executable;)V` | BOUND-MATCH | required | 1901 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener` | `executionFinished(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener` | `lambda$executionFinished$6(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;Lorg/junit/platform/engine/EngineExecutionListener;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener` | `lambda$notifyEach$11(Ljava/util/function/Consumer;Ljava/util/function/Supplier;Lorg/junit/platform/engine/EngineExecutionListener;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener` | `notifyEach(Ljava/util/List;Ljava/util/function/Consumer;Ljava/util/function/Supplier;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.DefaultLauncher` | `execute(Lorg/junit/platform/launcher/LauncherDiscoveryRequest;[Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.launcher.core.DefaultLauncher` | `execute(Lorg/junit/platform/launcher/core/InternalTestPlan;[Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.launcher.core.DefaultLauncherSession$DelegatingLauncher` | `execute(Lorg/junit/platform/launcher/LauncherDiscoveryRequest;[Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.launcher.core.DelegatingEngineExecutionListener` | `executionFinished(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `execute(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/EngineExecutionListener;Lorg/junit/platform/engine/ConfigurationParameters;Lorg/junit/platform/engine/TestEngine;)V` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `execute(Lorg/junit/platform/launcher/core/InternalTestPlan;Lorg/junit/platform/engine/EngineExecutionListener;Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `execute(Lorg/junit/platform/launcher/core/InternalTestPlan;[Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `execute(Lorg/junit/platform/launcher/core/LauncherDiscoveryResult;Lorg/junit/platform/engine/EngineExecutionListener;)V` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `lambda$execute$0(Lorg/junit/platform/launcher/core/InternalTestPlan;Lorg/junit/platform/launcher/TestExecutionListener;)V` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator` | `withInterceptedStreams(Lorg/junit/platform/engine/ConfigurationParameters;Lorg/junit/platform/launcher/core/ListenerRegistry;Ljava/util/function/Consumer;)V` | BOUND-MATCH | required | 272 / 0 |
| `org.junit.platform.launcher.core.ExecutionListenerAdapter` | `executionFinished(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.junit.platform.launcher.core.OutcomeDelayingEngineExecutionListener` | `executionFinished(Lorg/junit/platform/engine/TestDescriptor;Lorg/junit/platform/engine/TestExecutionResult;)V` | BOUND-MATCH | required | 1 / 0 |
| `org.osgi.util.tracker.AbstractTracked` | `trackAdding(Ljava/lang/Object;Ljava/lang/Object;)V` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.AbstractTracked` | `trackInitial()V` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.ServiceTracker` | `addingService(Lorg/osgi/framework/ServiceReference;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.ServiceTracker` | `open()V` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.ServiceTracker` | `open(Z)V` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.ServiceTracker$Tracked` | `customizerAdding(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.osgi.util.tracker.ServiceTracker$Tracked` | `customizerAdding(Lorg/osgi/framework/ServiceReference;Lorg/osgi/framework/ServiceEvent;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |

### candidate

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `org.idempiere.test.LightyearOperationsTest` | `action(Lorg/compiere/model/PO;Ljava/lang/String;)V` | BOUND-MATCH | required | 193 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `complete(Ljava/lang/String;Lorg/compiere/model/PO;)V` | BOUND-MATCH | required | 127 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `lambda$1(Ljava/util/Properties;Lorg/compiere/model/MBPartner;Ljava/lang/String;)Ljava/lang/Object;` | BOUND-MATCH | required | 1 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `operationsJourney()V` | BOUND-MATCH | required | 271 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `post(Lorg/compiere/model/PO;[Lorg/compiere/model/MAcctSchema;)V` | BOUND-MATCH | required | 22 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `postAllocations(Ljava/util/Properties;ILjava/lang/String;[Lorg/compiere/model/MAcctSchema;)V` | BOUND-MATCH | required | 6 / 0 |
| `org.idempiere.test.LightyearOperationsTest` | `recovery(Ljava/util/Properties;Lorg/compiere/model/MBPartner;)V` | BOUND-MATCH | required | 3 / 1 |

### generated/hidden

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `java.lang.invoke.LambdaForm$DMH/0x0000772a04000c00` | `invokeVirtual(Ljava/lang/Object;Ljava/lang/Object;)V` | UNBOUND | not required | 271 / 0 |
| `java.lang.invoke.LambdaForm$DMH/0x0000772a041b8800` | `invokeVirtual(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `java.lang.invoke.LambdaForm$DMH/0x0000772a049c0000` | `newInvokeSpecial(Ljava/lang/Object;Ljava/lang/Object;ILjava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 22 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x0000772a04001400` | `invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x0000772a04006800` | `invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 272 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x0000772a04006c00` | `invokeExact_MT(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 342 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x0000772a040bc800` | `invoke(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 271 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x0000772a045c1800` | `invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 24 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x0000772a049c0c00` | `invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 22 / 0 |
| `java.lang.invoke.LambdaForm$MH/0x0000772a049e1000` | `invoke(Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;` | UNBOUND | not required | 24 / 0 |
| `org.idempiere.test.LightyearOperationsTest$$Lambda/0x0000772a049d0a80` | `run(Ljava/lang/String;)Ljava/lang/Object;` | UNBOUND | required | 1 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor$$Lambda/0x0000772a045ff3a8` | `apply(Lorg/junit/jupiter/api/extension/InvocationInterceptor;Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;)V` | UNBOUND | required | 271 / 0 |
| `org.junit.jupiter.engine.descriptor.TestMethodTestDescriptor$$Lambda/0x0000772a04999370` | `execute()V` | UNBOUND | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker$$Lambda/0x0000772a04689e38` | `apply(Lorg/junit/jupiter/api/extension/InvocationInterceptor;Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;)Ljava/lang/Object;` | UNBOUND | required | 271 / 0 |
| `org.junit.jupiter.engine.execution.InterceptingExecutableInvoker$ReflectiveInterceptorCall$$Lambda/0x0000772a045ff7c8` | `apply(Lorg/junit/jupiter/api/extension/InvocationInterceptor;Lorg/junit/jupiter/api/extension/InvocationInterceptor$Invocation;Lorg/junit/jupiter/api/extension/ReflectiveInvocationContext;Lorg/junit/jupiter/api/extension/ExtensionContext;)Ljava/lang/Object;` | UNBOUND | required | 271 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask$$Lambda/0x0000772a04620d40` | `execute()V` | UNBOUND | required | 815 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask$$Lambda/0x0000772a04621168` | `invoke(Lorg/junit/platform/engine/support/hierarchical/EngineExecutionContext;)V` | UNBOUND | required | 815 / 0 |
| `org.junit.platform.engine.support.hierarchical.NodeTestTask$$Lambda/0x0000772a04621390` | `execute()V` | UNBOUND | required | 815 / 0 |
| `org.junit.platform.engine.support.hierarchical.SameThreadHierarchicalTestExecutorService$$Lambda/0x0000772a04621ea8` | `accept(Ljava/lang/Object;)V` | UNBOUND | required | 544 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener$$Lambda/0x0000772a046198c0` | `accept(Ljava/lang/Object;)V` | UNBOUND | required | 1 / 0 |
| `org.junit.platform.launcher.core.CompositeEngineExecutionListener$$Lambda/0x0000772a04a008b0` | `accept(Ljava/lang/Object;)V` | UNBOUND | required | 1 / 0 |
| `org.junit.platform.launcher.core.EngineExecutionOrchestrator$$Lambda/0x0000772a0460f158` | `accept(Ljava/lang/Object;)V` | UNBOUND | required | 272 / 0 |

### iDempiere application

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `org.adempiere.base.AbstractModelFactory` | `getPO(Ljava/lang/Class;Ljava/lang/String;ILjava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 22 / 0 |
| `org.adempiere.base.AbstractModelFactory` | `getPO(Ljava/lang/Class;Ljava/lang/String;Ljava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 12 / 0 |
| `org.adempiere.base.AnnotationBasedModelFactory` | `getPO(Ljava/lang/String;ILjava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 22 / 0 |
| `org.adempiere.base.AnnotationBasedModelFactory` | `getPO(Ljava/lang/String;Ljava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 12 / 0 |
| `org.adempiere.base.Core` | `getProductPricing()Lorg/adempiere/base/IProductPricing;` | UNBOUND | not required | 2 / 0 |
| `org.adempiere.base.DefaultDocumentFactory` | `getDocument(Lorg/compiere/model/MAcctSchema;ILjava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/acct/Doc;` | UNBOUND | not required | 24 / 0 |
| `org.adempiere.base.ds.DynamicServiceHolder` | `<init>(Lorg/osgi/util/tracker/ServiceTracker;)V` | UNBOUND | not required | 4 / 0 |
| `org.adempiere.base.ds.DynamicServiceLocator` | `list(Ljava/lang/Class;Lorg/adempiere/base/ServiceQuery;)Lorg/adempiere/base/IServicesHolder;` | UNBOUND | not required | 2 / 0 |
| `org.adempiere.base.ds.DynamicServiceLocator` | `locate(Ljava/lang/Class;)Lorg/adempiere/base/IServiceHolder;` | UNBOUND | not required | 2 / 0 |
| `org.adempiere.util.ProcessUtil` | `startWorkFlow(Ljava/util/Properties;Lorg/compiere/process/ProcessInfo;I)Lorg/compiere/wf/MWFProcess;` | UNBOUND | not required | 187 / 0 |
| `org.compiere.acct.Doc` | `<init>(Lorg/compiere/model/MAcctSchema;Ljava/lang/Class;Ljava/sql/ResultSet;Ljava/lang/String;Ljava/lang/String;)V` | BOUND-MATCH | required | 24 / 0 |
| `org.compiere.acct.Doc` | `get(Lorg/compiere/model/MAcctSchema;ILjava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/acct/Doc;` | BOUND-MATCH | required | 26 / 0 |
| `org.compiere.acct.Doc` | `post(ZZZ)Ljava/lang/String;` | BOUND-MATCH | required | 105 / 3 |
| `org.compiere.acct.Doc` | `postImmediate([Lorg/compiere/model/MAcctSchema;IIZLjava/lang/String;)Ljava/lang/String;` | BOUND-MATCH | required | 137 / 0 |
| `org.compiere.acct.Doc` | `postLogic()Ljava/lang/String;` | BOUND-MATCH | required | 18 / 0 |
| `org.compiere.acct.DocManager` | `getDocument(Lorg/compiere/model/MAcctSchema;ILjava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/acct/Doc;` | BOUND-MATCH | required | 26 / 0 |
| `org.compiere.acct.DocManager` | `postDocument([Lorg/compiere/model/MAcctSchema;IIZZZLjava/lang/String;)Ljava/lang/String;` | BOUND-MATCH | required | 137 / 0 |
| `org.compiere.acct.DocManager` | `postDocument([Lorg/compiere/model/MAcctSchema;ILjava/sql/ResultSet;ZZZLjava/lang/String;)Ljava/lang/String;` | BOUND-MATCH | required | 137 / 0 |
| `org.compiere.acct.DocManager` | `startBackDateProcess([Lorg/compiere/model/MAcctSchema;IILjava/lang/String;)Ljava/lang/String;` | BOUND-MATCH | required | 6 / 0 |
| `org.compiere.acct.Doc_AllocationHdr` | `createFacts(Lorg/compiere/model/MAcctSchema;)Ljava/util/ArrayList;` | UNBOUND | not required | 18 / 0 |
| `org.compiere.acct.Doc_AllocationHdr` | `createInvoiceRoundingCorrection(Lorg/compiere/model/MAcctSchema;Lorg/compiere/acct/Fact;Lorg/compiere/model/MAccount;Lorg/compiere/model/MAccount;)Ljava/lang/String;` | UNBOUND | not required | 2 / 0 |
| `org.compiere.acct.Doc_AllocationHdr` | `isInterOrg(Lorg/compiere/model/MAcctSchema;)Z` | UNBOUND | not required | 4 / 0 |
| `org.compiere.acct.Doc_AllocationHdr` | `loadDocumentDetails()Ljava/lang/String;` | UNBOUND | not required | 8 / 0 |
| `org.compiere.acct.Doc_AllocationHdr` | `loadLines(Lorg/compiere/model/MAllocationHdr;)[Lorg/compiere/acct/DocLine;` | UNBOUND | not required | 8 / 0 |
| `org.compiere.acct.Doc_Inventory` | `loadDocumentDetails()Ljava/lang/String;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.acct.Doc_Inventory` | `loadLines(Lorg/compiere/model/MInventory;)[Lorg/compiere/acct/DocLine;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.acct.Doc_Invoice` | `<init>(Lorg/compiere/model/MAcctSchema;Ljava/sql/ResultSet;Ljava/lang/String;)V` | UNBOUND | not required | 24 / 0 |
| `org.compiere.acct.Doc_Invoice` | `loadDocumentDetails()Ljava/lang/String;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.acct.Doc_Invoice` | `loadLines(Lorg/compiere/model/MInvoice;)[Lorg/compiere/acct/DocLine;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MAllocationHdr` | `prepareIt()Ljava/lang/String;` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MAllocationHdr` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 30 / 0 |
| `org.compiere.model.MAllocationLine` | `beforeSave(Z)Z` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MAllocationLine` | `getInvoice()Lorg/compiere/model/MInvoice;` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.MBPGroup` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MBPGroup` | `get(Ljava/util/Properties;ILjava/lang/String;)Lorg/compiere/model/MBPGroup;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MBPGroup` | `getCopy(Ljava/util/Properties;ILjava/lang/String;)Lorg/compiere/model/MBPGroup;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MBPartner` | `beforeSave(Z)Z` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MBPartner` | `getBPGroup()Lorg/compiere/model/MBPGroup;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MCost` | `create(Lorg/compiere/model/MProduct;)V` | UNBOUND | not required | 15 / 0 |
| `org.compiere.model.MCost` | `createCostingRecord(Lorg/compiere/model/MProduct;ILorg/compiere/model/MAcctSchema;II)V` | UNBOUND | not required | 15 / 0 |
| `org.compiere.model.MCostDetail` | `getDateAcct(IILjava/lang/String;)Ljava/sql/Timestamp;` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MDocType` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.MDocType` | `get(I)Lorg/compiere/model/MDocType;` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.MDocType` | `get(Ljava/util/Properties;I)Lorg/compiere/model/MDocType;` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.MInOut` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 10 / 0 |
| `org.compiere.model.MInventory` | `beforeSave(Z)Z` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.MInventory` | `checkMaterialPolicy(Lorg/compiere/model/MInventoryLine;Ljava/math/BigDecimal;)V` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MInventory` | `completeIt()Ljava/lang/String;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MInventory` | `getLines(Z)[Lorg/compiere/model/MInventoryLine;` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.MInventory` | `getSummary()Ljava/lang/String;` | UNBOUND | not required | 8 / 0 |
| `org.compiere.model.MInventory` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 15 / 0 |
| `org.compiere.model.MInventoryLine` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MInventoryLine` | `<init>(Ljava/util/Properties;ILjava/lang/String;[Ljava/lang/String;)V` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MInventoryLine` | `<init>(Ljava/util/Properties;Ljava/sql/ResultSet;Ljava/lang/String;)V` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.MInventoryLineMA` | `beforeSave(Z)Z` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.MInvoice` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 74 / 0 |
| `org.compiere.model.MInvoice` | `<init>(Ljava/util/Properties;ILjava/lang/String;[Ljava/lang/String;)V` | UNBOUND | not required | 74 / 0 |
| `org.compiere.model.MInvoice` | `<init>(Ljava/util/Properties;Ljava/sql/ResultSet;Ljava/lang/String;)V` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.MInvoice` | `copyFrom(Lorg/compiere/model/MInvoice;Ljava/sql/Timestamp;Ljava/sql/Timestamp;IZZLjava/lang/String;Z)Lorg/compiere/model/MInvoice;` | UNBOUND | not required | 2 / 0 |
| `org.compiere.model.MInvoice` | `copyFrom(Lorg/compiere/model/MInvoice;Ljava/sql/Timestamp;Ljava/sql/Timestamp;IZZLjava/lang/String;ZLjava/lang/String;)Lorg/compiere/model/MInvoice;` | UNBOUND | not required | 2 / 0 |
| `org.compiere.model.MInvoice` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 118 / 0 |
| `org.compiere.model.MInvoice` | `reverse(Z)Lorg/compiere/model/MInvoice;` | UNBOUND | not required | 60 / 0 |
| `org.compiere.model.MInvoice` | `reverseCorrectIt()Z` | UNBOUND | not required | 60 / 0 |
| `org.compiere.model.MInvoiceLine` | `getParent()Lorg/compiere/model/MInvoice;` | UNBOUND | not required | 2 / 0 |
| `org.compiere.model.MOrder` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 8 / 0 |
| `org.compiere.model.MOrderLine` | `beforeSave(Z)Z` | UNBOUND | not required | 2 / 0 |
| `org.compiere.model.MOrderLine` | `getProductPricing(I)Lorg/adempiere/base/IProductPricing;` | UNBOUND | not required | 2 / 0 |
| `org.compiere.model.MPayment` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 3 / 0 |
| `org.compiere.model.MPayment` | `allocateInvoice()Z` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MPayment` | `allocateIt()Z` | UNBOUND | not required | 6 / 0 |
| `org.compiere.model.MPayment` | `beforeSave(Z)Z` | UNBOUND | not required | 2 / 0 |
| `org.compiere.model.MPayment` | `completeIt()Ljava/lang/String;` | UNBOUND | not required | 8 / 0 |
| `org.compiere.model.MPayment` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 34 / 0 |
| `org.compiere.model.MProduct` | `afterSave(ZZ)Z` | UNBOUND | not required | 15 / 0 |
| `org.compiere.model.MTable` | `getPO(ILjava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 22 / 0 |
| `org.compiere.model.MTable` | `getPO(Ljava/sql/ResultSet;Ljava/lang/String;)Lorg/compiere/model/PO;` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.PO` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | BOUND-MATCH | required | 8 / 0 |
| `org.compiere.model.PO` | `<init>(Ljava/util/Properties;ILjava/lang/String;Ljava/sql/ResultSet;[Ljava/lang/String;)V` | BOUND-MATCH | required | 110 / 0 |
| `org.compiere.model.PO` | `<init>(Ljava/util/Properties;ILjava/lang/String;[Ljava/lang/String;)V` | BOUND-MATCH | required | 78 / 0 |
| `org.compiere.model.PO` | `<init>(Ljava/util/Properties;Ljava/sql/ResultSet;Ljava/lang/String;)V` | BOUND-MATCH | required | 24 / 0 |
| `org.compiere.model.PO` | `checkRecordIDCrossTenant()V` | BOUND-MATCH | required | 3 / 0 |
| `org.compiere.model.PO` | `doInsert(Z)Z` | BOUND-MATCH | required | 25 / 0 |
| `org.compiere.model.PO` | `load(ILjava/lang/String;[Ljava/lang/String;)V` | BOUND-MATCH | required | 78 / 0 |
| `org.compiere.model.PO` | `load(Ljava/lang/String;[Ljava/lang/String;)Z` | BOUND-MATCH | required | 145 / 0 |
| `org.compiere.model.PO` | `load(Ljava/sql/ResultSet;)Z` | BOUND-MATCH | required | 169 / 0 |
| `org.compiere.model.PO` | `loadColumn(Ljava/sql/ResultSet;I)Z` | BOUND-MATCH | required | 169 / 81 |
| `org.compiere.model.PO` | `loadPO(Ljava/lang/String;Ljava/lang/String;[Ljava/lang/String;)Z` | BOUND-MATCH | required | 145 / 0 |
| `org.compiere.model.PO` | `save()Z` | BOUND-MATCH | required | 62 / 0 |
| `org.compiere.model.PO` | `saveEx()V` | BOUND-MATCH | required | 47 / 0 |
| `org.compiere.model.PO` | `saveEx(Ljava/lang/String;)V` | BOUND-MATCH | required | 4 / 0 |
| `org.compiere.model.PO` | `saveFinish(ZZ)Z` | BOUND-MATCH | required | 15 / 0 |
| `org.compiere.model.PO` | `saveNew()Z` | BOUND-MATCH | required | 40 / 0 |
| `org.compiere.model.POInfo` | `<init>(Ljava/util/Properties;IZLjava/lang/String;)V` | UNBOUND | not required | 8 / 0 |
| `org.compiere.model.POInfo` | `getPOInfo(Ljava/util/Properties;ILjava/lang/String;)Lorg/compiere/model/POInfo;` | UNBOUND | not required | 8 / 0 |
| `org.compiere.model.POInfo` | `loadInfo(ZLjava/lang/String;)V` | UNBOUND | not required | 8 / 0 |
| `org.compiere.model.POInfoColumn` | `<init>(ILjava/lang/String;Ljava/lang/String;IZZLjava/lang/String;Ljava/lang/String;Ljava/lang/String;ZZILjava/lang/String;ILjava/lang/String;Ljava/lang/String;ZZZZ)V` | UNBOUND | not required | 8 / 8 |
| `org.compiere.model.Query` | `getPO(Ljava/sql/ResultSet;)Lorg/compiere/model/PO;` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.Query` | `list()Ljava/util/List;` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.X_C_BP_Group` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.X_C_BP_Group` | `initPO(Ljava/util/Properties;)Lorg/compiere/model/POInfo;` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.X_C_DocType` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.X_C_DocType` | `initPO(Ljava/util/Properties;)Lorg/compiere/model/POInfo;` | UNBOUND | not required | 1 / 0 |
| `org.compiere.model.X_C_Invoice` | `<init>(Ljava/util/Properties;ILjava/lang/String;[Ljava/lang/String;)V` | UNBOUND | not required | 74 / 0 |
| `org.compiere.model.X_C_Invoice` | `<init>(Ljava/util/Properties;Ljava/sql/ResultSet;Ljava/lang/String;)V` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.X_C_Payment` | `<init>(Ljava/util/Properties;ILjava/lang/String;)V` | UNBOUND | not required | 3 / 0 |
| `org.compiere.model.X_C_Payment` | `initPO(Ljava/util/Properties;)Lorg/compiere/model/POInfo;` | UNBOUND | not required | 3 / 0 |
| `org.compiere.model.X_M_InventoryLine` | `<init>(Ljava/util/Properties;ILjava/lang/String;[Ljava/lang/String;)V` | UNBOUND | not required | 4 / 0 |
| `org.compiere.model.X_M_InventoryLine` | `<init>(Ljava/util/Properties;Ljava/sql/ResultSet;Ljava/lang/String;)V` | UNBOUND | not required | 12 / 0 |
| `org.compiere.model.credit.CreditManagerPayment` | `checkCreditStatus(Ljava/lang/String;)Lorg/adempiere/base/CreditStatus;` | UNBOUND | not required | 6 / 0 |
| `org.compiere.process.DocumentEngine` | `completeIt()Ljava/lang/String;` | UNBOUND | not required | 12 / 0 |
| `org.compiere.process.DocumentEngine` | `postImmediate(Ljava/util/Properties;IIIZLjava/lang/String;)Ljava/lang/String;` | UNBOUND | not required | 137 / 0 |
| `org.compiere.process.DocumentEngine` | `postIt()Z` | UNBOUND | not required | 119 / 0 |
| `org.compiere.process.DocumentEngine` | `prepareIt()Ljava/lang/String;` | UNBOUND | not required | 6 / 0 |
| `org.compiere.process.DocumentEngine` | `processIt(Ljava/lang/String;)Z` | UNBOUND | not required | 215 / 0 |
| `org.compiere.process.DocumentEngine` | `processIt(Ljava/lang/String;Ljava/lang/String;)Z` | UNBOUND | not required | 215 / 0 |
| `org.compiere.process.DocumentEngine` | `reverseCorrectIt()Z` | UNBOUND | not required | 60 / 0 |
| `org.compiere.process.ServerProcessCtl` | `process(Lorg/compiere/process/ProcessInfo;Lorg/compiere/util/Trx;)Lorg/compiere/process/ServerProcessCtl;` | UNBOUND | not required | 187 / 0 |
| `org.compiere.process.ServerProcessCtl` | `process(Lorg/compiere/process/ProcessInfo;Lorg/compiere/util/Trx;Z)Lorg/compiere/process/ServerProcessCtl;` | UNBOUND | not required | 187 / 0 |
| `org.compiere.process.ServerProcessCtl` | `run()V` | UNBOUND | not required | 187 / 0 |
| `org.compiere.process.ServerProcessCtl` | `startWorkflow(I)Z` | UNBOUND | not required | 187 / 0 |
| `org.compiere.util.DB` | `executeUpdate(Ljava/lang/String;Ljava/lang/String;)I` | BOUND-MATCH | required | 34 / 0 |
| `org.compiere.wf.MWFActivity` | `getPO(Lorg/compiere/util/Trx;)Lorg/compiere/model/PO;` | UNBOUND | not required | 16 / 0 |
| `org.compiere.wf.MWFActivity` | `getPO_AD_Client_ID()I` | UNBOUND | not required | 16 / 0 |
| `org.compiere.wf.MWFActivity` | `performWork(Lorg/compiere/util/Trx;)Z` | UNBOUND | not required | 167 / 0 |
| `org.compiere.wf.MWFActivity` | `run()V` | UNBOUND | not required | 471 / 0 |
| `org.compiere.wf.MWFActivity` | `setWFState(Ljava/lang/String;)V` | UNBOUND | not required | 304 / 0 |
| `org.compiere.wf.MWFProcess` | `<init>(Lorg/compiere/wf/MWorkflow;Lorg/compiere/process/ProcessInfo;Ljava/lang/String;)V` | UNBOUND | not required | 4 / 0 |
| `org.compiere.wf.MWFProcess` | `checkActivities(Ljava/lang/String;Lorg/compiere/model/PO;)V` | UNBOUND | not required | 304 / 0 |
| `org.compiere.wf.MWFProcess` | `setTextMsg(Lorg/compiere/model/PO;)V` | UNBOUND | not required | 4 / 0 |
| `org.compiere.wf.MWFProcess` | `startNext(Lorg/compiere/wf/MWFActivity;[Lorg/compiere/wf/MWFActivity;Lorg/compiere/model/PO;Ljava/lang/String;)Z` | UNBOUND | not required | 304 / 0 |
| `org.compiere.wf.MWFProcess` | `startWork()Z` | UNBOUND | not required | 183 / 0 |
| `org.compiere.wf.MWorkflow` | `runDocumentActionWorkflow(Lorg/compiere/model/PO;Ljava/lang/String;)Lorg/compiere/process/ProcessInfo;` | UNBOUND | not required | 187 / 0 |
| `org.compiere.wf.MWorkflow` | `start(Lorg/compiere/process/ProcessInfo;Ljava/lang/String;)Lorg/compiere/wf/MWFProcess;` | UNBOUND | not required | 187 / 0 |

### other dependency

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `com.zaxxer.hikari.pool.HikariProxyResultSet` | `getString(Ljava/lang/String;)Ljava/lang/String;` | UNBOUND | not required | 169 / 81 |
| `org.apache.felix.scr.impl.inject.methods.ActivateMethod` | `doFindMethod(Ljava/lang/Class;ZZLorg/apache/felix/scr/impl/logger/ComponentLogger;)Lorg/apache/felix/scr/impl/inject/methods/BaseMethod$MethodInfo;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.ActivateMethod` | `invoke(Ljava/lang/Object;Lorg/apache/felix/scr/impl/inject/ActivatorParameter;Lorg/apache/felix/scr/impl/inject/MethodResult;)Lorg/apache/felix/scr/impl/inject/MethodResult;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.ActivateMethod` | `invoke(Ljava/lang/Object;Lorg/apache/felix/scr/impl/inject/ScrComponentContext;ILorg/apache/felix/scr/impl/inject/MethodResult;)Lorg/apache/felix/scr/impl/inject/MethodResult;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod` | `access$400(Lorg/apache/felix/scr/impl/inject/methods/BaseMethod;Lorg/apache/felix/scr/impl/logger/ComponentLogger;)Lorg/apache/felix/scr/impl/inject/methods/BaseMethod$MethodInfo;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod` | `findMethod(Lorg/apache/felix/scr/impl/logger/ComponentLogger;)Lorg/apache/felix/scr/impl/inject/methods/BaseMethod$MethodInfo;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod` | `getMethod(Ljava/lang/Class;Ljava/lang/String;[Ljava/lang/Class;ZZLorg/apache/felix/scr/impl/logger/ComponentLogger;)Ljava/lang/reflect/Method;` | UNBOUND | not required | 4 / 4 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod` | `methodExists(Lorg/apache/felix/scr/impl/logger/ComponentLogger;)Z` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod$NotResolved` | `methodExists(Lorg/apache/felix/scr/impl/inject/methods/BaseMethod;Lorg/apache/felix/scr/impl/logger/ComponentLogger;)Z` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.inject.methods.BaseMethod$NotResolved` | `resolve(Lorg/apache/felix/scr/impl/inject/methods/BaseMethod;Lorg/apache/felix/scr/impl/logger/ComponentLogger;)V` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.manager.SingleComponentManager` | `createComponent(Lorg/apache/felix/scr/impl/manager/ComponentContextImpl;)Z` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.manager.SingleComponentManager` | `createImplementationObject(Lorg/osgi/framework/Bundle;Lorg/apache/felix/scr/impl/manager/SingleComponentManager$SetImplementationObject;Lorg/apache/felix/scr/impl/manager/ComponentContextImpl;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.manager.SingleComponentManager` | `getService(Lorg/apache/felix/scr/impl/manager/ComponentContextImpl;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.manager.SingleComponentManager` | `getService(Lorg/osgi/framework/Bundle;Lorg/osgi/framework/ServiceRegistration;)Ljava/lang/Object;` | UNBOUND | not required | 4 / 0 |
| `org.apache.felix.scr.impl.manager.SingleComponentManager` | `getServiceInternal(Lorg/osgi/framework/ServiceRegistration;)Z` | UNBOUND | not required | 4 / 0 |
| `org.postgresql.jdbc.PgResultSet` | `findColumn(Ljava/lang/String;)I` | UNBOUND | not required | 88 / 0 |
| `org.postgresql.jdbc.PgResultSet` | `getString(Ljava/lang/String;)Ljava/lang/String;` | UNBOUND | not required | 88 / 0 |
| `org.postgresql.util.GT` | `<clinit>()V` | UNBOUND | not required | 7 / 0 |
| `org.postgresql.util.GT` | `<init>()V` | UNBOUND | not required | 7 / 1 |

### support

| Class | Method and JVM signature | Binding | r10 check | Stack / catch count |
|---|---|---|---|---|
| `org.idempiere.test.JourneySupport` | `postOnce(Lorg/compiere/model/PO;[Lorg/compiere/model/MAcctSchema;)V` | BOUND-MATCH | required | 22 / 0 |
| `org.idempiere.test.JourneySupport` | `transaction(Ljava/lang/String;Lorg/idempiere/test/JourneySupport$TransactionBody;)Ljava/lang/Object;` | BOUND-MATCH | required | 3 / 2 |

