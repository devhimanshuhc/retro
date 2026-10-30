from pathlib import Path

import uvicorn

if __name__ == "__main__":
    # app_dir puts the repo root on sys.path so `app` and `config` import from any cwd
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True, app_dir=str(Path(__file__).parent.parent))
