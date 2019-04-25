'''
Calculate Cooling Radius defined at 3 Gyr for Non AGN fits
'''
import numpy as np
import pandas as pd
from scipy import interpolate
from Misc.LSCalc import ls_calc
def R_cool_calc(data_folder,redshift,main_out):
    data_file = pd.read_csv(data_folder+'/annuli_data.csv')
    data = data_file['T_Cool']
    r_in = data_file['R_in']
    r_out = data_file['R_out']
    agn_ = data_file['AGN']
    regions = []
    NonAGN_data = [];
    arcsec_to_kpc = ls_calc(redshift,1)#arcsec to kpc conversion factor
    for region in range(len(r_in)):
        if agn_[region] == 'no':
            inner = r_in[region]
            outer = r_out[region]
            mid_point = (inner+outer)/2
            regions.append(mid_point*arcsec_to_kpc)
            NonAGN_data.append(data[region])
    f = interpolate.UnivariateSpline(regions, NonAGN_data, s=10)
    yToFind = 3
    yreduced = np.array(NonAGN_data) - yToFind
    freduced = interpolate.UnivariateSpline(regions, yreduced, s=0)
    R_cool_3 = freduced.roots()[0]
    main_out.write("The Cooling Radius at 3 Gyr is %.2fkpc\n"%R_cool_3)
    yToFind = 7.7
    yreduced = np.array(NonAGN_data) - yToFind
    freduced = interpolate.UnivariateSpline(regions, yreduced, s=0)
    if len(freduced.roots()) > 0:
        R_cool_7 = freduced.roots()[0]
        main_out.write("The Cooling Radius at 7.7 Gyr is %.2fkpc\n"%R_cool_7)
    else:
        main_out.write("We are unable to calculate the 7.7 Gyr Cooling Radius.")
    return None
