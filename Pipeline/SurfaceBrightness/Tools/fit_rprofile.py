'''
Script to fit a single King Beta Model using a pre-created radial SB profile
'''
from sherpa.plot import DataPlot
from sherpa.astro.all import *
from sherpa.astro.ui import *
from pychips.all import *
from sherpa.all import *
import os



def profile1(scaling,model_type='single'):
    # Create basic profile
    load_data(1,'rprofile_rmid_data.fits', 3, ["RMID","SUR_BRI","SUR_BRI_ERR"])
    #Single Fit
    set_source("beta1d.src1")
    data = get_data()
    data.x = data.x*scaling #now in kpc
    set_method('moncar')
    fit()
    plot_fit_delchi()
    set_current_plot("plot1")
    log_scale(XY_AXIS)
    set_plot_title("")
    set_plot_ylabel("photons s^{-1} cm^{-2} arcsec^{-2}")
    set_current_plot("plot2")
    set_plot_xlabel("R (kpc)")
    print_window("Single_Beta.png",['clobber','true'])
    covar()
    with open(os.getcwd()+'/Beta1.out','w+') as res_out:
        res_out.write(str(get_covar_results()))
    return None
def profile2(scaling,model_type='single'):
    #stats, accept, params = get_draws(niter=1e4)
    #Double Fit
    load_data(1,'rprofile_rmid_data.fits', 3, ["RMID","SUR_BRI","SUR_BRI_ERR"])
    set_source("beta1d.src1+beta1d.src2")
    data = get_data()
    data.x = data.x*scaling #now in kpc
    set_method('moncar')
    fit()
    plot_fit_delchi()
    set_current_plot("plot1")
    log_scale(XY_AXIS)
    set_plot_title("")
    set_plot_ylabel("photons s^{-1} cm^{-2} arcsec^{-2}")
    set_current_plot("plot2")
    set_plot_xlabel("R (kpc)")
    print_window("Double_Beta.png",['clobber','true'])
    covar()
    with open(os.getcwd()+'/Beta2.out','w+') as res_out:
        res_out.write(str(get_covar_results()))
    return None
