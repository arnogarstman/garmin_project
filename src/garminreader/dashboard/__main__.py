"""Launch the dashboard: `uv run dashboard` (extra args go to `streamlit run`)."""

import sys
from pathlib import Path

from streamlit.web import cli


def main() -> None:
    sys.argv = ["streamlit", "run", str(Path(__file__).with_name("app.py")), *sys.argv[1:]]
    sys.exit(cli.main())


if __name__ == "__main__":
    main()
