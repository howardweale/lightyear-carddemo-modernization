"""Deterministic J1 posting controls; original source and J1 judge never edited."""
import hashlib
from lightyear_calibration.contracts import seal
from tools.ms94_b06_admission import check

CONTROLS = ('prior-post', 'prior-lock', 'support-origin', 'outside-origin', 'wrong-document', 'genuine-equipment-fault')


def once(source, old, new):
    check(source.count(old) == 1, 'posting-control-source-anchor')
    return source.replace(old, new, 1)


def j1(source_bytes, control):
    check(control in CONTROLS, 'posting-control-unknown')
    source = source_bytes.decode('utf-8')
    call = '        JourneySupport.postOnce(model, schemas);'
    support = '    public static void postOnce(org.compiere.model.PO model, org.compiere.model.MAcctSchema[] schemas) {'
    if control == 'prior-post':
        source = once(source, call, '        commit();\n'
            '        assertNull(org.compiere.acct.DocManager.postDocument(schemas, model.get_Table_ID(), model.get_ID(), false, false, model.get_TrxName()));\n'
            '        commit();\n' + call)
    elif control == 'prior-lock':
        source = once(source, call, '        commit();\n'
            '        if (!model.get_ValueAsBoolean("Posted")) assertTrue(model.lock());\n' + call)
    elif control == 'support-origin':
        source = once(source, support, support + '\n        if (model != null) throw new IllegalStateException("Support control");')
    elif control == 'outside-origin':
        source = once(source, call, '        commit();\n'
            '        if (!model.get_ValueAsBoolean("Posted")) B06OutsideControl.lock(model);\n' + call)
        source += '\nfinal class B06OutsideControl { static void lock(org.compiere.model.PO model) { if (!model.lock()) throw new IllegalStateException("Outside control"); } }\n'
    elif control == 'wrong-document':
        source = once(source, '    private final Properties evidence = new Properties();',
            '    private final Properties evidence = new Properties();\n    private org.compiere.model.PO b06Previous;')
        source = once(source, call, '        commit();\n'
            '        if (b06Previous != null) { assertTrue(b06Previous.lock()); JourneySupport.b06Fail = true; }\n' +
            call + '\n        b06Previous = model;')
        source = once(source, 'final class JourneySupport {', 'final class JourneySupport {\n    static boolean b06Fail;')
        source = once(source, support, support + '\n        if (b06Fail) throw new IllegalStateException("Different-document support control");')
    # Genuine equipment failure has an unchanged source and a host-owned hook.
    raw = source.encode('utf-8')
    return raw, seal({'artifact_type': 'ms94-b06-control-source/1', 'control': control, 'journey': 'J1',
        'base_sha256': hashlib.sha256(source_bytes).hexdigest(), 'source_sha256': hashlib.sha256(raw).hexdigest(),
        'mutator_sha256': hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest(),
        'compiled': False, 'native_qualified': False, 'J1_predicates_changed': False})
