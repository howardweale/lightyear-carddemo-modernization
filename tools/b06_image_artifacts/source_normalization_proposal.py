"""DRAFT for operator approval only. Not imported by capture, producer or replay.

Two exact entries in an enumerated source-bundle set. No class/resource or
active identity change. Tests and offline triage are the only callers.
"""
import re
from datetime import datetime
from .application_identity import manifest,base_version

SOURCE_BUNDLES = frozenset(['org.adempiere.base.callout.source', 'org.adempiere.base.process.source', 'org.adempiere.base.source', 'org.adempiere.install.source', 'org.adempiere.payment.processor.source', 'org.adempiere.pipo.source', 'org.adempiere.plugin.utils.source', 'org.adempiere.replication.source', 'org.adempiere.report.jasper.source', 'org.adempiere.server.source', 'org.adempiere.ui.source', 'org.adempiere.ui.zk.source', 'org.apache.ecs.source', 'org.compiere.db.oracle.provider.source', 'org.compiere.db.postgresql.provider.source', 'org.idempiere.hazelcast.service.source', 'org.idempiere.tablepartition.source', 'org.idempiere.webservices.resources.source', 'org.idempiere.webservices.source', 'org.idempiere.zk.billboard.source', 'org.idempiere.zk.extra.source'])


def normalize_proposed(symbolic_name,entry,raw):
 if symbolic_name not in SOURCE_BUNDLES:raise ValueError('proposal-bundle-not-enumerated')
 if entry=='OSGI-INF/l10n/bundle-src.properties':
  lines=raw.splitlines(keepends=True)
  if len(lines)<2 or lines[0].rstrip(b'\r\n')!=b'#Source Bundle Localization':raise ValueError('proposal-localization-header')
  value=lines[1].rstrip(b'\r\n')
  if not re.fullmatch(rb'#[A-Z][a-z]{2} [A-Z][a-z]{2} [0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC [0-9]{4}',value):raise ValueError('proposal-timestamp-line')
  when=datetime.strptime(value.decode('ascii'),'#%a %b %d %H:%M:%S UTC %Y')
  if when.strftime('#%a %b %d %H:%M:%S UTC %Y').encode()!=value:raise ValueError('proposal-invalid-timestamp')
  lines[1]=b'#<generated UTC timestamp>'+lines[1][len(value):]
  return b''.join(lines)
 if entry!='META-INF/MANIFEST.MF':raise ValueError('proposal-entry-not-enumerated')
 normal,headers,_=manifest(raw)
 host=symbolic_name.removesuffix('.source');version=headers['bundle-version']
 expected=host+';version="'+version+'";roots:="."'
 if headers.get('eclipse-sourcebundle')!=expected:raise ValueError('proposal-host-version-or-roots')
 groups=[]
 for line in normal.splitlines(keepends=True):
  if line.startswith(b' '):groups[-1]+=line
  else:groups.append(line)
 found=0
 for i,group in enumerate(groups):
  if group.startswith(b'Eclipse-SourceBundle: '):
   end=b'\r\n' if group.endswith(b'\r\n') else b'\n' if group.endswith(b'\n') else b''
   groups[i]=('Eclipse-SourceBundle: '+host+';version="'+base_version(version)[0]+'";roots:="."').encode()+end;found+=1
 if found!=1:raise ValueError('proposal-exact-source-header')
 return b''.join(groups)
