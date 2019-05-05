'''
python program to tie together three main components in the creation of a
surface brightess profile
'''
import os
import numpy as np
from SurfaceBrightness.Tools.LSCalc import calc_scale
from SurfaceBrightness.Tools.fit_rprofile import profile1,profile2
from SurfaceBrightness.Tools.radial_prof import calc_profs
from SurfaceBrightness.Tools.annuli_create import create_ann
#--------------------------INPUTS-----------------------------#

def SB_profile(merged_dir,evt_file,exposure_map,bkg_region,ra,dec,z,model_type='single'):
    Flux = True
    #-------------------------------------------------------------#
    if not os.path.exists(merged_dir):
        os.mkdir(merged_dir)
    os.chdir(merged_dir)
    #---------------------Create Annuli---------------------------#
    create_ann(ra,dec)
    #---------------------Create Profile--------------------------#
    calc_profs(evt_file,exposure_map,bkg_region)
    #---------------------PostProcess-----------------------------#
    scaling = calc_scale(z)
    profile1(scaling,model_type)
    profile2(scaling,model_type)
    return None
