"""Install this ZIP's Insights code with backups; preserve credentials and data."""
import argparse
import shutil
from datetime import datetime
from pathlib import Path


def install(source, target):
    source=Path(source).resolve();target=Path(target).resolve()
    if source==target:raise ValueError('Extract the update separately from the installed application')
    if not (target/'insights'/'service.py').is_file() or not (target/'web'/'package.json').is_file():
        raise ValueError('Destination is not the existing BharatSignal Fusion Insights project')
    required=['insights/fii_holdings.py','insights/fii_stock_deals.py','insights/service.py',
              'insights/api.py','insights/strategies/btst_closing.py',
              'web/src/main.js','web/src/styles.css']
    for relative in required:
        if not (source/relative).is_file():raise ValueError('Update archive missing '+relative)
    # Copy the complete Python module set, so partial older installs gain all
    # dependencies. Unrelated local-only files are retained.
    files=sorted((source/'insights').rglob('*.py'))
    files+=[source/'web'/'src'/'main.js',source/'web'/'src'/'styles.css']
    plan=[(p,p.relative_to(source),target/p.relative_to(source)) for p in files]
    backup=target/'update_backups'/('fii-holdings-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True,exist_ok=False)
    for _,relative,dest in plan:
        if dest.exists():
            saved=backup/relative;saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(dest,saved)
    written=[]
    try:
        for src,relative,dest in plan:
            existed=dest.exists();dest.parent.mkdir(parents=True,exist_ok=True)
            written.append((relative,dest,existed));shutil.copy2(src,dest)
    except Exception:
        for relative,dest,existed in reversed(written):
            if existed:shutil.copy2(backup/relative,dest)
            elif dest.exists():dest.unlink()
        raise
    print('Installed',len(plan),'source files. Backup:',backup)
    print('Credentials, settings and databases were not changed. Run tests and rebuild the frontend.')
    return backup


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True)
    args=parser.parse_args()
    try:install(Path(__file__).resolve().parents[1],args.project)
    except (OSError,ValueError) as exc:raise SystemExit('UPDATE STOPPED: '+str(exc))
