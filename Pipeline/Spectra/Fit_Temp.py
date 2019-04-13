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
from Misc.Classes import annulus
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
#-----------------------------------CLASSES------------------------------------#
class region_class:
    '''
    Class for a region including the inner/outer radius and all relevant parameters
    :param r_in - inner radius
    :param r_out - outer radius
    :param temp - temperature
    :param temp_min - min temp value
    :param temp_max - max temp value
    :param Ab - abundace
    :param Ab_min - min ab value
    :param Ab_max - max ab value
    :param norm - temperature model normalization value
    :param norm_min - min norm value
    :param norm_max - max norm value
    :param flux - flux value
    :param agn_act - notate the use of AGN in fit or no
    '''
    def __init__(self,r_in,r_out,temp,temp_min,temp_max,Ab,Ab_min,Ab_max,norm,norm_min,norm_max,flux,agn_act):
        self.r_in = r_in
        self.r_out = r_out
        self.temp = [temp_min, temp, temp_max]
        self.Ab = [Ab_min,Ab,Ab_max]
        self.norm = [norm_min,norm,norm_max]
        self.flux = flux
        self.agn_act = agn_act
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
def obsid_set(src_model_dict,bkg_model_dict,obsid, obs_count,redshift,nH_val,Temp_guess, agn):
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
        agn - boolean for additional AGN fit
    '''
    load_pha(obs_count,obsid) #Read in
    if obs_count == 1:
        if agn == False:
            src_model_dict[obsid] = xsphabs('abs'+str(obs_count)) * xsapec('apec'+str(obs_count)) #set model and name
        if agn == True:
            src_model_dict[obsid] = xsphabs('abs'+str(obs_count)) * (xsapec('apec'+str(obs_count)+ xszpowerlw('zpwd'+str(obs_count))))
            get_model_component('zpwd' + str(obs_count)).redshift = redshift
        # Change src model component values
        get_model_component('apec' + str(obs_count)).kT = Temp_guess
        get_model_component('apec' + str(obs_count)).redshift = redshift  # need to tie all together
        get_model_component('apec' + str(obs_count)).Abundanc = 0.3
        thaw(get_model_component('apec' + str(obs_count)).Abundanc)
        get_model_component('abs1').nH = nH_val  # change preset value
        freeze(get_model_component('abs1'))
    else:
        if agn == False:
            src_model_dict[obsid] = get_model_component('abs1') * xsapec('apec' + str(obs_count))
        if agn == True:
            src_model_dict[obsid] = get_model_component('abs1') * (xsapec('apec'+str(obs_count)+ xszpowerlw('zpwd'+str(obs_count))))
            get_model_component('zpwd' + str(obs_count)).redshift = redshift
        get_model_component('apec'+str(obs_count)).kT = get_model_component('apec1').kT #link to first kT
        get_model_component('apec' + str(obs_count)).redshift = redshift
        get_model_component('apec' + str(obs_count)).Abundanc = get_model_component('apec1').Abundanc  # link to first kT
    # BACKGROUND MODEL
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
def flux_prep(src_model_dict,bkg_model_dict,obsid,obs_count,agn):
    '''
    Dynamically set source and background model for obsid for FLUX calculation
    PARAMETERS:
        src_model_dict - dictionary of source models for each obsid
        bkg_model_dict - dictionary of background models for each obsid
        obsid - current Chandra observation ID
        obs_count - current number of Chandra observation ID out of all IDs
        agn - boolean for additional AGN fit
    '''
    #freeze(get_model_component('bkgApec'+str(obs_count)).norm)
    #freeze(get_model_component('brem'+str(obs_count)).norm)
    if agn == False:
        src_model_dict[obsid] = get_model_component('abs1')*cflux(get_model_component('apec'+str(obs_count)))
    if agn == True:
        src_model_dict[obsid] = get_model_component('abs1')*(cflux(get_model_component('apec'+str(obs_count)))+get_model_component('zpwd'+str(obs_count)))
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


def FitXSPEC(spectrum_files,background_files,Ann_cur, redshift,n_H,Temp_guess,spec_count,sigma_covar,agn=False):
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
        agn - boolean for additional AGN fit
    '''
    #FIX HEADER
    set_stat(statistic)
    set_method(optimization)
    #---------------Set source with background------------#
    cflux.Emin = energy_flux_min
    cflux.Emax = energy_flux_max
    src_model_dict = {}; bkg_model_dict = {}
    obs_count = 1
    for obsid in spectrum_files:
        obsid_set(src_model_dict, bkg_model_dict, obsid, obs_count, redshift, n_H, Temp_guess, agn)
        obs_count += 1
    for ob_num in range(obs_count-1):
        group_counts(ob_num+1,grouping)
        notice_id(ob_num+1, energy_min, energy_max)
    fit()#outfile=os.getcwd()+'/Fits/%s.out'%spec_count,clobber=True)
    f = get_fit_results()
    with open(os.getcwd() + '/Fits/Params/%s.out'%spec_count, 'w+') as res_out:
        res_out.write(str(f))
    set_log_sherpa()
    os.makedirs(os.getcwd() + "/Fits/Spectra/Annulus_%s" % spec_count)
    src_ids = list_data_ids()
    ct = 0
    for id_ in src_ids:
        plot("fit",id_,"resid",id_)
        obsid_val = str(spectrum_files[id_-1].split('/')[-4])
        print_window(os.getcwd() + "/Fits/Spectra/Annulus_%s/%s.png" % (spec_count,obsid_val), ['clobber', 'yes'])
    set_covar_opt("sigma",sigma_covar)
    covar(get_model_component('apec1').kT,get_model_component('apec1').Abundanc)
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
    #Calculate norm as average value
    Norm = 0; Norm_min = 0; Norm_max = 0
    for id_ in src_ids:
        Norm += get_model_component('apec'+str(id_)).norm.val #add up values
        #get errors
        covar(get_model_component('apec'+str(id_)).norm)
        mins = list(get_covar_results().parmins)
        maxes = list(get_covar_results().parmaxes)
        if isFloat(mins) == False:
            mins = 0.0
        elif isFloat(maxes) == False:
            maxes = 0.0
        Norm_min += mins
        Norm_max += maxes
    Norm = Norm/len(src_ids)
    Norm_min = Norm_min/len(src_ids)
    Norm_max = Norm_max/len(src_ids)
    #---------Set up Flux Calculation----------#
    freeze(get_model_component('apec1').kT);freeze(get_model_component('apec1').Abundanc);
    obs_count = 1
    for obsid in spectrum_files:
        flux_prep(src_model_dict,bkg_model_dict, obsid, obs_count, agn)
        obs_count += 1
    #switch to more robust fitting method
    set_method('neldermead')
    cflux.lg10Flux.val = -13.5 #initial guess
    fit()#outfile=os.getcwd()+'/Fits/%s_flux.out'%spec_count,clobber=True)
    set_log_sherpa()
    src_ids = list_data_ids()
    for id_ in src_ids:
        plot("fit",id_,"resid",id_)
        obsid_val = str(spectrum_files[id_-1].split('/')[-4])
        print_window(os.getcwd() + "/Fits/Spectra/Annulus_%s/%s_flux.png" % (spec_count,obsid_val), ['clobber', 'yes'])
    Flux = cflux.lg10Flux.val
    f = get_fit_results()
    with open(os.getcwd()+'/Fits/Params/%s_flux.out'%spec_count,'w+') as res_out:
        res_out.write(str(f))
    reduced_chi_sq = f.rstat
    '''reset(get_model()); reset(get_bkg_model())
    reset(get_source());
    delete_data()'''
    clean()
    Ann_cur.add_fit_data(Temperature,Temp_min,Temp_max,Abundance,Ab_min,Ab_max,Norm,Norm_min,Norm_max,Flux,reduced_chi_sq,agn)
    return None


def PrimeFitting(home_dir,merge_dir,dir,file_name,output_file,annuli_data,num_files,redshift,n_H,Temp_guess,sigma_covar,agn_):
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
        agn_ - AGN class instance
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
    Annuli_ = []
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
        #check if AGN is active and if it is in the current region
        if agn_ == True and agn_.radius > float(region_.split('-')[0]):
            #now we need to do two fits: one with and one without the AGN
            for i in range(2):
                Ann_cur = annulus(float(region_.split('-')[0]),float(region_.split('-')[1]))
                if i == 0: #include AGN
                    FitXSPEC(spectrum_files,background_files,Ann_cur,redshift,n_H,Temp_guess,i+1,sigma_covar,agn = True)
                    Annuli_.append(Ann_cur)
                if i == 1: #dont include AGN
                    FitXSPEC(spectrum_files,background_files,Ann_cur,redshift,n_H,Temp_guess,i+1,sigma_covar)
                    Annuli_.append(Ann_cur)
        else:
            Ann_cur = annulus(float(region_.split('-')[0]),float(region_.split('-')[1]))
            FitXSPEC(spectrum_files,background_files,Ann_cur,redshift,n_H,Temp_guess,i+1,sigma_covar)
            Annuli_.append(Ann_cur)
    return Annuli_
