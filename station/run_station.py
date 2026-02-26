"""
Entry point for running the Station server.
"""

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def _find_available_port(preferred=18888):
    """Try preferred port, fall back to a random available one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", preferred))
            return preferred
        except OSError:
            pass
    # Fallback: let OS pick
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


def main():
    """Main function to run the station server."""
    station_dir = Path(__file__).parent
    station_path = str(station_dir)
    sys.path.insert(0, station_path)

    # Use absolute paths so CWD doesn't matter
    restart_marker = station_dir / ".restart"
    env_file = station_dir / ".env"
    first_run = True

    while True:
        # Clean up stale restart marker
        restart_marker.unlink(missing_ok=True)

        if first_run:
            print("")
            print("  Open Anonymity Station")
            print("  " + "=" * 30)
            print("")

        env_exists = env_file.exists()

        # Auto-enable config UI on first run when no .env exists
        if not env_exists:
            os.environ["STATION_ENABLE_CONFIG_UI"] = "true"

        try:
            import uvicorn
            from system.bootstrap import bootstrap_station
            from system.config import Settings

            settings = Settings()
            bootstrap_station(settings)

            # Pick an available port on first run, reuse on restart
            if first_run:
                port = _find_available_port(preferred=settings.port)
            # port is retained across restarts

            display_host = "localhost" if settings.host == "0.0.0.0" else settings.host
            base_url = f"http://{display_host}:{port}"

            if first_run and not env_exists:
                print("  No .env file found — opening setup UI...")
                print("")
                print(f"  -> {base_url}/config")
                print("")
                print("  Configure your station in the browser, then restart.")
                print("")
            elif first_run:
                print(f"  Server:  {base_url}")
                print(f"  Config:  {base_url}/config")
                print(f"  Docs:    {base_url}/docs")
                print("")
                print("  Endpoints:")
                print("    POST  /api/request_key             Request ephemeral key")
                print("    POST  /api/tickets/ticket_request  Issue tickets (Bearer)")
                print("    GET   /api/tickets/issue/public-key")
                print("")
            else:
                print(f"  Restarted — {base_url}/config")
                print("")

            # Auto-open browser to config page if no .env on first run
            if first_run and not env_exists:
                def _open_browser():
                    import time
                    time.sleep(1.5)
                    webbrowser.open(f"{base_url}/config")
                threading.Thread(target=_open_browser, daemon=True).start()

            reload_enabled = os.getenv("STATION_RELOAD", "false").lower() == "true"
            reload_config = {}

            if reload_enabled:
                reload_config = {
                    "reload": True,
                    "reload_excludes": ["*.log", "*.db", "*.sqlite*"],
                }

            first_run = False

            uvicorn.run(
                "main:app",
                host=settings.host,
                port=port,
                log_level=settings.log_level.lower(),
                access_log=True,
                **reload_config,
            )

        except KeyboardInterrupt:
            if restart_marker.exists():
                restart_marker.unlink(missing_ok=True)
                print("\n  Restarting...")
                continue
            print("\n  Station stopped.")
            return 0
        except Exception as e:
            print(f"\n  Failed to start: {str(e)}")
            import traceback
            traceback.print_exc()
            return 1

        # Check if this was a restart signal (non-KeyboardInterrupt exit)
        if restart_marker.exists():
            restart_marker.unlink(missing_ok=True)
            print("  Restarting...")
            continue

        # Normal exit
        return 0


if __name__ == "__main__":
    sys.exit(main())
