"""
Script to fit a single King Beta Model using a pre-created radial SB profile
"""

import os

import matplotlib.pyplot as plt
from sherpa.all import *
from sherpa.astro.all import *
from sherpa.astro.ui import *


def profile1(scaling, model_type="single"):
    # Create basic profile
    load_data(1, "rprofile_rmid_data.fits", 3, ["RMID", "SUR_BRI", "SUR_BRI_ERR"])
    # Single Fit
    set_source("beta1d.src1")
    get_data()
    set_method("moncar")
    fit()
    data_plot = get_data_plot()
    model_plot = get_model_plot()
    delchi_plot = get_delchi_plot()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 7))
    ax1.errorbar(
        data_plot.x,
        data_plot.y,
        yerr=data_plot.yerr,
        fmt=".",
        color="#f5f7ff",
        alpha=0.85,
    )
    ax1.plot(model_plot.x, model_plot.y, color="#47f5ff", linewidth=1.5)
    ax1.set_ylabel("photons s$^{-1}$ cm$^{-2}$ arcsec$^{-2}$")
    if (data_plot.x > 0).all() and (data_plot.y > 0).all() and (model_plot.y > 0).all():
        ax1.set_xscale("log")
        ax1.set_yscale("log")

    ax2.errorbar(
        delchi_plot.x,
        delchi_plot.y,
        yerr=delchi_plot.yerr,
        fmt=".",
        color="#ff4fd8",
        alpha=0.85,
    )
    ax2.axhline(0, color="#f5f7ff", linewidth=0.8, alpha=0.6)
    ax2.set_xlabel("R (kpc)")
    ax2.set_ylabel("Delchi")

    fig.tight_layout()
    fig.savefig("Single_Beta.png", dpi=150)
    plt.close(fig)
    covar()
    with open(os.getcwd() + "/Beta1.out", "w+") as res_out:
        res_out.write(str(get_covar_results()))
    return None


def profile2(scaling, model_type="single"):
    # stats, accept, params = get_draws(niter=1e4)
    # Double Fit
    load_data(1, "rprofile_rmid_data.fits", 3, ["RMID", "SUR_BRI", "SUR_BRI_ERR"])
    set_source("beta1d.src1+beta1d.src2")
    get_data()
    set_method("moncar")
    fit()
    data_plot = get_data_plot()
    model_plot = get_model_plot()
    delchi_plot = get_delchi_plot()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6, 7))
    ax1.errorbar(
        data_plot.x,
        data_plot.y,
        yerr=data_plot.yerr,
        fmt=".",
        color="#f5f7ff",
        alpha=0.85,
    )
    ax1.plot(model_plot.x, model_plot.y, color="#47f5ff", linewidth=1.5)
    ax1.set_ylabel("photons s$^{-1}$ cm$^{-2}$ arcsec$^{-2}$")
    if (data_plot.x > 0).all() and (data_plot.y > 0).all() and (model_plot.y > 0).all():
        ax1.set_xscale("log")
        ax1.set_yscale("log")

    ax2.errorbar(
        delchi_plot.x,
        delchi_plot.y,
        yerr=delchi_plot.yerr,
        fmt=".",
        color="#ff4fd8",
        alpha=0.85,
    )
    ax2.axhline(0, color="#f5f7ff", linewidth=0.8, alpha=0.6)
    ax2.set_xlabel("R (kpc)")
    ax2.set_ylabel("Delchi")

    fig.tight_layout()
    fig.savefig("Double_Beta.png", dpi=150)
    plt.close(fig)
    covar()
    with open(os.getcwd() + "/Beta2.out", "w+") as res_out:
        res_out.write(str(get_covar_results()))
    return None
