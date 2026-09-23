import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'app')]
from store import Store, REPORT_NAMES, csv_bytes, read_trades, trade_payload, compare_trades
from package_public import package


def sample(**changes):
    row = dict(trade_id='EXAMPLE-001', date='2026-04-01', ticker='EXAMPLE ETF',
               event_type='buy', quantity_delta=10, amount_jpy=1000,
               amount_basis='actual', pair_id='', notes='', status='confirmed')
    row.update(changes)
    return row


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_and_partial_import(self):
        self.assertIsNone(self.store.report())
        with self.assertRaisesRegex(ValueError, '9'):
            self.store.import_reports({REPORT_NAMES[0]: b'invalid'})
        self.assertIsNone(self.store.report())

    def test_failure_preserves_state_and_previous_report(self):
        previous = self.store.state()
        previous['run'] = 'previous'
        folder = self.store.root / 'runs' / 'previous'
        folder.mkdir(parents=True)
        (folder / 'report.html').write_text('previous successful output')
        self.store.save(previous)
        with patch('store.build', side_effect=ValueError('invalid workbook')):
            with self.assertRaises(ValueError):
                self.store.import_reports({n: b'invalid' for n in REPORT_NAMES})
        self.assertEqual(self.store.report().read_text(), 'previous successful output')
        self.assertEqual(self.store.state(), previous)
        self.assertEqual(len(list((self.store.root / 'runs').iterdir())), 1)

    def test_trade_upsert_void_and_pending(self):
        self.store.import_trades(csv_bytes([sample()]))
        self.store.import_trades(csv_bytes([sample()]))
        self.assertEqual(len(self.store.state()['trades']), 1)
        self.assertEqual(len(self.store.state()['notices']), 1)
        self.store.import_trades(csv_bytes([sample(status='void')]))
        self.assertEqual(trade_payload(self.store.state()['trades'])['rows'], [])
        self.store.import_trades(csv_bytes([sample(trade_id='EXAMPLE-002', status='pending')]))
        self.assertEqual(len(self.store.state()['trades']), 2)
        self.assertEqual(trade_payload(self.store.state()['trades'])['rows'], [])

    def test_split_not_trade_amount_and_sign_validation(self):
        rows = read_trades(csv_bytes([sample(event_type='split', amount_jpy='')]))
        self.assertIsNone(trade_payload(rows)['rows'][0]['estimate'])
        with self.assertRaises(ValueError):
            read_trades(csv_bytes([sample(amount_jpy=-1)]))
        with self.assertRaises(ValueError):
            read_trades(csv_bytes([sample(), sample()]))

    def test_package_is_explicit_source_only(self):
        destination = Path(self.temp.name) / 'source.zip'
        package(destination)
        with ZipFile(destination) as archive:
            names = archive.namelist()
            self.assertFalse(any('/data/' in n or n.endswith('.xlsx') for n in names))
            self.assertFalse(any(n.endswith('.csv') for n in names))
            self.assertNotIn('__PORT_DATA__', archive.read('portfolio-report-viewer/app/portal.html').decode())

    def test_comparison_detects_add_modify_cancel_and_missing(self):
        before = [sample(), sample(trade_id='EXAMPLE-002'), sample(trade_id='EXAMPLE-003')]
        after = [sample(amount_jpy=2000), sample(trade_id='EXAMPLE-002', status='void'), sample(trade_id='EXAMPLE-004')]
        result = compare_trades(before, after)
        self.assertEqual([len(result[k]) for k in ['added', 'modified', 'cancelled', 'missing']], [1, 1, 1, 1])
        self.assertFalse(result['can_calculate'])
        self.assertEqual(result['modified'][0]['fields'], ['売買金額（円）'])

    def test_check_does_not_save_or_calculate(self):
        with patch('store.read_trade_workbook', return_value=[sample()]), patch('store.build') as build:
            result = self.store.check_workbook(b'workbook')
            self.assertEqual(len(result['added']), 1)
            self.assertTrue(result['first_import'])
            self.assertFalse(self.store.state_path.exists())
            build.assert_not_called()

    def test_api_replacement_keeps_only_incoming_trade(self):
        old=sample(date='2026-09-17')
        new=sample(trade_id='API-example',date='2026-09-16',amount_jpy=950,_detection_id='detected')
        result=compare_trades([old],[new])
        self.assertEqual(len(result['replaced']),1)
        self.assertEqual(result['added'],[])
        self.assertEqual(result['missing'],[])
        self.assertTrue(result['can_calculate'])
        self.assertIn('取引日',result['replaced'][0]['fields'])
        self.assertIn('売買金額（円）',result['replaced'][0]['fields'])
        state=self.store.state();state['trades']=[old];self.store.save(state)
        with patch('store.read_trade_workbook',return_value=[new]),patch.object(self.store,'import_reports') as save:
            token=self.store.check_workbook(b'xlsx')['check_token']
            self.store.calculate({},b'xlsx',token)
            self.assertEqual(save.call_args.args[1],[new])
        again=compare_trades([new],[new])
        self.assertEqual(again['unchanged'],1)
        self.assertEqual(again['replaced'],[])

    def test_ambiguous_and_different_trades_are_not_replacements(self):
        old=sample(date='2026-09-17')
        new=sample(trade_id='API-example',date='2026-09-16',_detection_id='detected')
        for rows in ([old,sample(trade_id='SECOND',date='2026-09-17')],):
            result=compare_trades(rows,[new]);self.assertEqual(result['replaced'],[]);self.assertFalse(result['can_calculate'])
        for delta in (11,-10):
            result=compare_trades([old],[dict(new,quantity_delta=delta)])
            self.assertEqual(result['replaced'],[])
        result=compare_trades([old],[new,dict(new,trade_id='API-other')])
        self.assertEqual(result['replaced'],[])

    def test_calculation_requires_current_comparison_and_complete_pack(self):
        with patch('store.read_trade_workbook', return_value=[sample()]):
            check = self.store.check_workbook(b'workbook')
            with self.assertRaises(ValueError):
                self.store.calculate({}, b'workbook', '')
            with self.assertRaises(ValueError):
                self.store.calculate({}, b'workbook', check['check_token'])
            state = self.store.state()
            state['trades'] = [sample(amount_jpy=1200)]
            self.store.save(state)
            with self.assertRaisesRegex(ValueError, 'もう一度'):
                self.store.calculate({}, b'workbook', check['check_token'])


if __name__ == '__main__':
    unittest.main()
