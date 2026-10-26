"""Allow ``python -m mi6``; delegates to mi6.cli.main."""

import sys

from mi6.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
