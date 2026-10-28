"""Launch the live presentation dashboard for the DAC simulation."""

import argparse
import sys
import webbrowser
from pathlib import Path

# Ensure src is on sys.path
ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dac_sim.dashboard import start_dashboard_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the DAC live simulation dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8050, help="Port (default: 8050)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print("\n" + "=" * 70)
    print("DAC SIMULATION -- HEAT-LINKED ROLLER BELT LIVE SHOWCASE SERVER")
    print("=" * 70)
    print(f"Server running at:  {url}")
    print(f"Local dashboard:    {url}/")
    print(f"API endpoints:      {url}/api/simulate, {url}/api/export/csv, etc.")
    print("=" * 70)
    print("Press Ctrl+C to stop the dashboard server.\n")

    server = start_dashboard_server(host=args.host, port=args.port)

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
    finally:
        server.server_close()
        print("Dashboard server stopped.")


if __name__ == "__main__":
    main()
