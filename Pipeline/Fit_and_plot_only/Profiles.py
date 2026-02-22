"""
Python file to create temperature profile
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from LSCalc import ls_calc


def all_profiles(data_folder, output_folder, redshift):
    properties = {
        "Temperature": "keV",
        "Density": "$cm^{-3}$",
        "Pressure": "$erg cm^{-3}$",
        "Entropy": "$keV cm^{2}$",
        "T_Cool": "years",
    }
    for key, val in properties.items():
        profile(data_folder, output_folder, redshift, key, val)
    return None


def profile(data_folder, output_folder, redshift, property, units):
    data_file = pd.read_csv(data_folder + "/annuli_data.csv")
    data = data_file[property]
    min_ = pd.read_csv(data_folder + "/annuli_data_min.csv")
    min_ = min_[property]
    max_ = pd.read_csv(data_folder + "/annuli_data_max.csv")
    max_ = max_[property]
    region_init = data_file["Region"]
    regions = []
    arcsec_to_kpc = ls_calc(redshift, 1)  # arcsec to kpc conversion factor
    for region in region_init:
        inner = float(region.split("-")[0])
        outer = float(region.split("-")[1])
        mid_point = (inner + outer) / 2
        regions.append(mid_point * arcsec_to_kpc)
    err_min = [data[i] - min_[i] for i in range(len(min_))]
    err_max = [max_[i] - data[i] for i in range(len(max_))]
    errors = np.array([err_min, err_max])
    fig = plt.figure()
    fig.subplots_adjust(bottom=0.2, left=0.2)
    ax = fig.add_subplot(111)
    ax.errorbar(
        regions,
        data,
        yerr=errors,
        lw=0,
        elinewidth=1,
        fmt="ko",
        ecolor="green",
        color="green",
        markersize=4,
    )
    plt.title(property + " Profile")
    plt.xlabel(r"$R$ (kpc)")
    plt.ylabel(property + " (" + units + ")")
    if property == "Density":
        plt.yscale("log")
    ax.yaxis.label.set_fontsize(12)
    ax.xaxis.label.set_fontsize(12)
    plt.savefig(output_folder + "/" + property + "_profile.png")
