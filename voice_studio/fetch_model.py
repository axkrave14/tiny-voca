"""Download the released model and its matching phonemizer assets."""
import os
from pathlib import Path
from huggingface_hub import snapshot_download

REVISION = "eac048b7a4392584725af9792460a0211fa1cac7"

if __name__ == "__main__":
    destination = Path(os.environ.get("TINY_VOCA_WEIGHTS", "weights"))
    snapshot_download("n4ze3m/tiny-voca", revision=REVISION, local_dir=destination,
                      allow_patterns=["tiny-voca.pt", "config.json", "LICENSE", "phonemizer/*"])
    print(f"Model files saved to {destination.resolve()}")
