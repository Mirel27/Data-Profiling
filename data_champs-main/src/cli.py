from __future__ import annotations

import sys
from collections.abc import Sequence

from .generate_raw_demo_db import main as simulate_main


USAGE = """Usage:
  python -m src simulate [options]
"""


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in {"-h", "--help"}:
        print(USAGE.strip())
        return 0 if args else 2

    command, *command_args = args
    if command == "simulate":
        return simulate_main(command_args)

    print(f"Unknown command: {command}")
    print(USAGE.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
