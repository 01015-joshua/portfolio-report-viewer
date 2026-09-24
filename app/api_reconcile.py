"""Read local Bloomberg positions and reconcile quantity changes, never inferred fills."""
import hashlib
import json
import math
import re
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from store import APP, SELF_START_DATE, dump


def api_failure(process):
    output=(process.stderr or b'')+(process.stdout or b'')
    messages={
        b'BLPAPI_DLL_NOT_FOUND':'Bloomberg APIのDLLが見つかりません。C:\\blp、C:\\Program Files\\Bloomberg\\blp、C:\\Program Files (x86)\\Bloomberg\\blp の API\\Office Tools を確認してください。',
        b'BLPAPI_DLL_LOAD_FAILED':'Bloomberg APIのDLLは見つかりましたが読み込めません。依存DLL・Desktop APIの導入状態・32/64ビットの互換性を確認してください。',
        b'BLPAPI_SESSION_UNAVAILABLE':'Bloomberg Terminalに接続できません。同じPCでTerminalにログインして再実行してください。',
        b'BLPAPI_SERVICE_UNAVAILABLE':'Bloombergの参照データサービスに接続できません。Terminalの接続状態を確認してください。',
    }
    for marker,message in messages.items():
        if marker in output:return message
    return 'Bloomberg APIの取得に失敗しました。Terminalのログイン、ポートフォリオのアクセス権、API導入状況を確認してください。未取得を「取引なし」とは扱いません。'


def parse_positions(text, portfolio):
    if re.search(r'responseError|securityError|fieldException\s*=|NOT_ENTITLED|NO_AUTH', text, re.I):
        raise ValueError('Bloombergがエラーを返しました。権限・対象ポートフォリオを確認してください。')
    identity = re.search(r'\bsecurity = "([^"]+)"', text)
    if not identity or identity[1] != portfolio or 'PORTFOLIO_DATA[]' not in text:
        raise ValueError('Bloombergの応答を完全な持倉データとして確認できません。')
    result = {}
    blocks = re.findall(r'PORTFOLIO_DATA = \{([^{}]*)\}', text, re.S)
    for block in blocks:
        security = re.search(r'Security = "([^"]+)"', block)
        quantity = re.search(r'Position = ([^\s]+)', block)
        if not security or not quantity:
            raise ValueError('持倉明細に銘柄コードまたは数量がありません。')
        q = float(quantity[1])
        if not math.isfinite(q) or security[1] in result:
            raise ValueError('持倉数量が不正、または銘柄が重複しています。')
        result[security[1]] = q
    return result


def load_positions(root, portfolio, end_date):
    if not portfolio.strip() or len(portfolio) > 160:
        raise ValueError('BloombergのポートフォリオIDを入力してください。')
    begin = date.fromisoformat(SELF_START_DATE)
    end = date.fromisoformat(end_date)
    if end < begin or end >= date.today() or (end-begin).days > 370:
        raise ValueError('確認終了日は2026/3/31以降、前日までの日付を指定してください（最大370日）。')
    days = [(begin+timedelta(days=i)).isoformat() for i in range((end-begin).days+1)]
    cache = Path(root)/'positions'/hashlib.sha256(portfolio.encode()).hexdigest()[:20]
    cache.mkdir(parents=True, exist_ok=True)
    refresh = (end-timedelta(days=2)).isoformat()
    missing = [d for d in days if not (cache/(d+'.json')).exists() or d >= refresh]
    if missing:
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            work = Path(tmp)
            job = work/'job.json'
            job.write_text(dump(dict(portfolio=portfolio, dates=[d.replace('-','') for d in missing])), encoding='utf-8')
            command=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(APP/'pull_positions.ps1'),
                     '-JobFile',str(job),'-OutputDir',str(work)]
            try:
                process=subprocess.run(command, capture_output=True, timeout=240,
                                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError('Bloomberg APIに接続できないか、確認がタイムアウトしました。TerminalへのログインとDesktop APIの導入を確認してください。') from exc
            if process.returncode:
                raise ValueError(api_failure(process))
            fetched={}
            for d in missing:
                path=work/(d.replace('-','')+'.txt')
                if not path.exists():raise ValueError('APIの日次データが不足しています。確認は完了していません。')
                fetched[d]=parse_positions(path.read_text(encoding='utf-8-sig'),portfolio)
            for d,positions in fetched.items():
                (cache/(d+'.json')).write_text(dump(positions),encoding='utf-8')
    return [dict(date=d, positions=json.loads((cache/(d+'.json')).read_text(encoding='utf-8'))) for d in days]


def reconcile(snapshots, rows, portfolio):
    candidates=[]; unresolved=[]; matched=0; changes=0; linked_ids=set()
    for old,new in zip(snapshots,snapshots[1:]):
        for ticker in sorted(old['positions'].keys()|new['positions'].keys()):
            delta=new['positions'].get(ticker,0)-old['positions'].get(ticker,0)
            if math.isclose(delta,0,abs_tol=1e-7):continue
            # The portfolio consists of listed ETFs. Cash balances are not ETF trades.
            if not ticker.endswith(' Equity'):continue
            changes+=1
            identity=hashlib.sha256(dump([portfolio,old['date'],new['date'],ticker,delta]).encode()).hexdigest()[:16]
            linked=[r for r in rows if r['status']!='void' and r['ticker'].strip().upper()==ticker.upper() and (
                r.get('_detection_id')==identity or (not r.get('_detection_id') and r.get('date') and old['date']<r['date']<=new['date']))]
            linked_ids.update(r['trade_id'] for r in linked)
            known=sum(float(r['quantity_delta'] or 0) for r in linked)
            if math.isclose(known,delta,abs_tol=1e-6):
                pending=[r for r in linked if r['status']!='confirmed']
                if pending:unresolved.extend(dict(id=r['trade_id'],ticker=ticker,date=new['date'],reason='候補行の取引日・区分・金額を確認し、確認状態を「確認済み」にしてください。') for r in pending)
                else:matched+=1
                continue
            if any(r.get('_detection_id')==identity for r in linked):
                unresolved.append(dict(id=linked[0]['trade_id'],ticker=ticker,date=new['date'],reason=f'台帳数量{known:g}とAPI数量変化{delta:g}が一致しません。'))
                continue
            nearby=[r for r in rows if not linked and r['status']=='confirmed' and not r.get('_detection_id')
                    and r['trade_id'] not in linked_ids and r['ticker'].strip().upper()==ticker.upper()
                    and r.get('date') and abs((date.fromisoformat(r['date'])-date.fromisoformat(new['date'])).days)<=3
                    and math.isclose(float(r['quantity_delta'] or 0),delta,abs_tol=1e-6)]
            if len(nearby)==1:
                row=nearby[0];linked_ids.add(row['trade_id'])
                candidates.append(dict(row,status='pending',_existing=True,
                    _detection_id=identity,_detected_start=old['date'],_detected_end=new['date'],
                    _required=f'日付差異：API検出{new["date"]}、台帳{row["date"]}。同じ取引か確認し、実際の取引日を保持・訂正して確認済みに変更。'))
                continue
            candidates.append(dict(trade_id='API-'+identity[:10],date='',ticker=ticker,event_type='',
                quantity_delta=delta-known,amount_jpy='',amount_basis='',pair_id='',status='pending',
                notes=f'API数量変化 {delta:g}、同期間の台帳数量 {known:g}。買付・売却・分割・移管等を確認してください。',
                _detection_id=identity,_detected_start=old['date'],_detected_end=new['date'],
                _required='取引日・取引区分・円建て金額（売買の場合）・確認状態'))
    # Existing ledger-only events are also visible; they are not proof of an API failure.
    return dict(start=snapshots[0]['date'],end=snapshots[-1]['date'],changes=changes,matched=matched,
                candidates=candidates,unresolved=unresolved,
                ledger_only=[dict(id=r['trade_id'],ticker=r['ticker'],date=r['date']) for r in rows if r['status']!='void' and r['trade_id'] not in linked_ids and r.get('date') and snapshots[0]['date']<r['date']<=snapshots[-1]['date']],
                note='日次の保有数量差による候補です。検出日は約定日ではありません。同日中に相殺される取引は検出できません。')


def prefill_candidates(root, portfolio, candidates):
    """Proposal only: snapshot date, quantity direction, and valuation-based JPY estimate."""
    fresh=[r for r in candidates if not r.get('_existing')]
    if not fresh:return
    days=sorted({r[k] for r in fresh for k in ('_detected_start','_detected_end')})
    cache=Path(root)/'valuations'/hashlib.sha256(portfolio.encode()).hexdigest()[:20]
    cache.mkdir(parents=True,exist_ok=True)
    # Always refresh the few candidate dates so estimates use the same current API records.
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        work=Path(tmp);job=work/'job.json'
        job.write_text(dump(dict(portfolio=portfolio,dates=[d.replace('-','') for d in days])),encoding='utf-8')
        try:
            process=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                '-File',str(APP/'pull_positions.ps1'),'-JobFile',str(job),'-OutputDir',str(work)],
                capture_output=True,timeout=240,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise ValueError('候補金額の評価データを取得できませんでした。再確認してください。') from exc
        if process.returncode:raise ValueError(api_failure(process))
        values={}
        for day in days:
            text=(work/(day.replace('-','')+'.txt')).read_text(encoding='utf-8-sig')
            quantities=parse_positions(text,portfolio)
            values[day]={}
            for block in re.findall(r'PORTFOLIO_DATA = \{([^{}]*)\}',text,re.S):
                ticker=re.search(r'Security = "([^"]+)"',block)[1]
                mv=re.search(r'Market Value = ([^\s]+)',block)
                if mv and quantities[ticker]:
                    price=float(mv[1])/quantities[ticker]
                    if math.isfinite(price) and price>0:values[day][ticker]=price
        fill_proposals(fresh,values)


def fill_proposals(candidates, values):
    for row in candidates:
        day=row['_detected_end'];ticker=row['ticker'];delta=row['quantity_delta']
        price=values.get(day,{}).get(ticker)
        pricing_day=day
        if price is None:
            pricing_day=row['_detected_start'];price=values.get(pricing_day,{}).get(ticker)
        if price is None:raise ValueError(f'{ticker}：日元評価単価が取得できず金額を補完できません。')
        row.update(date=day,event_type='buy' if delta>0 else 'sell',
            amount_jpy=round(delta*price,2),amount_basis='estimated',status='pending')
        row['notes']+=f' 仮入力：取引日は数量変化の検出日。方向は数量の符号から推定。概算額＝数量増減×{pricing_day}の円建て時価総額÷保有数量。約定金額・手数料ではありません。分割・移管の場合は区分と金額を訂正してください。'
        row['_required']='日付・区分・概算額を確認し、必要な訂正後に確認状態を「確認済み」に変更。'
