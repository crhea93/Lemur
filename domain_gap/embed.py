"""Frozen AstroCLIP embeddings of a preprocessing run.

    ~/miniconda3/envs/lemur-astroclip/bin/python -m domain_gap.embed --run <output_dir>

Writes embeddings_{source}.npy (N, 1024), row i being the embedding of row i of
inputs_{source}.npy (the manifest's ``index``). Images are replicated to three
channels and resized to 144 px (bilinear, antialiased) by LEMUR's own
``to_model_batch``, so a run with ``grid: 144`` reaches the model unchanged
and the baseline (64 px) is resized exactly as in LEMUR.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import io


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", required=True, help="Output directory of domain_gap.preprocess")
    parser.add_argument("--checkpoint", help="AstroCLIP checkpoint (default: from Hugging Face)")
    parser.add_argument("--device", help="cuda or cpu (default: cuda if available)")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--force", action="store_true", help="Recompute existing embeddings")
    args = parser.parse_args(argv)

    run_dir = Path(args.run)
    run = json.loads((run_dir / "run.json").read_text())
    model_size = int(run["config"].get("model_size", 144))
    script = io.astroclip_script()
    if model_size != script.MODEL_INPUT_SIZE:
        raise SystemExit(f"model_size {model_size} != AstroCLIP input {script.MODEL_INPUT_SIZE}")
    encode = script.make_astroclip_encoder(args.checkpoint, args.device, args.batch_size)
    for inputs in sorted(run_dir.glob("inputs_*.npy")):
        source = inputs.stem[len("inputs_") :]
        out = run_dir / f"embeddings_{source}.npy"
        if out.exists() and not args.force:
            print(f"{source}: exists, skipped")
            continue
        images = np.load(inputs, mmap_mode="r")
        started = time.time()
        embeddings = (
            encode(np.asarray(images)) if len(images) else np.zeros((0, 1024), np.float32)
        )
        np.save(out, embeddings.astype(np.float32))
        print(f"{source}: {embeddings.shape} in {time.time() - started:.0f} s", flush=True)
    (run_dir / "embed.json").write_text(
        json.dumps(
            {
                "checkpoint": args.checkpoint or f"{script.HF_REPO_ID}/{script.HF_CHECKPOINT}",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "model_size": model_size,
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
