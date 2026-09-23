import sys, unittest, tempfile, io
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from api_reconcile import parse_positions, reconcile, fill_proposals
from trade_review import append_candidates
from store import Store, read_trade_workbook, TRADE_HEADERS
from xml.sax.saxutils import escape

def fixture():
    cells=''.join(f'<c r="{chr(65+i)}7" t="inlineStr"><is><t>{escape(h)}</t></is></c>' for i,h in enumerate(TRADE_HEADERS))
    values=['T1','2026-04-01','TEST US Equity','買付',10,1000,'実額','','','確認済み']
    cells2=''.join(f'<c r="{chr(65+i)}8" t="inlineStr"><is><t>{escape(str(h))}</t></is></c>' for i,h in enumerate(values))
    entries={'[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/></Types>',
    'xl/workbook.xml':'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="売買台帳" sheetId="1" r:id="rId1"/></sheets></workbook>',
    'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
    'xl/worksheets/sheet1.xml':f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:J8"/><sheetData><row r="7">{cells}</row><row r="8">{cells2}</row></sheetData></worksheet>'}
    buf=io.BytesIO()
    with ZipFile(buf,'w',ZIP_DEFLATED) as z:
        for n,v in entries.items():z.writestr(n,v)
    return buf.getvalue()

class WorkflowTests(unittest.TestCase):
    def test_prefilled_proposal_is_estimated_and_unconfirmed(self):
        snapshots=[dict(date='2026-04-01',positions={'TEST US Equity':10}),dict(date='2026-04-02',positions={'TEST US Equity':0})]
        candidate=reconcile(snapshots,[],'PORT')['candidates'][0]
        fill_proposals([candidate],{'2026-04-01':{'TEST US Equity':100},'2026-04-02':{}})
        self.assertEqual(candidate['date'],'2026-04-02')
        self.assertEqual(candidate['event_type'],'sell')
        self.assertEqual(candidate['amount_jpy'],-1000)
        self.assertEqual(candidate['amount_basis'],'estimated')
        self.assertEqual(candidate['status'],'pending')
        row=next(r for r in read_trade_workbook(append_candidates(fixture(),[candidate])) if r['trade_id']==candidate['trade_id'])
        self.assertEqual(row['amount_jpy'],-1000)
        self.assertEqual(row['event_type'],'sell')
    def test_api_errors_are_not_zero_positions(self):
        text='security = "PORT" PORTFOLIO_DATA[] = { PORTFOLIO_DATA = { Security = "TEST US Equity" Position = 10 } }'
        self.assertEqual(parse_positions(text,'PORT'),{'TEST US Equity':10})
        for invalid in ('securityError',text.replace('PORT','OTHER',1),'empty'):
            with self.assertRaises(ValueError):parse_positions(invalid,'PORT')
    def test_candidate_roundtrip_and_confirmation(self):
        snapshots=[dict(date='2026-04-01',positions={'TEST US Equity':10}),dict(date='2026-04-02',positions={'TEST US Equity':15})]
        ledger=fixture();old=read_trade_workbook(ledger)
        result=reconcile(snapshots,old,'PORT');candidate=result['candidates'][0]
        self.assertEqual(candidate['quantity_delta'],5)
        self.assertEqual(candidate['date'],'');self.assertEqual(candidate['amount_jpy'],'')
        output=append_candidates(ledger,[candidate]);new=read_trade_workbook(output)
        self.assertEqual(len(new),2)
        self.assertEqual(next(r for r in new if r['trade_id']=='T1'),old[0])
        check=reconcile(snapshots,new,'PORT')
        self.assertEqual(check['candidates'],[]);self.assertEqual(len(check['unresolved']),1)
        for r in new:
            if r['status']=='pending':r.update(date='2026-04-02',event_type='buy',amount_jpy=500,amount_basis='actual',status='confirmed')
        final=reconcile(snapshots,new,'PORT')
        self.assertEqual(final['candidates'],[]);self.assertEqual(final['unresolved'],[]);self.assertEqual(final['matched'],1)
    def test_history_and_path_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);self.assertEqual(store.history(),[])
            folder=Path(tmp)/'runs'/('a'*32);folder.mkdir(parents=True);(folder/'report.html').write_text('saved')
            self.assertEqual(len(store.history()),1)
            self.assertIsNone(store.saved_report('../state.json'))
            self.assertEqual(store.saved_report('a'*32).read_text(),'saved')
    def test_date_difference_preserves_existing_row(self):
        ledger=fixture();rows=read_trade_workbook(ledger)
        snapshots=[dict(date='2026-03-31',positions={'TEST US Equity':0}),dict(date='2026-04-02',positions={'TEST US Equity':10})]
        rows[0]['date']='2026-04-03'
        result=reconcile(snapshots,rows,'PORT')
        self.assertTrue(result['candidates'][0]['_existing'])
        output=append_candidates(ledger,result['candidates'])
        self.assertEqual(len(read_trade_workbook(output)),1)
        self.assertEqual(read_trade_workbook(output)[0]['status'],'pending')

if __name__=='__main__':unittest.main()
