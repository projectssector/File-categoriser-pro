import os
import sys
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    # Ensure src/ is on path when running from source
    if not getattr(sys, 'frozen', False):
        src = HERE / 'src'
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))

    def _bundle_dir():
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS)
        return HERE

    def _app_root():
        if getattr(sys, 'frozen', False):
            return Path.home() / 'FileCategorizer'
        return HERE

    bundle = _bundle_dir()
    root = _app_root()
    (root / 'config').mkdir(parents=True, exist_ok=True)
    (root / 'data').mkdir(parents=True, exist_ok=True)

    config_file = root / 'config' / 'config.yaml'
    example = bundle / 'config' / 'config.example.yaml'
    if not config_file.exists() and example.exists():
        shutil.copyfile(example, config_file)

    os.chdir(root)

    settings_path = root / 'data' / 'settings.json'
    try:
        if settings_path.exists():
            s = json.loads(settings_path.read_text(encoding='utf-8'))
            if s.get('gemini_api_key'):
                os.environ['GEMINI_API_KEY'] = str(s['gemini_api_key']).strip()
    except Exception:
        pass

    from file_categorizer.gui import run
    run(str(config_file))


if __name__ == '__main__':
    main()