'''
PIPELINE FOR TEMPERATURE PROFILE:
The following program will handle all automation of the creation of the
temperature pipeline. The input is handle through an input file so that the user
does not need to change this file.

The program should read run as the following:
python pipeline.py input.i #
where # is the number of values in the input file

INPUT PARAMETERS:
    home_dir -- Directory containing Chandra Data (e.g. '/home/user/Documents/Chandra')
    dir_list -- List of OBSIDS (e.g. ['15173'])



VERSIONS:
v0.0.1 - 01/11/19

For suggestions/comments/errata please contact:
Carter Rhea
carter.rhea@umontreal.ca
'''
#------------------------------------IMPORTS-----------------------------------#
import os
import sys
import numpy as np
import easygui as gui
import pandas as pd
from shutil import copyfile
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from Preliminary.unzip import unzip
from Misc.Post_Process import PostProcess
from Misc.filenames import get_filenames
from Misc.read_input import read_input_file
from Misc.Bkg_sub import run_bkg_sub, create_clean_img
from Preliminary.Merge import merge_objects
from Preliminary.CCD_split import split_ccds
from Preliminary.Centroid import basic_centroid, basic_centroid_guess, merged_centroid
from Spectra.deproject_mod import deproj_final
from Preliminary.FaintCleaning import FaintCleaning
from Spectra.annuli_create import create_annuli,create_annuli_preset
from Spectra.Batch_Spec import spec_create
from Spectra.Fit_Temp import PrimeFitting
from Misc.Profiles import all_profiles
from Preliminary.chips_ccd import display_ccds, display_entire
from Preliminary.CreateLightcurves import bkg_clean_srcs, bkg_lightcurve
#------------------------------------------------------------------------------#
#------------------------------------PROGRAM-----------------------------------#
def main():
    #Read input file
    print("Reading Input File and Running Preliminary Steps...")
    inputs = read_input_file(sys.argv[1],float(sys.argv[2]))
    os.chdir(inputs['home_dir'])
    #Unzip all relavent files
    unzip(inputs['home_dir'],inputs['dir_list'])
    print("    Generating fits and image files for each individual CCD...")
    ccds = split_ccds(inputs['home_dir'],inputs['dir_list'])
    for obsid_ in inputs['dir_list']:
        if inputs['choose_ccds'].lower() == 'true':
            display_ccds(ccds)
            imgplot = plt.imshow(mpimg.imread('ccds.png'))
            plt.ion()
            plt.show()
            msg = "Which CCD should be used for Background Flare Extraction?"
            bkg_ccd = gui.buttonbox(msg, choices=ccds)
            msg = "Which CCD should be used for Source Centroid Extraction?"
            src_ccd = gui.buttonbox(msg, choices=ccds)
            plt.close()
            bkg_clean_srcs(bkg_ccd)
            bkg_lightcurve(bkg_ccd)
        if inputs['choose_ccds'].lower() == 'false':
            bkd_ccd = str(int(inputs['bkg_ccd']))
            src_ccd = str(int(inputs['src_ccd']))
        if inputs['cleaning'].lower == 'true':
            cen_x,cen_y = basic_centroid_guess(src_ccd)
            filenames = FaintCleaning(inputs['home_dir'],obsid_,bkg_ccd,cen_x,cen_y)
            os.chdir(inputs['home_dir']+'/'+obsid_)
            print("    We will now choose the extent of the source and any contamination...")
            edge_x,edge_y = display_entire(inputs['home_dir'],obsid_,filenames['evt2_repro'])
            os.chdir(inputs['home_dir']+'/'+obsid_+'/Background')
            cen_x,cen_y = basic_centroid(src_ccd)
            os.chdir(inputs['home_dir']+'/'+obsid_+'/repro')
            create_clean_img(filenames)
            run_bkg_sub(filenames['evt2_repro_uncontam'],filenames['evt_uncontam_img'],obsid_,filenames)
        if inputs['cleaning'].lower() == 'false':
            cen_x,cen_y = inputs['cen_x'],inputs['cen_y']#basic_centroid(src_ccd)
            os.chdir(inputs['home_dir']+'/'+obsid_)
            filenames,temp = get_filenames()
            filenames['evt2_repro'] = os.getcwd()+'/repro/acisf'+obsid_+'_repro_evt2.fits'
            filenames['evt2_repro_uncontam'] = filenames['evt2_repro'].split('.')[0]+'_uncontam.fits'
            filenames['evt_bkgsub_img'] = obsid_+'_blank_particle_bkgsub.img'
            filenames['evt_uncontam_img'] = 'evt_uncontam.img'
        #Clean up data
        os.chdir(inputs['home_dir']+'/'+obsid_+'/repro')
        print("    Creating Annuli...")
        if inputs['merge'].lower() == 'false' and inputs['choose_reg'].lower() == 'false':
            annuli_data = create_annuli(os.getcwd(),filenames['evt_bkgsub_img'],[cen_x,cen_y],[edge_x,edge_y],int(inputs['num_ann_guess']),int(inputs['threshold']))
        if inputs['merge'].lower() == 'false' and inputs['choose_reg'].lower() == 'true':
            annuli_data = create_annuli_preset(os.getcwd(),filenames['evt_bkgsub_img'],[cen_x,cen_y],inputs['radius'],int(inputs['num_ann_guess']),int(inputs['threshold']))
    if inputs['merge'].lower() == 'true':
        print("Merging obsids...")
        os.chdir(inputs['home_dir'])
        merge_objects(inputs['dir_list'],clean='yes')
        edge_x,edge_y = display_merge(inputs['home_dir'],'Merged','merged_evt.fits')
        os.chdir(inputs['home_dir']+'/Merged')
        cen_x,cen_y = merged_centroid('merged_evt.fits')
        annuli_data = create_annuli(os.getcwd(),'Merged/merged_evt.fits',[cen_x,cen_y],[edge_x,edge_y],int(inputs['num_ann_guess']),int(inputs['threshold']))
    print("Beginning Spectra Extraction...")
    total_ann_num = len(annuli_data.keys())
    print("    We have a total of %i annuli..."%total_ann_num)
    if inputs['create_spec'].lower() == 'true':
        spec_create(inputs['home_dir'],inputs['dir_list'],total_ann_num,list(annuli_data.values()))
        for obsid_ in inputs['dir_list']:
            prefix = inputs['home_dir']+'/'+obsid_+'/repro/Annuli/Annulus_'
            deproj_final(prefix,'.pi',1,total_ann_num,0,prefix,'.deproj')
        os.chdir(inputs['home_dir'])
        Temperatures, Temp_min, Temp_max, Abundances, Ab_min, Ab_max, Norms, Norm_min, Norm_max, Fluxes = PrimeFitting(inputs['home_dir'],inputs['dir_list'],'repro/Annuli/Annulus','temperatures',list(annuli_data.values()),total_ann_num,inputs['redshift'],inputs['n_h'],inputs['temp_guess'],inputs['sigma'])
    if inputs['create_spec'].lower() == 'false' and inputs['fit_spec'].lower() == 'true':
        print('go')
        Temperatures, Temp_min, Temp_max, Abundances, Ab_min, Ab_max, Norms, Norm_min, Norm_max, Fluxes = PrimeFitting(
            inputs['home_dir'], inputs['dir_list'], 'repro/Annuli/Annulus', 'temperatures', list(annuli_data.values()),
            total_ann_num, inputs['redshift'], inputs['n_h'], inputs['temp_guess'], inputs['sigma'])
    if inputs['create_spec'].lower() == 'false' and inputs['fit_spec'].lower() == 'false':
        temperature_data = pd.read_csv(inputs['home_dir']+'/'+obsid_+'/Fits/temperatures.csv')
        Temperatures = pd.to_numeric(temperature_data['Temperature']); Temp_min = pd.to_numeric(temperature_data['Temp_min']); Temp_max = pd.to_numeric(temperature_data['Temp_max'])
        Abundances = pd.to_numeric(temperature_data['Abundance']); Ab_min = pd.to_numeric(temperature_data['Ab_min']); Ab_max = pd.to_numeric(temperature_data['Ab_max'])
        Norms = pd.to_numeric(temperature_data['Norm']); Norm_min = pd.to_numeric(temperature_data['Norm_min']); Norm_max = pd.to_numeric(temperature_data['Norm_max'])
        Fluxes = temperature_data['Flux']
    #Annuli = PostProcess(annuli_data.keys(),list(annuli_data.values()),Temperatures, Temp_mins, Temp_maxes, Abundances, Ab_mins, Ab_maxes, Norms, Norm_mins, Norm_maxes, Fluxes,inputs['redshift'])
    os.chdir(inputs['home_dir']+'/'+inputs['dir_list'][0])
    Annuli = PostProcess(annuli_data.keys(),list(annuli_data.values()),Temperatures, Temp_min, Temp_max, Abundances, Ab_min, Ab_max, Norms, Norm_min, Norm_max, Fluxes,inputs['redshift'])
    all_profiles(inputs['home_dir']+'/'+obsid_+'/Fits',inputs['home_dir']+'/'+obsid_+'/Fits',inputs['redshift'])
    return None
main()
