'''
Python file to create radial profiles
'''
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from Misc.LSCalc import ls_calc

def all_profiles(data_folder,output_folder,redshift):
    '''
    Define the properties that we want a profile for along with their units
    PARAMETERS:
        data_folder - location of csv files containing data and errors
        output_folder - output directory of plots
        redshift - redshift of object
    '''
    properties = {"Temperature":'keV','Abundance':'$Z/Z_{\odot}$','Density':'$cm^{-3}$','Pressure':'$erg cm^{-3}$','Entropy':'$keV cm^{2}$','T_Cool':'Gyr'}
    for key,val in properties.items():
        profile(data_folder,output_folder,redshift,key,val)
    return None


def profile(data_folder,output_folder,redshift,property,units):
    '''
    Create radial profiles for several parameters
    PARAMETERS:
        data_folder - location of csv files containing data and errors
        output_folder - output directory of plots
        redshift - redshift of object
        property - Name of the property
        units - Units of property
    '''
    #Read in data and errors
    data_file = pd.read_csv(data_folder+'/annuli_data.csv')
    data = data_file[property]
    min_ = pd.read_csv(data_folder+'/annuli_data_min.csv')
    min_ = min_[property]
    max_ = pd.read_csv(data_folder+'/annuli_data_max.csv')
    max_ = max_[property]
    r_in = data_file['R_in']
    r_out = data_file['R_out']
    regions = []
    arcsec_to_kpc = ls_calc(redshift,1)#arcsec to kpc conversion factor
    #Grab region info
    for region_ct in range(len(r_in)):
        mid_point = float((float(r_in[region_ct])+float(r_out[region_ct])))/2
        regions.append(mid_point*arcsec_to_kpc)
    #Error info

    #Pick out AGN vs Non-AGN
    agn_bool = data_file['AGN']
    AGN_regions = []; NonAGN_regions = []
    AGN_data = []; NonAGN_data = []
    AGN_min = []; NonAGN_min = []
    AGN_max = []; NonAGN_max = []
    for count in range(len(agn_bool)):
        if agn_bool[count] == 'yes':
            AGN_regions.append(regions[count])
            AGN_data.append(data[count])
            AGN_min.append(min_[count])
            AGN_max.append(max_[count])
        if agn_bool[count] == 'no':
            NonAGN_regions.append(regions[count])
            NonAGN_data.append(data[count])
            NonAGN_min.append(min_[count])
            NonAGN_max.append(max_[count])
    #now get errors
    err_min = [AGN_data[i]-AGN_min[i] for i in range(len(AGN_min))]
    err_max = [AGN_max[i]-AGN_data[i] for i in range(len(AGN_max))]
    AGN_errors = np.array([err_min,err_max])
    err_min = [data[i]-NonAGN_min[i] for i in range(len(NonAGN_min))]
    err_max = [NonAGN_max[i]-data[i] for i in range(len(NonAGN_max))]
    NonAGN_errors = np.array([err_min,err_max])
    #plotting
    fig = plt.figure()
    fig.subplots_adjust(bottom=0.2,left=0.2)
    ax = fig.add_subplot(111)
    ax.errorbar(AGN_regions,AGN_data,yerr=AGN_errors,lw=0,elinewidth=1,fmt='ko',ecolor='C0',color='C0',markersize=4,label='AGN+ICM')
    ax.errorbar(NonAGN_regions,NonAGN_data,yerr=NonAGN_errors,lw=0,elinewidth=1,fmt='ko',ecolor='green',color='green',markersize=4,label='AGN')
    plt.title(property+" Profile")
    plt.xlabel(r'$R$ (kpc)')
    plt.ylabel(property+' ('+units+')')
    if property == 'Density':
        plt.yscale('log')
    ax.yaxis.label.set_fontsize(12)
    ax.xaxis.label.set_fontsize(12)
    plt.legend()
    plt.savefig(output_folder+"/"+property+"_profile.png")
