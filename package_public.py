"""Export only explicitly named source files, even if private data exists locally."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
PUBLIC = ['.gitignore', 'README.md', 'requirements.txt', 'setup.cmd', 'start.cmd',
          'package_public.py', 'github_transfer.py', 'github_upload.bat', 'company_download.bat', 'tests/test_transfer.py', 'app/analytics.js', 'app/analytics_data.py', 'app/port_parser.py',
          'app/report_template.html', 'app/portal.html', 'app/server.py', 'app/store.py',
          'app/api_reconcile.py', 'app/pull_positions.ps1', 'app/trade_review.py', 'tests/test_workflow.py', 'tests/test_store.py', 'tests/test_analytics.cjs']


def package(destination=None):
    destination = Path(destination) if destination else ROOT / 'dist' / 'portfolio-report-viewer-source.zip'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for name in PUBLIC:
            archive.write(ROOT / name, 'portfolio-report-viewer/' + name)
    return destination


if __name__ == '__main__':
    print(package())
