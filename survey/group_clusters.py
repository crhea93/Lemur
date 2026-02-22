import astropy.units as u
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord

df = pd.read_csv("galaxyClusters.csv")

# --- adjust these to your CSV headers ---
ra_col = "RA"  # strings like "03 38 29.40"
dec_col = "Dec"  # strings like "-35 27 00.40"
obsid_col = "Obs ID"

# Clean up: ensure strings, strip whitespace
ra_str = df[ra_col].astype(str).str.strip()
dec_str = df[dec_col].astype(str).str.strip()

# Parse into SkyCoord (RA is hourangle, Dec is degrees)
coords = SkyCoord(
    ra=ra_str.values, dec=dec_str.values, unit=(u.hourangle, u.deg), frame="icrs"
)

# Store decimal degrees if you want them later
df["ra_deg"] = coords.ra.deg
df["dec_deg"] = coords.dec.deg

# ---- Group within 10 arcsec (spherical), NO friends-of-friends chaining ----
max_sep = 10.0 * u.arcsec

group_ids = np.full(len(df), -1, dtype=int)
group_centers = []  # list of SkyCoord centers

for i, c in enumerate(coords):
    assigned = False
    for gid, center in enumerate(group_centers):
        if c.separation(center) <= max_sep:
            group_ids[i] = gid
            assigned = True
            break
    if not assigned:
        group_ids[i] = len(group_centers)
        group_centers.append(c)

df["group_id"] = group_ids

# Now aggregate ObsIDs per group
df[obsid_col] = pd.to_numeric(df[obsid_col], errors="coerce")

grouped = (
    df.dropna(subset=[obsid_col])
    .groupby("group_id")
    .agg(
        ra_center_deg=("ra_deg", "median"),
        dec_center_deg=("dec_deg", "median"),
        n_rows=(obsid_col, "size"),
        n_obsids=(obsid_col, "nunique"),
        obsids=(obsid_col, lambda s: sorted(set(int(x) for x in s))),
        example_target=(
            "Target Name",
            lambda s: s.dropna().astype(str).value_counts().index[0]
            if "Target Name" in df.columns and len(s.dropna())
            else "",
        ),
    )
    .reset_index()
)

print("Num groups:", grouped.shape[0])
print(grouped.head())

grouped.to_csv("clusters_grouped_within_10arcsec.csv", index=False)
