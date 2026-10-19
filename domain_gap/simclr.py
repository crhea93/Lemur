"""An X-ray-native encoder: SimCLR trained on our own images, as a second view of the gap.

    PY=~/miniconda3/envs/lemur-astroclip/bin/python
    PYTHONPATH=. $PY -m domain_gap.simclr train --train-on mocks     # or lemur
    PYTHONPATH=. $PY -m domain_gap.simclr embed --train-on mocks
    PYTHONPATH=. $PY -m domain_gap.simclr validate                   # positive controls

AstroCLIP was trained on optical galaxy images. Here a ResNet-18 is trained
from scratch, by contrastive learning (SimCLR, NT-Xent loss), on the model
inputs of one preprocessing run (default harmonized_physical: 500 kpc, 144 px,
one shared intensity scale), on either the mocks only (the
train-on-simulations case) or LEMUR only.

Augmentations, applied on the GPU: any rotation, flips, zoom 1-1.3x, shifts of
up to 5% of the field, Gaussian blur (sigma 0-1.5 px) and additive noise
(sigma 0-0.03). There is no brightness or contrast jitter, so absolute surface
brightness stays part of what the encoder learns.

``embed`` writes outputs/embeddings/simclr_<train-on>/ (the preprocessing run's
manifest, run.json and embeddings_<source>.npy of the 512-d backbone output),
which every gap analysis (core, mass_match, analyze_embeddings, observational)
reads like the AstroCLIP runs. ``validate`` checks that an encoder carries
physical information before its gap numbers mean anything: an encoder that
separates nothing would also show no gap. It reports, per run, the grouped
cross-validated R^2 of ridge regressions for log M500 (mocks), log central
cooling time (TNG-Cluster) and log c (all), and how often a mock image's
nearest neighbour is another image of the same halo.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PREPROCESSED = Path("/run/media/crhea/ef10789c-0ada-41e4-8d3f-8f17dbcc0558/_domain_gap/preprocessed")
EMB = ROOT / "outputs" / "embeddings"
MODELS = ROOT / "outputs" / "simclr"
SOURCES = ("LEMUR", "TNG300-1", "TNG-Cluster")


# ---------------------------------------------------------------- data


def load_inputs(run_dir, sources):
    """(images N x 144 x 144 float32, manifest rows) for the extracted images of ``sources``."""
    run_dir = Path(run_dir)
    manifest = pd.read_parquet(run_dir / "manifest.parquet")
    images, rows = [], []
    for source in sources:
        arr = np.load(run_dir / f"inputs_{source}.npy", mmap_mode="r")
        m = manifest[(manifest["source"] == source) & (manifest["index"] >= 0)].sort_values("index")
        images.append(np.asarray(arr[m["index"].astype(int).to_numpy()], dtype=np.float32))
        rows.append(m)
    return np.concatenate(images), pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------- model


def make_encoder():
    import torch
    import torchvision

    net = torchvision.models.resnet18(weights=None)
    net.conv1 = torch.nn.Conv2d(1, 64, kernel_size=7, stride=2, padding=3, bias=False)
    net.fc = torch.nn.Identity()
    return net


def make_head():
    import torch

    return torch.nn.Sequential(
        torch.nn.Linear(512, 512), torch.nn.BatchNorm1d(512), torch.nn.ReLU(inplace=True), torch.nn.Linear(512, 128)
    )


def augment(x, gen):
    """Random view of a batch (B, 1, H, W) on its device."""
    import torch
    import torch.nn.functional as F

    b = x.shape[0]
    dev = x.device
    angle = torch.rand(b, generator=gen, device=dev) * 2 * np.pi
    flip = torch.where(torch.rand(b, generator=gen, device=dev) < 0.5, -1.0, 1.0)
    zoom = 1.0 + 0.3 * torch.rand(b, generator=gen, device=dev)
    shift = (torch.rand(b, 2, generator=gen, device=dev) - 0.5) * 0.1
    cos, sin = torch.cos(angle) / zoom, torch.sin(angle) / zoom
    theta = torch.stack(
        [torch.stack([cos * flip, -sin, shift[:, 0]], 1), torch.stack([sin * flip, cos, shift[:, 1]], 1)], 1
    )
    grid = F.affine_grid(theta, x.shape, align_corners=False)
    x = F.grid_sample(x, grid, mode="bilinear", padding_mode="zeros", align_corners=False)
    # Blur: a per-sample Gaussian of sigma 0-1.5 px, as a separable convolution.
    sigma = 1.5 * torch.rand(b, generator=gen, device=dev)
    radius = 4
    t = torch.arange(-radius, radius + 1, device=dev, dtype=x.dtype)
    kern = torch.exp(-0.5 * (t[None, :] / sigma.clamp(min=1e-3)[:, None]) ** 2)
    kern = torch.where(sigma[:, None] < 0.05, (t[None, :] == 0).to(x.dtype), kern)
    kern = kern / kern.sum(1, keepdim=True)
    xs = x.reshape(1, b, *x.shape[2:])
    xs = F.conv2d(F.pad(xs, (radius, radius, 0, 0), mode="reflect"), kern[:, None, None, :], groups=b)
    xs = F.conv2d(F.pad(xs, (0, 0, radius, radius), mode="reflect"), kern[:, None, :, None], groups=b)
    x = xs.reshape(b, 1, *x.shape[2:])
    noise = 0.03 * torch.rand(b, 1, 1, 1, generator=gen, device=dev)
    return (x + noise * torch.randn(x.shape, generator=gen, device=dev, dtype=x.dtype)).clamp(0, 1)


def nt_xent(z1, z2, temperature):
    import torch
    import torch.nn.functional as F

    z = F.normalize(torch.cat([z1, z2]), dim=1)
    sim = z @ z.T / temperature
    n = z1.shape[0]
    sim.fill_diagonal_(float("-inf"))
    target = torch.cat([torch.arange(n, 2 * n), torch.arange(0, n)]).to(z.device)
    return F.cross_entropy(sim, target)


def train(args):
    import torch

    torch.manual_seed(args.seed)
    sources = ["TNG300-1", "TNG-Cluster"] if args.train_on == "mocks" else ["LEMUR"]
    images, rows = load_inputs(PREPROCESSED / args.config, sources)
    keep = (rows["coverage_mean"] >= 0.8).to_numpy()
    images = images[keep]
    print(f"Training on {len(images)} {args.train_on} images from {args.config}", flush=True)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = torch.from_numpy(images).to(dev).unsqueeze(1)
    encoder, head = make_encoder().to(dev), make_head().to(dev)
    params = list(encoder.parameters()) + list(head.parameters())
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=1e-4)
    steps_per_epoch = max(1, len(data) // args.batch_size)
    total = steps_per_epoch * args.epochs
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=total, pct_start=0.05)
    gen = torch.Generator(device=dev).manual_seed(args.seed)
    out = MODELS / f"simclr_{args.train_on}"
    out.mkdir(parents=True, exist_ok=True)
    log = []
    started = time.time()
    for epoch in range(args.epochs):
        perm = torch.randperm(len(data), generator=gen, device=dev)
        losses = []
        encoder.train()
        head.train()
        for s in range(steps_per_epoch):
            batch = data[perm[s * args.batch_size : (s + 1) * args.batch_size]]
            with torch.autocast(device_type=dev.type, dtype=torch.bfloat16):
                z1 = head(encoder(augment(batch, gen)))
                z2 = head(encoder(augment(batch, gen)))
            loss = nt_xent(z1.float(), z2.float(), args.temperature)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            losses.append(loss.item())
        log.append({"epoch": epoch + 1, "loss": float(np.mean(losses)), "minutes": (time.time() - started) / 60})
        if (epoch + 1) % 10 == 0 or epoch == 0:
            print(f"epoch {epoch + 1}/{args.epochs}: loss {log[-1]['loss']:.3f} ({log[-1]['minutes']:.1f} min)", flush=True)
    torch.save({"encoder": encoder.state_dict(), "args": vars(args)}, out / "encoder.pt")
    pd.DataFrame(log).to_csv(out / "training_log.csv", index=False)
    print(f"Saved {out / 'encoder.pt'}")


def embed(args):
    import torch

    model_dir = MODELS / f"simclr_{args.train_on}"
    state = torch.load(model_dir / "encoder.pt", map_location="cpu", weights_only=True)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    encoder = make_encoder()
    encoder.load_state_dict(state["encoder"])
    encoder.to(dev).eval()
    run_dir = PREPROCESSED / state["args"]["config"]
    name = f"simclr_{args.train_on}"
    out = EMB / name
    out.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        arr = np.load(run_dir / f"inputs_{source}.npy", mmap_mode="r")
        chunks = []
        with torch.no_grad():
            for i in range(0, len(arr), 512):
                x = torch.from_numpy(np.asarray(arr[i : i + 512], dtype=np.float32)).to(dev).unsqueeze(1)
                chunks.append(encoder(x).float().cpu().numpy())
        emb = np.concatenate(chunks) if chunks else np.zeros((0, 512), np.float32)
        np.save(out / f"embeddings_{source}.npy", emb.astype(np.float32))
        print(f"{source}: {emb.shape}")
    shutil.copy2(run_dir / "manifest.parquet", out / "manifest.parquet")
    run = json.loads((run_dir / "run.json").read_text())
    run["config"]["name"] = name
    run["encoder"] = {"kind": "simclr", "train_on": args.train_on, **state["args"]}
    (out / "run.json").write_text(json.dumps(run, indent=1, default=str))
    (out / "embed.json").write_text(json.dumps({"encoder": str(model_dir / "encoder.pt"), "date": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1))
    print(f"Wrote {out}")


# ---------------------------------------------------------------- positive controls


def ridge_cv_r2(x, y, groups, folds=5, alpha=1.0, seed=0):
    """Grouped k-fold R^2 of ridge regression (standardized features)."""
    ok = np.isfinite(y)
    x, y, groups = x[ok], y[ok], np.asarray(groups)[ok]
    unique = np.unique(groups)
    rng = np.random.default_rng(seed)
    fold_of = dict(zip(rng.permutation(unique), np.arange(len(unique)) % folds))
    fold = np.array([fold_of[g] for g in groups])
    pred = np.zeros_like(y)
    for k in range(folds):
        tr, te = fold != k, fold == k
        mu, sd = x[tr].mean(0), x[tr].std(0) + 1e-8
        a = (x[tr] - mu) / sd
        ym = y[tr].mean()
        w = np.linalg.solve(a.T @ a + alpha * len(a) * np.eye(a.shape[1]), a.T @ (y[tr] - ym))
        pred[te] = ((x[te] - mu) / sd) @ w + ym
    return float(1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2))


def validate(args):
    sys.path.insert(0, str(ROOT))
    from domain_gap import analyze_embeddings as ae

    core = pd.read_csv(ROOT / "outputs" / "figures" / "core" / "core.csv")
    cool = pd.read_csv(ROOT / "configs" / "halos" / "tng_cluster.csv")
    rows = []
    for run in args.runs:
        df, x, name = ae.load_run(EMB / run)
        df = df.merge(core, on=["source", "name"], how="left")
        mocks = (df["source"] != "LEMUR").to_numpy()
        m = df[mocks]
        r = {"run": name}
        r["R2_logM500_mocks"] = ridge_cv_r2(x[mocks], np.log10(m["M500c_Msun"].to_numpy()), m["group"].to_numpy())
        cl = df["source"].eq("TNG-Cluster").to_numpy()
        tc = df[cl].merge(cool, on="halo_id", how="left")["central_cooling_time_gyr_z0"].to_numpy()
        r["R2_logtcool_TNGCluster"] = ridge_cv_r2(x[cl], np.log10(tc), df[cl]["group"].to_numpy())
        logc = np.log10(df["c40_250"].where(df["c40_250"] > 0)).to_numpy()
        r["R2_logc_all"] = ridge_cv_r2(x, logc, df["group"].to_numpy())
        deep = np.where(mocks & (df["exposure_ks"] == 100).to_numpy())[0]
        sim = x[deep] @ x[deep].T
        np.fill_diagonal(sim, -np.inf)
        nearest = deep[np.argmax(sim, axis=1)]
        r["same_halo_nn_fraction"] = float(np.mean(df["group"].to_numpy()[nearest] == df["group"].to_numpy()[deep]))
        rows.append(r)
        print(r, flush=True)
    out = ROOT / "outputs" / "figures" / "simclr"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "positive_controls.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("train")
    t.add_argument("--train-on", choices=["mocks", "lemur"], default="mocks")
    t.add_argument("--config", default="harmonized_physical")
    t.add_argument("--epochs", type=int, default=150)
    t.add_argument("--batch-size", type=int, default=256)
    t.add_argument("--lr", type=float, default=1e-3)
    t.add_argument("--temperature", type=float, default=0.2)
    t.add_argument("--seed", type=int, default=0)
    e = sub.add_parser("embed")
    e.add_argument("--train-on", choices=["mocks", "lemur"], default="mocks")
    v = sub.add_parser("validate")
    v.add_argument("--runs", nargs="*", default=["harmonized_physical", "simclr_mocks"])
    args = parser.parse_args(argv)
    {"train": train, "embed": embed, "validate": validate}[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
