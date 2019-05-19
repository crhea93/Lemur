'''
Analysis of aprates data to calculate surface brightness concentration bounds

INPUTS:
    chandra_dir -- full path to directory contianing data (i.e. '/home/user/Documents/Data')
    merge_dir -- name of merged directory (e.g. 'Merged')
    region -- name of region file of interest without .reg extension (e.g. 'simple')
    quantity_to_calc -- string acronym for quantity to calculate (e.g. 'NEFA')

Options for quantity to calculate:
    NC - Net Counts
    NCR - Net Count Rates
    NPF - Net Photon Flux
    NEFA - Net Energy Flux option A
    NEFB - Net Energy Flux option B

OUTPUTS:
    Prints value and confidence bounds in terminal
'''
import os
import numpy as np
from math import ceil
from Database.Add_new import add_csb
#------------------INPUTS------------------------------------------------------#
#------------------------------------------------------------------------------#

def isfloat(value):
  try:
    float(value)
    return True
  except ValueError:
    return False
def div_with_err(val1,val2):
    try:
        value = val1/val2
        return value
    except ZeroDivisionError:
        return 1e2
def calc_bounds(mydb,mycursor,cluster_id,region1,region2,cluster_name):
    with open('aprates_'+region1+'.par') as f:
        data = []
        count = 0
        for line in f:
            if count < 35:
                val = line.split(',')[3]
                if isfloat(val) == False:
                    data.append(0)
                else:
                    data.append(val)
            count += 1
    with open('aprates_'+region2+'.par') as f:
        data2 = []
        count = 0
        for line in f:
            if count < 35:
                val = line.split(',')[3]
                if isfloat(val) == False:
                    data2.append(0)
                else:
                    data2.append(val)
            count += 1

    #Calculate count rate
    val_1 = float(data[7])
    lower_1 = float(data[8])
    upper_1 = float(data[9])
    val_2 = float(data2[7])
    lower_2 = float(data2[8])
    upper_2 = float(data2[9])
    csb_val = div_with_err(val_1,val_2)
    csb_lower = div_with_err(lower_1,upper_2)
    csb_upper = div_with_err(upper_1,lower_2)
    csb_ct = ceil(csb_val*1000)/1000
    csb_ct_l = ceil(csb_lower*1000)/1000
    csb_ct_u = ceil(csb_upper*1000)/1000
    #Calculate net photon rate
    val_1 = float(data[14])
    lower_1 = float(data[15])
    upper_1 = float(data[16])
    val_2 = float(data2[14])
    lower_2 = float(data2[15])
    upper_2 = float(data2[16])
    csb_val = div_with_err(val_1,val_2)
    csb_lower = div_with_err(lower_1,upper_2)
    csb_upper = div_with_err(upper_1,lower_2)
    csb_pho = ceil(csb_val*1000)/1000
    csb_pho_l = ceil(csb_lower*1000)/1000
    csb_pho_u = ceil(csb_upper*1000)/1000
    #Calculate net energy rate
    val_1 = float(data[21])
    lower_1 = float(data[22])
    upper_1 = float(data[23])
    val_2 = float(data2[21])
    lower_2 = float(data2[22])
    upper_2 = float(data2[23])
    csb_val = div_with_err(val_1,val_2)
    csb_lower = div_with_err(lower_1,upper_2)
    csb_upper = div_with_err(upper_1,lower_2)
    csb_flux = ceil(csb_val*1000)/1000
    csb_flux_l = ceil(csb_lower*1000)/1000
    csb_flux_u = ceil(csb_upper*1000)/1000
    print(csb_ct,csb_pho,csb_flux)
    add_csb(mydb,mycursor,cluster_id,cluster_name,csb_ct,csb_ct_l,csb_ct_u,csb_pho,csb_pho_l,csb_pho_u,csb_flux,csb_flux_l,csb_flux_u)
    return None

def calculate_bounds(mydb,mycursor,cluster_id,directory,cluster_name):
    os.chdir(directory)
    calc_bounds(mydb,mycursor,cluster_id,'40kpc','400kpc',cluster_name)
    return None
#calculate_bounds('/home/carterrhea/Documents/Test/Abell133/Abell133/SurfaceBrightness')
