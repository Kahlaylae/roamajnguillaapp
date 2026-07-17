#!/usr/bin/env python3
"""macOS App Launcher — starts server and opens browser. Designed to be called from AppleScript app."""
import subprocess, webbrowser, time, os, sys, urllib.request

DATA_DIR = "/Users/kayboy/Documents/ROAMCMS"
PORT = 5050

def is_running():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/files", timeout=1)
        return True
    except:
        return False

if __name__ == "__main__":
    if is_running():
        # Server already running — just open browser
        webbrowser.open(f"http://localhost:{PORT}")
        sys.exit(0)

    # Kill any stale process on the port
    subprocess.run(["lsof", "-ti", f":{PORT}"], capture_output=True)
    
    # Start server as a fully detached daemon
    subprocess.Popen(
        [sys.executable, os.path.join(DATA_DIR, "server.py")],
        cwd=DATA_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # detach from parent so it survives
    )

    # Wait for server to be ready
    for _ in range(30):
        if is_running():
            break
        time.sleep(0.2)

    # Open browser
    webbrowser.open(f"http://localhost:{PORT}")
