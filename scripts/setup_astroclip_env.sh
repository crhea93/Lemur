#!/usr/bin/env bash
# Create the conda env used by `make similar` and `make serve`.
#
# AstroCLIP's README pins torch 2.0, which predates recent GPUs (RTX 50xx needs
# torch>=2.7 built for CUDA 12.8), so this installs a current torch and adds the
# packages AstroCLIP/DINOv2 import but do not declare (they install --no-deps).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_NAME="${ASTROCLIP_ENV:-lemur-astroclip}"
CONDA="${CONDA:-$(command -v conda || echo "$HOME/miniconda3/bin/conda")}"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu128}"
DINOV2_COMMIT="2302b6bf46953431b969155307b9bed152754069"

if [[ ! -x "$CONDA" ]]; then
    echo "conda not found (set CONDA=/path/to/conda)" >&2
    exit 1
fi

if ! "$CONDA" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "==> Creating conda env '$ENV_NAME'"
    "$CONDA" create -y -q -n "$ENV_NAME" python=3.11
fi

ENV_PREFIX="$("$CONDA" env list | awk -v n="$ENV_NAME" '$1 == n {print $NF}')"
PIP="$ENV_PREFIX/bin/pip"

echo "==> Installing torch from $TORCH_INDEX"
"$PIP" install -q torch torchvision --index-url "$TORCH_INDEX"

echo "==> Installing AstroCLIP runtime dependencies"
"$PIP" install -q lightning omegaconf fvcore iopath jaxtyping huggingface_hub \
    astropy scipy matplotlib "numpy<2" "datasets>=3" scikit-image python-dotenv \
    h5py joblib submitit

echo "==> Installing DINOv2 and AstroCLIP (no deps; their pins are too old)"
"$PIP" install -q --no-deps "git+https://github.com/facebookresearch/dinov2.git@$DINOV2_COMMIT"
"$PIP" install -q --no-deps "git+https://github.com/PolymathicAI/AstroCLIP.git"

echo "==> Installing Lemur (API server for make serve)"
"$PIP" install -q -e "$ROOT_DIR"

"$ENV_PREFIX/bin/python" - <<'PY'
import torch
import astroclip.models  # noqa: F401

device = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU only"
print(f"OK: torch {torch.__version__}, AstroCLIP importable, device: {device}")
PY
