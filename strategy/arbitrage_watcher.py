"""Command-line entry point for the NSE/BSE arbitrage watcher."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from strategy.arbitrage.runner import main


if __name__ == "__main__":
	main()
