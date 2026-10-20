"""Compile COACTUP's rendering, protection and cursor paragraphs from source."""
import re
from .screen_update import paragraph
from .screen_edits import Parser
from .web_bindings import active

NAMES=('3200-SETUP-SCREEN-VARS','3201-SHOW-INITIAL-VALUES','3202-SHOW-ORIGINAL-VALUES',
       '3203-SHOW-UPDATED-VALUES','3250-SETUP-INFOMSG','3300-SETUP-SCREEN-ATTRS',
       '3310-PROTECT-ALL-ATTRS','3320-UNPROTECT-FEW-ATTRS','3390-SETUP-INFOMSG-ATTRS')
SYMBOLS={'DFHBMFSE','DFHBMPRF','DFHBMASB','DFHBMDAR','DFHRED','DFHDFCOL'}


def build(raw,source,screen,attribute_copy,performs):
    paragraphs={};expanded={};bodies={}
    pattern=re.compile(r'COPY\s+CSSETATY\s+REPLACING\s+==\(TESTVAR1\)==\s+BY\s+==([A-Z0-9-]+)==\s+==\(SCRNVAR2\)==\s+BY\s+==([A-Z0-9]+)==\s+==\(MAPNAME3\)==\s+BY\s+==([A-Z0-9]+)==\s*[.]')
    for name in NAMES:
        code,lines=paragraph(raw,source,name);pieces=[];locations=[];previous=0
        for index,m in enumerate(pattern.finditer(code)):
            label='ATTR-'+str(index+1)
            copy_text,copy_lines=active(attribute_copy[1],attribute_copy[0])
            replacements={'(TESTVAR1)':m[1],'(SCRNVAR2)':m[2],'(MAPNAME3)':m[3]}
            # Keep COPY member physical locations as replacement changes lengths.
            out='';mapping=[];at=0
            for token in re.finditer(r'\(TESTVAR1\)|\(SCRNVAR2\)|\(MAPNAME3\)',copy_text):
                out+=copy_text[at:token.start()];mapping.extend(copy_lines[at:token.start()])
                value=replacements[token[0]];out+=value;mapping.extend([copy_lines[token.start()]]*len(value));at=token.end()
            out+=copy_text[at:];mapping.extend(copy_lines[at:]);expanded[label]=(out,mapping,attribute_copy[0])
            pieces.append(code[previous:m.start()]);locations.extend(lines[previous:m.start()])
            replacement='PERFORM '+label+' THRU '+label+'-EXIT .'
            pieces.append(replacement);locations.extend([lines[m.start()]]*len(replacement));previous=m.end()
        pieces.append(code[previous:]);locations.extend(lines[previous:]);bodies[name]=(''.join(pieces),locations,source)
    allowed=set(performs)|set(NAMES)|set(expanded)
    for name,(code,lines,path) in {**bodies,**expanded}.items():paragraphs[name]=Parser(code,lines,path,name,allowed).parse()
    fields={}
    for f in screen['fields']:
        name=f['name']
        if not name:continue
        for suffix,length,kind in [('I',f['length'],'text'),('O',f['length'],'text'),('A',12,'text'),('C',12,'text'),('L',4,'number')]:
            fields[name+suffix]=dict(type=kind,length=length,value=None,ancestors=[],body='',source='generated BMS ABI',line=f.get('line',1),screen_field=name,screen_part=suffix)
    for symbol in SYMBOLS:
        fields[symbol]=dict(type='text',length=len(symbol),value="'"+symbol+"'",ancestors=[],body='',source='CICS BMS ABI',line=1)
    code,lines=active(raw,source)
    pic=re.search(r'WS-EDIT-CURRENCY-9-2-F\s+PIC\s+([+Z,9.]+)[.]',code)
    if not pic:raise ValueError('source currency edit picture missing')
    fields['WS-EDIT-CURRENCY-9-2-F']=dict(type='edited',length=len(pic[1]),value=None,ancestors=[],body='',picture=pic[1],source=source,line=lines[pic.start()])
    return paragraphs,fields
