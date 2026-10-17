"""Read-only DISPLAY record audit for the pinned F0 provider layouts."""
import re


def layout(lines, root_name):
    text = "\n".join(lines)
    declarations = []
    pattern = r"(?m)^\s*(\d\d)\s+([A-Z][A-Z0-9-]*)(.*?)(?=^\s*\d\d\s+|\Z)"
    for match in re.finditer(pattern, text, re.S | re.M):
        level, name, body = int(match[1]), match[2], match[3]
        if level == 88:
            continue
        if level == 1 and declarations:
            break
        if not declarations and name != root_name:
            continue
        if re.search(r"\b(OCCURS|COMP|BINARY|SEPARATE)\b", body):
            raise ValueError("Unsupported storage clause in F0 record")
        pic = re.search(r"\bPIC\s+([SX9V()0-9]+)", body)
        redefine = re.search(r"\bREDEFINES\s+([A-Z0-9-]+)", body)
        declarations.append(dict(level=level, name=name, pic=pic[1] if pic else None,
                                 redefine=redefine[1] if redefine else None, children=[]))
    if not declarations:
        raise ValueError("Missing record")
    stack = []
    for item in declarations:
        while stack and stack[-1]['level'] >= item['level']:
            stack.pop()
        if stack:
            stack[-1]['children'].append(item)
        stack.append(item)
    fields = {}

    def size_pic(pic):
        return sum(int(count or 1) for char, count in re.findall(r"([SX9V])(?:\((\d+)\))?", pic) if char in 'X9')

    def visit(item, offset):
        if item['pic']:
            size = size_pic(item['pic'])
        else:
            end, siblings = offset, {}
            for child in item['children']:
                at = siblings[child['redefine']] if child['redefine'] else end
                child_size = visit(child, at)
                siblings[child['name']] = at
                end = max(end, at + child_size)
            size = end - offset
        if item['name'] != 'FILLER':
            if item['name'] in fields:
                raise ValueError("Ambiguous field name in F0 record")
            fields[item['name']] = dict(offset=offset, size=size, picture=item['pic'])
        return size

    total = visit(declarations[0], 0)
    return total, fields
