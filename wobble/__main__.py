"""Allow ``python -m wobble`` to run the CLI through the fast bootstrap."""

import sys

from wobble.bootstrap import run

if __name__ == "__main__":
    sys.exit(run())
