"""Execute deterministic Java plumbing with explicit API doubles; not native evidence."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('javac') and shutil.which('java'),'JDK required for support unit tests')
class JavaPlumbing(unittest.TestCase):
    def test_trace_posting_and_transaction_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            sources={
                'org/compiere/model/PO.java':'''package org.compiere.model;
public class PO { public boolean value; public boolean get_ValueAsBoolean(String f){return value;}
 public void load(String t){} public String get_TrxName(){return "unit";}
 public int get_Table_ID(){return 1;} public int get_ID(){return 1;} }''',
                'org/compiere/model/MAcctSchema.java':'package org.compiere.model; public class MAcctSchema {}',
                'org/compiere/acct/DocManager.java':'''package org.compiere.acct;
public class DocManager { public static int calls;
 public static String postDocument(org.compiere.model.MAcctSchema[] s,int t,int i,boolean f,boolean r,String x){
 calls++; if(r)throw new AssertionError("repost flag"); return null;} }''',
                'org/compiere/util/Trx.java':'''package org.compiere.util;
public class Trx { public static Trx latest; public boolean closed,rolled,committed;
 public static boolean commitResult=true,rollbackResult=true;
 public static String createTrxName(String n){return n;} public static Trx get(String n,boolean c){latest=new Trx();return latest;}
 public boolean commit(boolean x){committed=true;return commitResult;}
 public boolean rollback(){rolled=true;return rollbackResult;} public void close(){closed=true;} }''',
                'SupportUnitMain.java':'''import org.idempiere.test.JourneySupport;
import org.compiere.util.Trx;
public class SupportUnitMain {
 static void check(boolean v){if(!v)throw new AssertionError();}
 public static void main(String[] args) throws Exception {
  check(JourneySupport.text(null).equals("SQL-NULL"));
  check(JourneySupport.text(new java.math.BigDecimal("1000.000")).equals("1000"));
  check(JourneySupport.text(new java.math.BigDecimal("0.0000001")).equals("0.0000001"));
  java.util.Properties p=new java.util.Properties();JourneySupport.fact(p,"key",1);
  try{JourneySupport.fact(p,"key",2);throw new AssertionError();}catch(IllegalArgumentException expected){}
  JourneySupport.replaceFact(p,"key",3);check(p.size()==1&&p.getProperty("key").equals("3"));
  try{JourneySupport.replaceFact(p,"absent",3);throw new AssertionError();}catch(IllegalArgumentException expected){}
  org.compiere.model.PO model=new org.compiere.model.PO();model.value=true;
  JourneySupport.postOnce(model,new org.compiere.model.MAcctSchema[0]);check(org.compiere.acct.DocManager.calls==0);
  model.value=false;check(!JourneySupport.posted(model));
  try{JourneySupport.postOnce(model,new org.compiere.model.MAcctSchema[0]);throw new AssertionError();}catch(IllegalStateException expected){}
  check(org.compiere.acct.DocManager.calls==1);
  check(JourneySupport.transaction("success",n->"ok").equals("ok"));
  check(Trx.latest.closed&&Trx.latest.committed&&!Trx.latest.rolled);
  try{JourneySupport.transaction("failure",n->{throw new Exception("injected");});throw new AssertionError();}catch(Exception e){check(e.getMessage().equals("injected"));}
  check(Trx.latest.closed&&Trx.latest.rolled&&!Trx.latest.committed);
  Trx.commitResult=false;
  try{JourneySupport.transaction("commit-failure",n->null);throw new AssertionError();}catch(IllegalStateException expected){}
  check(Trx.latest.closed&&Trx.latest.rolled);
  Trx.rollbackResult=false;
  try{JourneySupport.transaction("rollback-failure",n->{throw new Exception();});throw new AssertionError();}catch(IllegalStateException expected){}
  check(Trx.latest.closed&&Trx.latest.rolled);
 }
}'''}
            sources['org/idempiere/test/JourneySupport.java']=(Path(__file__).resolve().parents[1]/
                'factory/idempiere/qualification/public/JourneySupport.java').read_text(encoding='utf-8')
            for name,source in sources.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(source,encoding='utf-8')
            subprocess.run(['javac','-encoding','UTF-8','-d',str(root),*(str(root/n) for n in sources)],capture_output=True,check=True,timeout=30)
            subprocess.run(['java','-cp',str(root),'SupportUnitMain'],capture_output=True,check=True,timeout=30)


if __name__=='__main__':unittest.main()
