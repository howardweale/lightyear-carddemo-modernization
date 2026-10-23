"""Strict profile scope and paired-CI mutation-count comparison for K7.

This does not grant a freeze exception. The original frozen-judge check must
continue refusing the modified main POM until post-run review.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

SERVICE = 'factory/carddemo-web/service'
GROUPS = ('map', 'phone-date', 'feedback', 'account-view')
BASE_SHA256 = '6497637db619a851c113391524ee0044da9892b2d18a85134bcc7dc183485d5f'
NS = {'m': 'http://maven.apache.org/POM/4.0.0'}


def contents(root):
    path = Path(root) / SERVICE / 'pom.xml'
    text = path.read_text(encoding='utf-8')
    sections = re.findall(r'  <profiles>.*?</profiles>\n', text, flags=re.S)
    if len(sections) != 1:
        raise ValueError('proof-profiles-section')
    base = text.replace(sections[0], '', 1)
    if sha256(base.encode()).hexdigest() != BASE_SHA256:
        raise ValueError('proof-default-build-changed')
    tree = ET.fromstring(text)
    profiles = tree.findall('m:profiles/m:profile', NS)
    if [p.findtext('m:id', namespaces=NS) for p in profiles] != ['proof-' + g for g in GROUPS]:
        raise ValueError('proof-profile-inventory')
    for profile in profiles:
        if [node.tag.rsplit('}', 1)[-1] for node in profile] != ['id', 'build']:
            raise ValueError('proof-profile-extra-configuration')
    if list((Path(root) / SERVICE).glob('*-proof.pom.xml')):
        raise ValueError('separate-proof-pom-forbidden')
    return text, base


def baseline_pom(root):
    return contents(root)[1]


def profile_pom(root, group):
    """Return a strict standalone view for the unchanged per-group validators.

CI separately compares Maven's real effective POM and actual mutation output;
this structural check does not claim to implement Maven's model builder.
"""
    if group not in GROUPS:
        raise ValueError('unknown-proof-profile')
    text, base = contents(root)
    pattern = r'<profile><id>proof-' + re.escape(group) + r'</id>(<build>.*?</build>)</profile>'
    match = re.findall(pattern, text, flags=re.S)
    if len(match) != 1:
        raise ValueError('proof-profile-build')
    build = match[0]
    # Both configurations deliberately suppress inherited configuration. The
    # complete expected plugin tree is still compared by the existing checker.
    if build.count(' combine.self="override"') != 2:
        raise ValueError('proof-profile-inheritance')
    build = build.replace(' combine.self="override"', '')
    return re.sub(r'<build>.*?</build>', lambda _: build, base, count=1, flags=re.S)


def mutation_counts(path):
    path = Path(path)
    nodes = ET.parse(path).getroot().findall('mutation')
    if not nodes:
        raise ValueError('empty-mutation-comparison')
    counts = Counter()
    for node in nodes:
        name = node.findtext('mutatedClass')
        status = node.get('status')
        if not name or not status:
            raise ValueError('incomplete-mutation-row')
        counts[(name, status)] += 1
    return [{'class': name, 'status': status, 'count': count}
            for (name, status), count in sorted(counts.items())]


def effective_build(path, checkout):
    tree = ET.parse(path).getroot()
    build = tree.find('m:build', NS)
    if build is None:
        raise ValueError('missing-effective-build')

    def canonical(node):
        value = (node.text or '').strip().replace(str(Path(checkout).resolve()), '${CHECKOUT}')
        attributes = dict(node.attrib)
        if attributes.get('combine.self') == 'override':
            del attributes['combine.self']  # Already applied by Maven's model builder.
        children = list(node)
        if node.tag.rsplit('}', 1)[-1] == 'plugins':
            children.sort(key=lambda p: (p.findtext('m:groupId', namespaces=NS) or '',
                                         p.findtext('m:artifactId', namespaces=NS) or ''))
        return [node.tag, sorted(attributes.items()), value, [canonical(child) for child in children]]

    # Includes all effective plugins, executions, versions, configuration,
    # output/source directories and resources. Only checkout location varies.
    return canonical(build)


def compare(old, new, old_effective, new_effective, old_root, new_root):
    before = mutation_counts(old); after = mutation_counts(new)
    if before != after:
        raise ValueError('mutation-counts-changed')
    if effective_build(old_effective, old_root) != effective_build(new_effective, new_root):
        raise ValueError('effective-build-changed')
    return dict(schema='k7-paired-proof/1', mutation_counts=after,
                identical_counts=True, identical_effective_build=True,
                baseline_mutations_sha256=sha256(Path(old).read_bytes()).hexdigest(),
                profile_mutations_sha256=sha256(Path(new).read_bytes()).hexdigest(),
                freeze_exception=False, merge_authorized=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old', required=True); parser.add_argument('--new', required=True)
    parser.add_argument('--old-effective', required=True); parser.add_argument('--new-effective', required=True)
    parser.add_argument('--old-root', required=True); parser.add_argument('--new-root', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = compare(args.old, args.new, args.old_effective, args.new_effective, args.old_root, args.new_root)
    output = Path(args.out); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
