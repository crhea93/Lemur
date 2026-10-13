"""Run CIAO's merge_obs with its image co-add done a few images at a time.

merge_obs adds up the per-ObsID images of a band with one dmimgcalc call for
up to 100 images, which holds them all in memory: about (12 + 2 N) times the
image size by CIAO's own estimate (fluximage.Project_Memory_Use), 58 GB for
M31's 107 ObsIDs at native resolution. CIAO's co-add can work in chunks, and
flux_obs uses that when memory is short, but merge_obs has no parameter for
it. This sets the chunk size and then runs merge_obs unchanged:

    python merge_obs_chunked.py NCHUNK <merge_obs arguments>
"""

import runpy
import shutil
import sys

import ciao_contrib._tools.merging as merging

_merge = merging.merge


def main():
    nchunk = int(sys.argv[1])

    def merge(*args, **kwargs):
        kwargs["counts_nchunk"] = nchunk
        return _merge(*args, **kwargs)

    merging.merge = merge  # merge_obs calls merging.merge(...) by attribute
    tool = shutil.which("merge_obs")
    sys.argv = [tool, *sys.argv[2:]]
    runpy.run_path(tool, run_name="__main__")


if __name__ == "__main__":
    main()
