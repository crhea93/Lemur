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
import shutil
import glob
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
energy_flux_min = 0.1
energy_flux_max = 50.00
grouping = 10
statistic = 'chi2gehrels'
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
    '''
    Dynamically set source and background model for obsid
    PARAMETERS:
        src_model_dict - dictionary of source models for each obsid
        bkg_model_dict - dictionary of background models for each obsid
        obsid - current Chandra observation ID
        obs_count - current number of Chandra observation ID out of all IDs
        redshift - cluster redshift value
        nH_val - Column density value in the direction of the cluster
        Temp_guess - Initial temperature guess for region
    '''
    load_pha(obs_count,obsid) #Read in
    if obs_count == 1:
        src_model_dict[obsid] = xsphabs('abs'+str(obs_count)) * xsapec('apec'+str(obs_count)) #set model and name
        # Change src model component values
        get_model_component('apec' + str(obs_count)).kT = Temp_guess
        get_model_component('apec' + str(obs_count)).redshift = redshift  # need to tie all together
        get_model_component('apec' + str(obs_count)).Abundanc = 0.3
        thaw(get_model_component('apec' + str(obs_count)).Abundanc)
        get_model_component('abs1').nH = nH_val  # change preset value
        freeze(get_model_component('abs1'))
    else:
        src_model_dict[obsid] = get_model_component('abs1') * xsapec('apec' + str(obs_count))
        get_model_component('apec'+str(obs_count)).kT = get_model_component('apec1').kT #link to first kT
        get_model_component('apec' + str(obs_count)).redshift = redshift
        get_model_component('apec' + str(obs_count)).Abundanc = get_model_component('apec1').Abundanc  # link to first kT

    bkg_model_dict[obsid] = xsapec('bkgApec'+str(obs_count))+get_model_component('abs1')*xsbremss('brem'+str(obs_count))
    set_source(obs_count, src_model_dict[obsid]) #set model to source
    set_bkg_model(obs_count,bkg_model_dict[obsid])
    #Change bkg model component values
    get_model_component('bkgApec' + str(obs_count)).kT = 0.18
    freeze(get_model_component('bkgApec'+str(obs_count)).kT)
    get_model_component('brem' + str(obs_count)).kT = 40.0
    freeze(get_model_component('brem' + str(obs_count)).kT)
    return None

#Get ready for flux calculations
def flux_prep(src_model_dict,bkg_model_dict,obsid,obs_count):
    '''
    Dynamically set source and background model for obsid for FLUX calculation
    PARAMETERS:
        src_model_dict - dictionary of source models for each obsid
        bkg_model_dict - dictionary of background models for each obsid
        obsid - current Chandra observation ID
        obs_count - current number of Chandra observation ID out of all IDs
    '''
    #freeze(get_model_component('bkgApec'+str(obs_count)).norm)
    #freeze(get_model_component('brem'+str(obs_count)).norm)
    src_model_dict[obsid] = get_model_component('abs1')*cflux(get_model_component('apec'+str(obs_count)))
    bkg_model_dict[obsid] = get_model_component('bkgApec' + str(obs_count)) + get_model_component('abs1') * get_model_component(
        'brem' + str(obs_count))
    set_source(obs_count, src_model_dict[obsid])  # set model to source
    set_bkg_model(obs_count, bkg_model_dict[obsid])
    freeze(get_model_component('apec' + str(obs_count)).kT)
    freeze(get_model_component('apec' + str(obs_count)).Abundanc)
    # Change bkg model component values
    get_model_component('bkgApec' + str(obs_count)).kT = 0.18
    freeze(get_model_component('bkgApec' + str(obs_count)).kT)
    get_model_component('brem' + str(obs_count)).kT = 40.0
    freeze(get_model_component('brem' + str(obs_count)).kT)

    return None


def FitXSPEC(spectrum_files,background_files,redshift,n_H,Temp_guess,spec_count,sigma_covar):
    '''
    Fit spectra
    PARAMETERS:
        spectrum_file - Name of combined spectra File
        background_file - Name of associated background file
        arf_file - Name of associated arf file
        resp_file - Name of associated rmf file
        redshift - redshift of object
        n_H - Hydrogen Equivalent Column Density
        Temp_guess - Guess for Temperature value
        spec_count - current spectra/annulus number
        sigma_covar - error estimate confidence level
    '''
    #FIX HEADER
    set_stat(statistic)
    set_method(optimization)
    #---------------Set source with background------------#
    cflux.Emin = energy_flux_min
    cflux.Emax = energy_flux_max
    src_model_dict = {}; bkg_model_dict = {}
    obs_count = 1
    for spec_pha in spectrum_files:
        obsid_set(src_model_dict, bkg_model_dict, spec_pha, obs_count, redshift, n_H, Temp_guess)
        obs_count += 1
    for ob_num in range(obs_count-1):
        group_counts(ob_num+1,grouping)
        notice_id(ob_num+1, energy_min, energy_max)
    fit()#outfile=os.getcwd()+'/Fits/%s.out'%spec_count,clobber=True)
    f = get_fit_results()
    with open(os.getcwd() + '/Fits/Params/%s.out'%spec_count, 'w+') as res_out:
        res_out.write(str(f))
    set_log_sherpa()
    plot("fit")
    print_window(os.getcwd() + "/Fits/Spectra/%s.png" % spec_count, ['clobber', 'yes'])
    set_covar_opt("sigma",sigma_covar)
    covar(get_model_component('apec1').kT,get_model_component('apec1').Abundanc,get_model_component('apec1').norm)
    with open(os.getcwd()+'/Fits/Params/%s_err.out'%spec_count,'w+') as res_out:
        res_out.write(str(get_covar_results()))
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
    #Get important values
    Temperature = apec1.kT.val;
    Temp_min = mins[0];
    Temp_max = maxes[0]
    Abundance = apec1.Abundanc.val;
    Ab_min = mins[1];
    Ab_max = maxes[1]
    Norm = apec1.norm.val;
    Norm_min = mins[2];
    Norm_max = maxes[2]
    #---------Set up Flux Calculation----------#
    freeze(get_model_component('apec1').kT);freeze(get_model_component('apec1').Abundanc);
    obs_count = 1
    for spec_pha in spectrum_files:
        flux_prep(src_model_dict,bkg_model_dict, spec_pha, obs_count)
        obs_count += 1
    #switch to more robust fitting method
    set_method('neldermead')
    cflux.lg10Flux.val = -13.5 #initial guess
    fit()#outfile=os.getcwd()+'/Fits/%s_flux.out'%spec_count,clobber=True)
    set_log_sherpa()
    plot("fit")
    print_window(os.getcwd() + "/Fits/Spectra/%s_flux.png" % spec_count, ['clobber', 'yes'])
    Flux = cflux.lg10Flux.val
    f = get_fit_results()
    with open(os.getcwd()+'/Fits/Params/%s_flux.out'%spec_count,'w+') as res_out:
        res_out.write(str(f))
    reduced_chi_sq = f.rstat
    '''reset(get_model()); reset(get_bkg_model())
    reset(get_source());
    delete_data()'''
    clean()
    #Make sure all error bounds are values
    return Temperature,Temp_min,Temp_max,Abundance,Ab_min,Ab_max,Norm,Norm_min,Norm_max,Flux,reduced_chi_sq


def PrimeFitting(home_dir,merge_dir,dir,file_name,output_file,annuli_data,num_files,redshift,n_H,Temp_guess,sigma_covar):
    '''
    Step through spectra to fit
    PARAMETERS:
        dir - main Directory
        file_name - FIlename of PI/PHA spectrum
        output_file - Filename for output containing temperature information
        num_files - number of bins
        redshift - redshift of object
        n_H - Hydrogen Equivalent Column Density
        Temp_guess - Guess for Temperature value
        spec_count - current spectra/annulus number
        sigma_covar - error estimate confidence level
    '''
    os.chdir(home_dir+'/'+merge_dir)
    #Time to make a few results folders and make sure they are clean
    if not os.path.exists(os.getcwd()+'/Fits'):
        os.makedirs(os.getcwd()+'/Fits')
    if os.path.exists(os.getcwd()+'/Fits/Spectra'):
        shutil.rmtree(os.getcwd()+'/Fits/Spectra')
    if not os.path.exists(os.getcwd()+'/Fits/Spectra'):
        os.makedirs(os.getcwd()+'/Fits/Spectra')
    if os.path.exists(os.getcwd()+'/Fits/Params'):
        shutil.rmtree(os.getcwd()+'/Fits/Params')
    if not os.path.exists(os.getcwd()+'/Fits/Params'):
        os.makedirs(os.getcwd()+'/Fits/Params')
    if os.path.exists(os.getcwd()+'/Fits/Plots'):
        shutil.rmtree(os.getcwd()+'/Fits/Plots')
    if not os.path.exists(os.getcwd()+'/Fits/Plots'):
        os.makedirs(os.getcwd()+'/Fits/Plots')
    if os.path.isfile(file_name) == True:
        os.remove(file_name) #remove it
    #Create main output
    file_to_write = open(home_dir+'/'+merge_dir+"/Fits/"+output_file+".csv",'w+')
    file_to_write.write("Region,Temperature,Temp_min,Temp_max,Abundance,Ab_min,Ab_max,Norm,Norm_min,Norm_max,Flux,ReducedChiSquare \n")
    Temperatures = []; Temp_mins = []; Temp_maxes = []
    Abundances = []; Ab_mins = []; Ab_maxes = []
    Norms = []; Norm_mins = []; Norm_maxes = []
    Fluxes = []
    #Fit spectra to each annulus
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
