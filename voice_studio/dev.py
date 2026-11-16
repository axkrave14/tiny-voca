"""Development entrypoint compatible with preview tools' host/port arguments."""
import argparse
import os
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8090")))
    # Uvicorn already fails on an occupied port instead of selecting another one.
    parser.add_argument("--strictPort", action="store_true")
    args = parser.parse_args()
    uvicorn.run("voice_studio.app:app", host=args.host, port=args.port, access_log=False)
