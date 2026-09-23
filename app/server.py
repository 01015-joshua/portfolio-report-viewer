"""Loopback-only file import server; deliberately does not serve the project directory."""
import argparse
import json
import secrets
import re
import threading
import webbrowser
from datetime import datetime
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from store import APP, REPORT_NAMES, Store, csv_bytes
from trade_review import check_api


def serve(data, port=8777, open_browser=True):
    store = Store(data)
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, payload, content_type='application/json; charset=utf-8', status=200, download=None):
            if not isinstance(payload, bytes):
                payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            if download:
                self.send_header('Content-Disposition', f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(payload)

        def local_request(self):
            expected = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != expected:
                self.send({'error': '127.0.0.1からローカルページを開いてください。'}, status=403)
                return False
            return True

        def do_GET(self):
            if not self.local_request():
                return
            path = urlsplit(self.path).path
            if path == '/':
                self.send((APP / 'portal.html').read_bytes(), 'text/html; charset=utf-8')
            elif path == '/api/status':
                state = store.state()
                settings=store.root/'api_settings.json'
                self.send(dict(required=REPORT_NAMES, ready=bool(state['run']), start=state['start'], end=state['end'],
                    updated=state.get('updated'), token=token, workflow='api-ledger-replacements-v5',
                    history=store.history(), settings={'end_date':json.loads(settings.read_text(encoding='utf-8')).get('end_date')} if settings.exists() else {},
                    trade_count=len(state['trades']), confirmed_count=sum(r['status'] == 'confirmed' for r in state['trades'])))
            elif re.fullmatch(r'/(?:history|download)/[a-f0-9]{32}\.html',path):
                run=path.rsplit('/',1)[1][:-5]
                report=store.saved_report(run)
                if report:
                    stamp=datetime.fromtimestamp(report.stat().st_mtime).strftime('%Y%m%d-%H%M%S')
                    self.send(report.read_bytes(),'text/html; charset=utf-8',download='portfolio-report-'+stamp+'-'+run[:8]+'.html' if path.startswith('/download/') else None)
                else:self.send({'error':'保存済みレポートがありません。'},status=404)
            elif re.fullmatch(r'/reviews/[a-f0-9]{32}\.xlsx',path):
                review=store.root/'reviews'/path.rsplit('/',1)[1]
                if review.is_file():self.send(review.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',download='trade-ledger-to-complete.xlsx')
                else:self.send({'error':'確認用台帳がありません。'},status=404)
            elif path == '/report' and store.report():
                self.send(store.report().read_bytes(), 'text/html; charset=utf-8')
            elif path == '/templates/trades.csv':
                self.send(csv_bytes([]), 'text/csv; charset=utf-8', download='trade_template.csv')
            elif path == '/api/trades.csv':
                self.send(csv_bytes(store.state()['trades']), 'text/csv; charset=utf-8', download='trade_ledger.csv')
            else:
                self.send({'error': 'レポートは未生成、または指定のページが見つかりません。'}, status=404)

        def do_POST(self):
            if not self.local_request():
                return
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if self.headers.get('Origin') != origin or self.headers.get('X-Local-Token') != token:
                self.send({'error': 'ローカルの読み込み画面から操作してください。'}, status=403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 150 * 1024 * 1024:
                    raise ValueError('ファイルの合計サイズは150 MB以下にしてください。')
                body = self.rfile.read(length)
                path = urlsplit(self.path).path
                with lock:
                    if path == '/api/read':
                        store.mark_read()
                    else:
                        content_type = self.headers.get('Content-Type', '')
                        if not content_type.startswith('multipart/form-data;'):
                            raise ValueError('ファイル選択ボタンから読み込んでください。')
                        message = BytesParser(policy=policy.default).parsebytes(
                            ('Content-Type: ' + content_type + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + body)
                        files = {}
                        ledger = None
                        check_token = ''
                        options = {}
                        for part in message.iter_parts():
                            filename = part.get_filename()
                            field = part.get_param('name', header='content-disposition')
                            if not filename:
                                if field in ('portfolio','end_date'):options[field]=part.get_content().strip()
                                if field == 'check_token':
                                    check_token = part.get_content().strip()
                                continue
                            if field == 'ledger':
                                if ledger is not None or not filename.lower().endswith('.xlsx'):
                                    raise ValueError('売買台帳はExcel（.xlsx）を1ファイル選択してください。')
                                ledger = part.get_payload(decode=True)
                                continue
                            if filename in files:
                                raise ValueError('ファイル名が重複しています：' + filename)
                            files[filename] = part.get_payload(decode=True)
                        if path == '/api/check-trades':
                            if ledger is None:
                                raise ValueError('売買台帳のExcelを選択してください。')
                            self.send(dict(ok=True, **check_api(store,ledger,options.get('portfolio',''),options.get('end_date',''))))
                            return
                        elif path == '/api/calculate':
                            if ledger is None:
                                raise ValueError('売買台帳のExcelを選択してください。')
                            audit_path=store.root/'api_check.json'
                            audit=json.loads(audit_path.read_text(encoding='utf-8')) if audit_path.exists() else {}
                            if audit.get('token')!=check_token or not audit.get('can_calculate'):
                                raise ValueError('APIの確認と候補行の補完を完了してください。')
                            store.calculate(files, ledger, check_token, checked_until=audit['end'])
                        else:
                            self.send({'error': '指定のページが見つかりません。'}, status=404)
                            return
                self.send({'ok': True})
            except Exception as exc:
                self.send({'error': str(exc) or type(exc).__name__}, status=400)

    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://127.0.0.1:{httpd.server_port}/'
    print('Local report viewer: ' + url, flush=True)
    if open_browser:
        webbrowser.open(url)
    httpd.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=APP.parent / 'data')
    parser.add_argument('--port', type=int, default=8777)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    serve(args.data, args.port, not args.no_browser)
