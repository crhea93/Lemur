'''
------------------------------------------------------
GOAL:
    Step through bins (spectra) and calculate the temperature value
    of each bin using XSPEC
------------------------------------------------------
INPUTS:
    dir - Full Path to Main Directory (e.g. '/home/user/Documents/Chandra/12833/repro/binned/')
    file_name - FIlename of PI/PHA spectrum (e.g. 'imageA')
    output_file - Filename for output containing temperature information (e.g. 'Temp_bin')
    num_files - number of bins (e.g. 100)
    redshift - redshift of object (e.g. 0.659)
    n_H - Hydrogen Equivalent Column Density in units of 10^{22} atoms cm^{-2} (e.g. 3.6e-2)
    Temp_guess - Guess for Temperature value in units of KeV (e.g. 5)
------------------------------------------------------
OUTPUTS:
    A file which contains the bin number and associated
    temperature and reduced chi-squared
------------------------------------------------------

------------------------------------------------------
'''
#from astropy.io import fits
import os
import subprocess
from sherpa.optmethods import LevMar
from sherpa.stats import LeastSq
from sherpa.plot import DataPlot
from sherpa.astro.xspec import *
from sherpa.astro.all import *
from sherpa.astro.ui import *
from pychips.all import *
from sherpa.fit import *
from sherpa.all import *
#TURN OFF ON-SCREEN OUTPUT FROM SHERPA
import logging
logger = logging.getLogger("sherpa")
logger.setLevel(logging.WARN)
logger.setLevel(logging.ERROR)
from sherpa_contrib.xspec.xsconvolve import load_xscflux
load_xscflux("cflux")
#------------------------------INPUTS------------------------------------------#
energy_min = 0.5
energy_max = 7.0
energy_flux_min = 0.01
energy_flux_max = 100.00
grouping = 10
statistic = 'cstat'
optimization = 'levmar'
#------------------------------------------------------------------------------#
def set_log_sherpa():
    p = get_data_plot_prefs()
    p["xlog"] = True
    p["ylog"] = True
    return None

def isFloat(string):
    if string == None:
        return False
    try:
        float(string)
        return True
    except ValueError:
        return False
    except TypeError:
        return False

#Dynamically set source for OBSID
def obsid_set(src_model_dict,bkg_model_dict,obsid, obs_count,redshift,nH_val,Temp_guess):
    load_pha(obs_count,obsid) #Read in
    if obs_count == 0:
        src_model_dict[obsid] = xsphabs('abs'+str(obs_count)) * xsapec('apec'+str(obs_count)) #set model and name
    else:
        src_model_dict[obsid] = get_model_component('abs0') * xsapec('apec' + str(obs_count))
        get_model_component('apec'+str(obs_count)).kT = get_model_component('apec0').kT #link to first kT
        get_model_component('apec' + str(obs_count)).Abundanc = get_model_component('apec0').Abundanc  # link to first kT
    bkg_model_dict[obsid] = xsapec('bkgApec'+str(obs_count))+get_model_component('abs0')*xsbremss('brem'+str(obs_count))
    set_source(obs_count, src_model_dict[obsid]) #set model to source
    set_bkg_model(obs_count,bkg_model_dict[obsid])
    #Change src model component values
    get_model_component('abs0').nH = nH_val#change preset value
    freeze(get_model_component('abs0'))
    get_model_component('apec'+str(obs_count)).kT = Temp_guess
    get_model_component('apec' + str(obs_count)).kT = redshift
    get_model_component('apec' + str(obs_count)).Abundanc = 0.3
    thaw(get_model_component('apec'+str(obs_count)).Abundanc)
    #Change bkg model component values
    get_model_component('bkgApec' + str(obs_count)).kT = 0.18
    thaw(get_model_component('bkgApec'+str(obs_count)).kT)
    get_model_component('brem' + str(obs_count)).kT = 40.0
    thaw(get_model_component('brem' + str(obs_count)).kT)
    return None

#Get ready for flux calculations
def flux_prep(src_model_dict,obsid,obs_count):
    freeze(get_model_component('apec'+str(obs_count)).kT)
    freeze(get_model_component('apec'+str(obs_count)).Abundanc)
    freeze(get_model_component('bkgApec'+str(obs_count)).norm)
    freeze(get_model_component('brem'+str(obs_count)).norm)
    src_model_dict[obsid] = get_model_component('abs0')*cflux(get_model_component('apec'+str(obs_count)))
    return None

#FitXSPEC
# Fit spectra
#   parameters:
#       spectrum_file = Name of combined spectra File
#       background_file = Name of associated background file
#       arf_file = Name of associated arf file
#       resp_file = Name of associated rmf file
#       redshift = redshift of object
#       n_H = Hydrogen Equivalent Column Density
#       Temp_guess = Guess for Temperature value
def FitXSPEC(spectrum_files,background_files,redshift,n_H,Temp_guess,spec_count,sigma_covar):
    #FIX HEADER
    set_stat(statistic)
    set_method(optimization)
    ignore(0,energy_min)
    ignore(energy_max,)
    #group_counts(1,grouping)
    #---------------Set source with background------------#
    cflux.emin = energy_flux_min
    cflux.emax = energy_flux_max
    src_model_dict = {}; bkg_model_dict = {}
    obs_count = 0
    for spec_pha in spectrum_files:
        obsid_set(src_model_dict, bkg_model_dict, spec_pha, obs_count, redshift, n_H, Temp_guess)
        obs_count += 1
    for ob_num in obs_count:
        group_counts(ob_num,grouping)
    '''set_source(1 , xsphabs.abs1*xsapec.mekal1)
    set_bkg_model(1, xsapec.apec1 + abs1 * xsbremss.brem1)
    apec1.kT = 0.18;
    freeze(apec1.kT);
    brem1.kT = 40;
    freeze(brem1.kT)
    abs1.nH = n_H; freeze(abs1.nH)
    mekal1.kT = Temp_guess
    mekal1.Abundanc = 0.3
    thaw(mekal1.Abundanc)
    mekal1.redshift = redshift'''
    fit()
    set_covar_opt("sigma",sigma_covar)
    #covar(mekal1.kT,mekal1.Abundanc,mekal1.norm)
    covar(get_model_component('apec0').kT,get_model_component('apec0').Abundanc,get_model_component('apec0').norm)
    #----------Calculate min/max values---------#
    mins = list(get_covar_results().parmins)
    maxes = list(get_covar_results().parmaxes)
    for val in range(len(mins)):
        if isFloat(mins[val]) == False:
            mins[val] = 0.0
        if isFloat(maxes[val]) == False:
            maxes[val] = 0.0
        else:
            pass
    #---------Set up Flux Calculation----------#
    freeze(get_model_component('apec0').kT);freeze(get_model_component('apec0').Abundanc);
    #set_source(1 , xsphabs.abs1*cflux(xsapec.mekal1))
    for spec_pha in spectrum_files:
        flux_prep(src_model_dict, spec_pha, obs_count)
    fit()
    set_log_sherpa()
    plot("fit", 1)
    print_window(os.getcwd()+"/Fits/%s.ps"%spec_count,['clobber','yes'])
    Temperature = mekal1.kT.val; Temp_min = mins[0]; Temp_max = maxes[0]
    Abundance = mekal1.Abundanc.val; Ab_min = mins[1]; Ab_max = maxes[1]
    Norm = mekal1.norm.val; Norm_min = mins[2]; Norm_max = maxes[2]
    Flux = cflux.lg10Flux.val
    f = get_fit_results()
    reduced_chi_sq = f.rstat
    reset(get_model()); reset(get_bkg_model())
    reset(get_source());
    delete_data()
    clean()
    #Make sure all error bounds are values
    return Temperature,Temp_min,Temp_max,Abundance,Ab_min,Ab_max,Norm,Norm_min,Norm_max,Flux,reduced_chi_sq

#PrimeFitting
# Step through spectra to fit
#   parameters:
#       dir = main Directory
#       file_name = FIlename of PI/PHA spectrum
#       output_file = Filename for output containing temperature information
#       num_files = number of bins
#       redshift = redshift of object
#       n_H = Hydrogen Equivalent Column Density
#       Temp_guess = Guess for Temperature value
def PrimeFitting(home_dir,dir,file_name,output_file,annuli_data,num_files,redshift,n_H,Temp_guess,sigma_covar):
    os.chdir(home_dir+'/'+dir[0])
    if not os.path.exists(os.getcwd()+'/Fits'):
        os.makedirs(os.getcwd()+'/Fits')
    if os.path.isfile(file_name) == True:
        os.remove(file_name) #remove it

    file_to_write = open(home_dir+'/'+dir[0]+"/Fits/"+output_file+".csv",'w+')
    file_to_write.write("Region,Temperature,Temp_min,Temp_max,Abundance,Ab_min,Ab_max,Norm,Norm_min,Norm_max,Flux,ReducedChiSquare \n")
    Temperatures = []; Temp_mins = []; Temp_maxes = []
    Abundances = []; Ab_mins = []; Ab_maxes = []
    Norms = []; Norm_mins = []; Norm_maxes = []
    Fluxes = []
    for i in range(num_files):
        print("      Fitting model to spectrum number "+str(i+1))
        spectrum_files = []
        background_files = []
        arf_files = []
        resp_file = []
        if i == 0:
            region_ = '0.0-'+str(annuli_data[0])
        if i > 0:
            region_ = str(annuli_data[i-1])+'-'+str(annuli_data[i])
        for directory in dir:
            spectrum_files.append(home_dir+'/'+directory+'/'+file_name+"_"+str(i+1)+".pi")
            background_files.append(home_dir+'/'+directory+'/'+file_name+"_"+str(i+1)+"_bkg.pi")
            #resp_file = file_name+"_"+str(i)+".rmf"
        Temperature,Temp_min,Temp_max,Abundance,Ab_min,Ab_max,Norm,Norm_min,Norm_max,Flux,reduced_chi_sq = FitXSPEC(spectrum_files,background_files,redshift,n_H,Temp_guess,i+1,sigma_covar)
        Temperatures.append(Temperature); Abundances.append(Abundance); Norms.append(Norm); Fluxes.append(Flux)
        Temp_mins.append(Temp_min);Ab_mins.append(Ab_min);Norm_mins.append(Norm_min)
        Temp_maxes.append(Temp_max);Ab_maxes.append(Ab_max);Norm_maxes.append(Norm_max)
        file_to_write.write(str(region_) + "," + str(Temperature) + "," + str(Temp_min)+ ","+ str(Temp_max)+',')
        file_to_write.write(str(Abundance)+ "," + str(Ab_min) + "," + str(Ab_max)+',')
        file_to_write.write(str(Norm)+ "," + str(Norm_min) + "," + str(Norm_max)+',')
        file_to_write.write(str(Flux)+','+str(reduced_chi_sq)+'\n')
    file_to_write.close()
    return Temperatures, Temp_mins, Temp_maxes, Abundances, Ab_mins, Ab_maxes, Norms, Norm_mins, Norm_maxes, Fluxes
