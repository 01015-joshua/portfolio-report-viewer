"""Append API candidates to a copy of the uploaded workbook; preserve existing cells."""
import io
import posixpath
import uuid
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED
from store import TRADE_FIELDS, read_trade_workbook, dump
from api_reconcile import load_positions, reconcile, prefill_candidates

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
ET.register_namespace('', NS)
ET.register_namespace('r', REL)
def q(name): return '{'+NS+'}'+name

def append_candidates(payload, candidates):
    with ZipFile(io.BytesIO(payload)) as archive:
        entries={name:archive.read(name) for name in archive.namelist()}
    book=ET.fromstring(entries['xl/workbook.xml'])
    sheet=next(s for s in book.find(q('sheets')) if s.get('name')=='売買台帳')
    relationships=ET.fromstring(entries['xl/_rels/workbook.xml.rels'])
    target=next(r.get('Target') for r in relationships if r.get('Id')==sheet.get('{'+REL+'}id'))
    path=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
    root=ET.fromstring(entries[path]); data=root.find(q('sheetData'))
    # The maintained template has a header in row 7. Locate it through actual cell values.
    shared=[]
    if 'xl/sharedStrings.xml' in entries:
        shared=[''.join(e.itertext()) for e in ET.fromstring(entries['xl/sharedStrings.xml'])]
    def value(c):
        v=c.find(q('v'))
        if c.get('t')=='s' and v is not None:return shared[int(v.text)]
        return ''.join(c.itertext())
    header=next(r for r in data if any(value(c) in ('取引ID','trade_id') for c in r))
    header_n=int(header.get('r'))
    existing=[r for r in data if int(r.get('r'))>header_n and any(c.get('r','').startswith('A') and value(c) for c in r)]
    last=max([header_n]+[int(r.get('r')) for r in existing])
    prototype=existing[-1] if existing else header
    styles={''.join(filter(str.isalpha,c.get('r'))):c.get('s') for c in prototype}
    def setcell(row,col,val,style=None):
        ref=col+row.get('r')
        for c in list(row):
            if c.get('r')==ref:row.remove(c)
        c=ET.SubElement(row,q('c'),{'r':ref})
        if style is not None:c.set('s',style)
        if isinstance(val,(int,float)):
            ET.SubElement(c,q('v')).text=str(val)
        else:
            c.set('t','inlineStr');ET.SubElement(ET.SubElement(c,q('is')),q('t')).text=str(val or '')
    extras=['検出ID','検出開始日','検出終了日','要確認事項']
    header_style=next(iter(header)).get('s')
    for col,label in zip('KLMN',extras):setcell(header,col,label,header_style)
    for candidate in candidates:
        row=next((r for r in existing if any(c.get('r','').startswith('A') and value(c)==candidate['trade_id'] for c in r)),None) if candidate.get('_existing') else None
        if row is not None:
            setcell(row,'J','未確認',styles.get('J'))
            for col,key in zip('KLMN',('_detection_id','_detected_start','_detected_end','_required')):setcell(row,col,candidate.get(key,''),styles.get('I'))
            continue
        last+=1
        row=next((r for r in data if int(r.get('r'))==last),None)
        if row is None:row=ET.SubElement(data,q('row'),{'r':str(last)})
        values=[candidate.get(k,'') for k in TRADE_FIELDS]
        values[3]={'buy':'買付','sell':'売却'}.get(values[3],values[3])
        values[6]={'estimated':'概算','actual':'実額'}.get(values[6],values[6])
        values[9]='未確認'
        values += [candidate.get(k,'') for k in ('_detection_id','_detected_start','_detected_end','_required')]
        for col,val in zip('ABCDEFGHIJKLMN',values):setcell(row,col,val,styles.get(col,styles.get('I')))
    data[:]=sorted(data,key=lambda r:int(r.get('r')))
    dimension=root.find(q('dimension'))
    if dimension is not None:dimension.set('ref',f'A1:N{max(last,int(data[-1].get("r")))}')
    cols=root.find(q('cols'))
    if cols is not None and not any(int(c.get('max','0')) >= 14 for c in cols):
        ET.SubElement(cols,q('col'),{'min':'11','max':'11','width':'22','customWidth':'1','hidden':'1'})
        ET.SubElement(cols,q('col'),{'min':'12','max':'13','width':'16','customWidth':'1'})
        ET.SubElement(cols,q('col'),{'min':'14','max':'14','width':'60','customWidth':'1'})
    entries[path]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    # Extend only the ledger table; all existing guide sheets and validations stay intact.
    for name,content in list(entries.items()):
        if name.startswith('xl/tables/') and name.endswith('.xml'):
            table=ET.fromstring(content)
            if table.get('name')!='TradeLedger':continue
            ref=f'A{header_n}:N{last}'
            table.set('ref',ref)
            af=table.find(q('autoFilter'))
            if af is not None:af.set('ref',ref)
            columns=table.find(q('tableColumns'))
            for i,label in enumerate(extras,11):
                if len(columns)<i:ET.SubElement(columns,q('tableColumn'),{'id':str(i),'name':label})
            columns.set('count',str(len(columns)))
            entries[name]=ET.tostring(table,encoding='utf-8',xml_declaration=True)
    output=io.BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for name,content in entries.items():archive.writestr(name,content)
    return output.getvalue()

def check_api(store, payload, portfolio, end_date):
    rows=read_trade_workbook(payload)
    result=store.check_workbook(payload)
    snapshots=load_positions(store.root,portfolio,end_date)
    api=reconcile(snapshots,rows,portfolio)
    prefill_candidates(store.root,portfolio,api['candidates'])
    result['api']=api
    result['can_calculate']=result['can_calculate'] and not api['candidates'] and not api['unresolved'] and not result['pending']
    store.root.joinpath('api_settings.json').write_text(dump(dict(end_date=end_date)),encoding='utf-8')
    if api['candidates']:
        review=uuid.uuid4().hex
        directory=store.root/'reviews';directory.mkdir(exist_ok=True)
        (directory/(review+'.xlsx')).write_bytes(append_candidates(payload,api['candidates']))
        result['review_url']='/reviews/'+review+'.xlsx'
    store.root.joinpath('api_check.json').write_text(dump(dict(token=result['check_token'],can_calculate=result['can_calculate'],end=end_date)),encoding='utf-8')
    return result
