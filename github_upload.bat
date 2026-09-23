@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
set "PORT_TRANSFER_SELF=%~f0"
set "PORT_TRANSFER_MODE=upload"
set "PORT_PYTHON="
if exist "%~dp0.venv\Scripts\python.exe" set "PORT_PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined PORT_PYTHON if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PORT_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if defined PORT_PYTHON goto explicit_python
where py >nul 2>nul
if not errorlevel 1 goto py_launcher
where python >nul 2>nul
if not errorlevel 1 goto python_path
echo Python 3.11以降が必要です。社内の導入手順に従ってインストールしてください。
echo https://www.python.org/downloads/windows/
pause
exit /b 1
:explicit_python
"%PORT_PYTHON%" -c "import os,pathlib;exec(compile(pathlib.Path(os.environ['PORT_TRANSFER_SELF']).read_text(encoding='utf-8').split('# === PYTHON PAYLOAD ===\n',1)[1],os.environ['PORT_TRANSFER_SELF'],'exec'))"
goto finish
:py_launcher
py -3 -c "import os,pathlib;exec(compile(pathlib.Path(os.environ['PORT_TRANSFER_SELF']).read_text(encoding='utf-8').split('# === PYTHON PAYLOAD ===\n',1)[1],os.environ['PORT_TRANSFER_SELF'],'exec'))"
goto finish
:python_path
python -c "import os,pathlib;exec(compile(pathlib.Path(os.environ['PORT_TRANSFER_SELF']).read_text(encoding='utf-8').split('# === PYTHON PAYLOAD ===\n',1)[1],os.environ['PORT_TRANSFER_SELF'],'exec'))"
:finish
set "PORT_RESULT=%ERRORLEVEL%"
pause
exit /b %PORT_RESULT%
# === PYTHON PAYLOAD ===
"""Interactive source-only GitHub transfer. Credentials stay in GitHub CLI."""
import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# Filled from package_public.PUBLIC when the release scripts are generated.
PUBLIC_FILES = ['.gitignore', 'README.md', 'requirements.txt', 'setup.cmd', 'start.cmd', 'package_public.py', 'github_transfer.py', 'github_upload.bat', 'company_download.bat', 'tests/test_transfer.py', 'app/analytics.js', 'app/analytics_data.py', 'app/port_parser.py', 'app/report_template.html', 'app/portal.html', 'app/server.py', 'app/store.py', 'app/api_reconcile.py', 'app/pull_positions.ps1', 'app/trade_review.py', 'tests/test_workflow.py', 'tests/test_store.py', 'tests/test_analytics.cjs']


def run(args, cwd=None, check=True):
    result = subprocess.run(args, cwd=cwd, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip() or 'コマンドの実行に失敗しました。')
    return result


def prepare_tools():
    config=settings()
    for command,key in [('git','git_executable'),('gh','github_cli')]:
        configured=config.get(key)
        if not shutil.which(command) and configured:
            executable=Path(configured)
            if executable.is_file() and executable.name.lower()==command+'.exe':
                os.environ['PATH']=str(executable.parent)+os.pathsep+os.environ.get('PATH','')


def authenticate():
    prepare_tools()
    if not shutil.which('gh'):
        raise RuntimeError('GitHub CLIが必要です。https://cli.github.com/ から導入して、このBATを再実行してください。')
    if run(['gh', 'auth', 'status', '--hostname', 'github.com'], check=False).returncode:
        print('ブラウザーでGitHubにログインしてください。パスワードやトークンをBATに記録しません。')
        if subprocess.run(['gh', 'auth', 'login', '--hostname', 'github.com', '--git-protocol', 'https', '--web']).returncode:
            raise RuntimeError('GitHubへのログインが完了しませんでした。')


def repository():
    repo = input('GitHubリポジトリ（例：account/portfolio-report-viewer）：').strip()
    repo = re.sub(r'^https://github\.com/', '', repo).removesuffix('.git').rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+', repo):
        raise ValueError('account/repository の形式で入力してください。')
    return repo


def settings_path():
    return Path(os.environ['PORT_TRANSFER_SELF']).resolve().parent / '.github-transfer-local.json'


def settings():
    path=settings_path()
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def remember(mode, value):
    config=settings();config[mode]=value
    settings_path().write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')


def valid_repository(repo):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+',repo):
        raise ValueError('保存済みのリポジトリ名が不正です。ローカル設定を削除して再設定してください。')
    return repo


def validate_sources(root):
    for name in PUBLIC_FILES:
        path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('公開用ファイルが不足、またはリンクになっています：' + name)


def upload(root):
    prepare_tools()
    if not shutil.which('git'):
        raise RuntimeError('Git for Windowsが必要です。https://git-scm.com/download/win から導入してください。')
    validate_sources(root)
    authenticate()
    saved=settings().get('upload',{})
    repo = valid_repository(saved['repo']) if saved.get('repo') else repository()
    exists = run(['gh', 'repo', 'view', repo, '--json', 'name'], check=False)
    if exists.returncode:
        if input('リポジトリを確認できません。新しい非公開リポジトリを作成しますか？ [y/N]：').strip().lower() != 'y':
            return
        run(['gh', 'repo', 'create', repo, '--private'])
    print('送信先：https://github.com/' + repo)
    print('送信対象：プログラム・説明書・テストのみ。data、Excel、取引台帳、HTML結果、設定、既存Git履歴は送りません。')
    if not saved and input('このリポジトリを更新先として保存し、アップロードしますか？ [y/N]：').strip().lower() != 'y':
        return
    # A new temporary checkout prevents local commits/history from leaking.
    git = ['git', '-c', 'credential.helper=', '-c', 'credential.helper=!gh auth git-credential']
    with tempfile.TemporaryDirectory(prefix='port-public-upload-') as temp:
        checkout = Path(temp) / 'source'
        run(git + ['clone', 'https://github.com/' + repo + '.git', str(checkout)])
        tracked = run(git + ['ls-files', '-z'], cwd=checkout).stdout.decode('utf-8').split('\0')
        extras = set(filter(None, tracked)) - set(PUBLIC_FILES)
        if extras:
            raise ValueError('このリポジトリには対象外のファイルがあります。専用の空リポジトリを使用してください：' + ', '.join(sorted(extras)[:8]))
        if run(git + ['rev-parse', '--verify', 'HEAD'], cwd=checkout, check=False).returncode:
            run(git + ['checkout', '-b', 'main'], cwd=checkout)
        for name in PUBLIC_FILES:
            destination = checkout / name
            if destination.is_symlink() or not destination.resolve().is_relative_to(checkout.resolve()):
                raise ValueError('リポジトリに外部リンクがあります：' + name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, destination)
        run(git + ['add', '--'] + PUBLIC_FILES, cwd=checkout)
        if not run(git + ['status', '--porcelain'], cwd=checkout).stdout.strip():
            remember('upload',dict(repo=repo))
            print('公開プログラムは最新です。変更はありません。')
            return
        user = json.loads(run(['gh', 'api', 'user']).stdout)
        run(git + ['config', 'user.name', user['login']], cwd=checkout)
        run(git + ['config', 'user.email', str(user['id']) + '+' + user['login'] + '@users.noreply.github.com'], cwd=checkout)
        run(git + ['commit', '-m', 'Update portfolio report viewer source'], cwd=checkout)
        run(git + ['push', 'origin', 'HEAD'], cwd=checkout)
    remember('upload',dict(repo=repo))
    print('アップロード完了：https://github.com/' + repo)


def source_archive(payload):
    """Extract only the explicit source list; never execute downloaded manifests."""
    files = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        manifests=[i for i in archive.infolist() if i.filename.split('/',1)[-1]=='package_public.py']
        if len(manifests)!=1 or manifests[0].file_size>100000:
            raise ValueError('公開ファイル一覧が見つかりません。')
        tree=ast.parse(archive.read(manifests[0]).decode('utf-8-sig'))
        declarations=[node.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PUBLIC' for t in node.targets)]
        if len(declarations)!=1:raise ValueError('公開ファイル一覧が不正です。')
        allowed=ast.literal_eval(declarations[0])
        if not isinstance(allowed,list) or not allowed or len(allowed)>200 or any(not safe_source_name(n) for n in allowed):
            raise ValueError('公開ファイル一覧に対象外のパスがあります。')
        total = 0
        for item in archive.infolist():
            parts = item.filename.split('/', 1)
            if len(parts) != 2 or parts[1] not in allowed:
                continue
            if parts[1] in files or item.file_size > 12 * 1024 * 1024:
                raise ValueError('公開アーカイブの構成が不正です。')
            total += item.file_size
            if total > 40 * 1024 * 1024:
                raise ValueError('公開アーカイブが想定サイズを超えています。')
            files[parts[1]] = archive.read(item)
    missing = set(allowed) - set(files)
    if missing:
        raise ValueError('公開用ファイルが不足しています。アップロードBATで更新してください：' + ', '.join(sorted(missing)))
    return files


def safe_source_name(name):
    if not isinstance(name,str):return False
    if name in PUBLIC_FILES:return True
    return bool(re.fullmatch(r'(app|tests)/[A-Za-z0-9_-]+\.(py|js|cjs|html|ps1)',name))


def install_sources(target, files):
    target.mkdir(parents=True, exist_ok=True)
    # Validate every destination before any mutation, including Windows junctions.
    for name in files:
        if not safe_source_name(name) or not (target / name).resolve().is_relative_to(target.resolve()):
            raise ValueError('保存先に対象外のパスまたは外部リンクがあります。')
    for name, payload in files.items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_name(destination.name + '.download-tmp')
        temp.write_bytes(payload)
        os.replace(temp, destination)


def download():
    authenticate()
    saved=settings().get('download',{})
    repo = valid_repository(saved['repo']) if saved.get('repo') else repository()
    default = Path.home() / 'Documents' / 'Codex' / 'PortfolioReportViewer'
    value = saved.get('target') or input('保存先 [' + str(default) + ']：').strip().strip('"')
    target = Path(value).expanduser().resolve() if value else default
    print('プログラムをダウンロードします。既存のdata・台帳・計算結果は変更しません。')
    archive = run(['gh', 'api', 'repos/' + repo + '/zipball']).stdout
    files = source_archive(archive)
    requirements=target/'requirements.txt'
    dependencies_changed=not requirements.exists() or requirements.read_bytes()!=files['requirements.txt']
    install_sources(target, files)
    remember('download',dict(repo=repo,target=str(target)))
    # Also remember the location when the installed copy of this BAT is used later.
    target_config=target/'.github-transfer-local.json'
    config=json.loads(target_config.read_text(encoding='utf-8')) if target_config.exists() else {}
    config['download']=dict(repo=repo,target=str(target))
    target_config.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print('保存完了：' + str(target))
    environment = target / '.venv'
    python = environment / 'Scripts' / 'python.exe'
    pending=target/'.dependencies-update-pending'
    if dependencies_changed or not python.exists() or pending.exists():
        pending.write_text('pending',encoding='utf-8')
        if not python.exists():
            run([sys.executable, '-m', 'venv', str(environment)])
        run([str(python), '-m', 'pip', 'install', '-r', str(target / 'requirements.txt')])
        pending.unlink()
        print('初期設定が完了しました。')
    print('更新完了。起動中のアプリがある場合は終了し、start.cmd から起動し直してください。')


def main(mode):
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11以降が必要です。')
    if mode == 'upload':
        upload(Path(os.environ['PORT_TRANSFER_SELF']).resolve().parent)
    elif mode == 'download':
        download()
    else:
        raise ValueError('不明な操作です。')


if __name__ == '__main__':
    try:
        main(os.environ['PORT_TRANSFER_MODE'])
    except (Exception, KeyboardInterrupt) as exc:
        print('\n処理を完了できませんでした：' + str(exc))
        sys.exit(1)
