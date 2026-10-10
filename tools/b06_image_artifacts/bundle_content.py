"""B06 selection policy adapter; historical byte-map schema is unchanged."""
from lightyear_evidence.content import content_view, safe, stream_hash, require
POLICY='b06-bundle-content-view/1'
EXCLUSIONS={
 'target/work':'Tycho test workspace, runtime installation and mutable OSGi state',
 'target/surefire-reports':'Test reports written by the fork',
 'target/surefire':'Surefire transient test execution output',
 'target/test-runtime':'Tycho generated test runtime',
 'target/configuration':'Generated test OSGi configuration',
 'target/surefire.properties':'Tycho per-run launch properties; retained and bound separately',
}
LIMIT=1024*1024*1024

def excluded(name):
 from lightyear_evidence.content import excluded as select
 return select(name, EXCLUSIONS)

def bundle_content_view(source,*,kind):
 return content_view(source,kind=kind,policy=POLICY,exclusions=EXCLUSIONS,
                     required_entries=('META-INF/MANIFEST.MF',),limit=LIMIT,validate_original_names=False)
