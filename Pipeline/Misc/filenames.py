"""
Small script to collect all relavent file names
"""

import os
import re


def _files(directory):
    """Directory listing without the e1 set of interleaved-mode ObsIDs.

    Interleaved (alternating exposure) observations ship two file sets,
    ..._e1_evt1.fits (short frames) and ..._e2_evt1.fits (long frames, almost
    all of the exposure). Mixing them (e.g. an e2 evt1 with an e1 flt1)
    empties the cleaned event file, so use the e2 set only.
    """
    files = os.listdir(directory)
    if any("_e2_" in f for f in files):
        files = [f for f in files if "_e1_" not in f]
    return files


def get_filenames():
    """
    Collect all relevant files for reduction/analysis and place into a dictionary
    """
    filenames = dict()
    biases = []
    for file in _files(os.getcwd() + "/primary"):
        if file.endswith("_evt2.fits"):
            filenames["evt2"] = os.getcwd() + "/primary/" + file
        if file.endswith("_asol1.fits"):
            filenames["asol1"] = os.getcwd() + "/primary/" + file
    for file in _files(os.getcwd() + "/secondary"):
        if file.endswith("_msk1.fits"):
            filenames["msk1"] = os.getcwd() + "/secondary/" + file
        if file.endswith("_stat1.fits"):
            filenames["stat1"] = os.getcwd() + "/secondary/" + file
        if file.endswith("_pbk0.fits"):
            filenames["pbk0"] = os.getcwd() + "/secondary/" + file
        if file.endswith("_evt1.fits"):
            filenames["evt1"] = os.getcwd() + "/secondary/" + file
        if file.endswith("_mtl1.fits"):
            filenames["mtl1"] = os.getcwd() + "/secondary/" + file
        if file.endswith("_flt1.fits"):
            filenames["flt1"] = os.getcwd() + "/secondary/" + file
        if file.endswith("_bias0.fits"):
            bias_number = file.split("_")[1]
            filenames[bias_number + "_bias0"] = os.getcwd() + "/secondary/" + file
            biases.append(bias_number)
    return filenames, biases


_OBI_FILE = re.compile(r"_(\d{3})N\d+_(evt1|flt1|msk1|mtl1|stat1|asol1)\.fits$")
_TIME_FILE = re.compile(r"^acisf(\d+)N\d+(?:_(\d)_bias0|_pbk0)\.fits$")


def get_segments():
    """Group an ObsID's files by observation segment (OBI), from the ObsID dir.

    Multi-OBI observations ship one evt1/flt1/msk1/mtl1/stat1/asol1 set per
    segment (named ..._001N004_evt1.fits, ..._002N005_evt1.fits); bias0 and
    pbk0 files are named by time instead and are assigned to the segment whose
    start time is nearest. Returns [] for ordinary single-segment ObsIDs.
    """
    from astropy.io import fits

    segments = {}
    for subdir in ("primary", "secondary"):
        for file in sorted(os.listdir(os.getcwd() + "/" + subdir)):
            match = _OBI_FILE.search(file)
            if match:
                code, kind = match.groups()
                path = os.getcwd() + "/" + subdir + "/" + file
                seg = segments.setdefault(code, {"code": code, "asol1": []})
                if kind == "asol1":
                    seg["asol1"].append(path)
                else:
                    seg[kind] = path
    segments = {
        code: seg for code, seg in segments.items() if "evt1" in seg and "flt1" in seg
    }
    if len(segments) < 2:
        return []

    for seg in segments.values():
        header = fits.getheader(seg["evt1"], "EVENTS")
        seg["tstart"], seg["tstop"] = float(header["TSTART"]), float(header["TSTOP"])
        seg["biases"] = {}

    def nearest(t):
        return min(segments.values(), key=lambda seg: abs(seg["tstart"] - t))

    for file in sorted(os.listdir(os.getcwd() + "/secondary")):
        match = _TIME_FILE.match(file)
        if not match:
            continue
        seg = nearest(float(match.group(1)))
        path = os.getcwd() + "/secondary/" + file
        if match.group(2):
            seg["biases"][match.group(2)] = path
        else:
            seg["pbk0"] = path
    return sorted(segments.values(), key=lambda seg: seg["tstart"])
