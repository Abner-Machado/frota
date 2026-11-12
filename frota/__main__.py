"""Allow running the toolkit with ``python -m frota``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
