"""Exact Oracle statement dispatch, without SQL*Plus literal whitespace loss.

The native dispatcher has its own boundaries; the static audit parser and its
published decision counts are deliberately unchanged.
"""
from lightyear_data.idempiere_sql import lex
from .contracts import require


def oracle_statements(source):
    require("\r" not in source, "Canonical LF source required")
    tokens = lex(source, "oracle")
    statements = []
    i = 0
    while i < len(tokens):
        start = i
        first = tokens[i]
        if first.kind == 'symbol' and first.value == ';':
            i += 1
            continue
        line_end = source.find("\n", first.start)
        if line_end < 0:
            line_end = len(source)
        if first.kind == 'word' and first.value == 'set':
            while i < len(tokens) and tokens[i].start < line_end:
                i += 1
            settings = [t.value for t in tokens[start:i]]
            if settings[-1:] == [';']:
                settings = settings[:-1]
            require(settings in
                    (["set", "define", "off"], ["set", "sqlblanklines", "on"],
                     ["set", "echo", "off"], ["set", "serveroutput", "on"], ["set", "serveroutput", "on", "size", "1000000"],
                     ["set", "pagesize", "999"], ["set", "linesize", "32000"]),
                    'Unsupported native client command')
            continue
        require(first.value not in {"prompt", "spool", "whenever", "exit", "quit", "@", "\\", "/"},
                'Unsupported native client command')
        procedural = first.kind == 'word' and first.value in {'begin', 'declare'}
        if first.kind == 'word' and first.value == 'create':
            j = i + 1
            if [t.value for t in tokens[j:j+2]] == ['or', 'replace']:
                j += 2
            if j < len(tokens) and tokens[j].value in {'editionable', 'noneditionable'}:
                j += 1
            procedural = j < len(tokens) and tokens[j].kind == 'word' and tokens[j].value in {'function', 'procedure', 'trigger', 'package', 'type'}
        while i < len(tokens):
            token = tokens[i]
            if procedural:
                endline = source.find('\n', token.end)
                if endline < 0:
                    endline = len(source)
                terminator = (token.kind == 'symbol' and token.value == '/' and
                    not source[source.rfind('\n', 0, token.start)+1:token.start].strip() and
                    not source[token.end:endline].strip())
            else:
                terminator = token.kind == 'symbol' and token.value == ';'
            if terminator:
                break
            i += 1
        require(i < len(tokens), 'Ambiguous or unterminated SQL boundary')
        statement = source[first.start:tokens[i].start].rstrip()
        require(bool(statement), 'Empty statement')
        statements.append(statement)
        i += 1
    return statements
