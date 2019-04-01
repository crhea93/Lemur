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
    debug -- If set to True then we are using OBSID 15173 (Abell 85). Normally set to False :)


VERSIONS:
v0.0.1 - 01/11/19

For suggestions/comments/errata please contact:
Carter Rhea
carter.rhea@umontreal.ca
'''
#------------------------------------IMPORTS-----------------------------------#
import os
import sys
import easygui as gui
import pandas as pd
from shutil import copyfile
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from Preliminary.unzip import unzip
from Misc.Post_Process import PostProcess
from Misc.filenames import get_filenames
from Misc.read_input import read_input_file
from Misc.Bkg_sub import run_bkg_sub, create_clean_img, exp_corr, create_clean_img_merge
from Preliminary.Merge import merge_objects
from Preliminary.CCD_split import split_ccds
from Preliminary.Centroid import basic_centroid, basic_centroid_guess, merged_centroid
from Spectra.deproject_mod import deproj_final
from Preliminary.FaintCleaning import FaintCleaning
from Spectra.annuli_create import create_annuli,create_src_img, annuli_obs
from Spectra.Batch_Spec import spec_create
from Spectra.Fit_Temp import PrimeFitting
from Misc.Profiles import all_profiles
from Preliminary.chips_ccd import display_ccds, display_entire, display_merge
from Preliminary.CreateLightcurves import bkg_clean_srcs, bkg_lightcurve
#------------------------------------------------------------------------------#
#------------------------------------PROGRAM-----------------------------------#
def main():
    #---------------------------Global Imports--------------------------------#
    global max_rad, cen_x, cen_y, edge_x, edge_y, filenames, annuli_data, Temperatures, Abundances, Norms, Fluxes, obsid_, main_out
    global Temp_min, Temp_max, Ab_min, Ab_max, Norm_min, Norm_max
    #---------------------------Read in data----------------------------------#
    print("Reading Input File and Running Preliminary Steps...")
    inputs = read_input_file(sys.argv[1],float(sys.argv[2]))
    os.chdir(inputs['home_dir'])
    #Unzip all relavent files
    unzip(inputs['home_dir'],inputs['dir_list'])
    print("Generating fits and image files for each individual CCD...")
    ccds = split_ccds(inputs['home_dir'],inputs['dir_list'])
    #-------------------------Single Obsid Scenario------------------------------#
    if inputs['merge'].lower() == 'false':
        print("#-----Single Observation Mode----#")
        for obsid_ in inputs['dir_list']: #left as a list to keep input deck the same and sample :)
            main_out = open(inputs['home_dir'] +"/"+obsid_+ "/decisions.txt", 'w+')
            if inputs['debug'].lower() == 'false':
                os.chdir(os.getcwd() + '/' + obsid_ + '/Background')
                print("    Now let us pick our src and background ccd...")
                #Lets take a look at each ccd and pick our background and src ccds
                display_ccds(ccds,obsid_)
                plt.imshow(mpimg.imread('ccds.png')) #the next few lines are just a bunch of minor decisions and pop-ups
                plt.ion()
                plt.show()
                msg = "Which CCD should be used for Background Flare Extraction?"
                bkg_ccd = gui.buttonbox(msg, choices=ccds[obsid_])
                main_out.write("The background CCD chosen is CCD#%s\n"%bkg_ccd)
                msg = "Which CCD should be used for Source Centroid Extraction?"
                src_ccd = gui.buttonbox(msg, choices=ccds[obsid_])
                main_out.write("The source CCD chosen is CCD#%s\n"%src_ccd)
                plt.close() #don't forget to close
                print("    We can now create a lightcurve for the background...")
                bkg_clean_srcs(bkg_ccd)
                bkg_lightcurve(bkg_ccd)
                cen_x,cen_y = basic_centroid_guess(src_ccd) #Currently not actually used
                print("    We need to clean our diffuse emission...")
                filenames = FaintCleaning(inputs['home_dir'],obsid_,bkg_ccd,cen_x,cen_y,ccds[obsid_])
                os.chdir(inputs['home_dir']+'/'+obsid_)
                print("    We will now choose the extent of the source and any point sources on the src ccd...")
                #Here we calculate three things: Extent of diffuse emission, BKG region, Contaminating Pt Srcs
                edge_x,edge_y = display_entire(inputs['home_dir'],obsid_,filenames['evt2_repro'])
                #print(edge_x,edge_y)'''
                #edge_x, edge_y = 4253.430527931717, 3812.8298364769335
                main_out.write('The edge point is chosen to be %.2f,%.2f'%(edge_x,edge_y))
                os.chdir(inputs['home_dir']+'/'+obsid_+'/Background')
                print("    We will now calculate the centroid...")
                #Just a quick calculation of the centroid based off the pixel with the most counts in a region of choice (deteremined in this step by the user)
                cen_x, cen_y = basic_centroid(src_ccd)
                #cen_x,cen_y = 4228, 3854
                main_out.write("The centroid's X,Y physical coordinates are: %s,%s"%(str(cen_x),str(cen_y)))
                #We can now get a pretty picture with all of our information and run the background subtraction
                os.chdir(inputs['home_dir']+'/'+obsid_+'/repro')
                print("    Creating Clean Image...")
                create_clean_img(filenames)
                print("    Running Background Subtraction...")
                run_bkg_sub(filenames['evt2_repro_uncontam'],filenames['evt_uncontam_img'],obsid_,filenames)
                #exp_corr(filenames) #exposure correct bkg sub image and update
            if inputs['debug'].lower() == 'true':
                bkg_ccd = '3'
                src_ccd = '0'
                cen_x,cen_y = 3810, 4378
                edge_x,edge_y = 3702.52166296, 4730.89657697
                os.chdir(inputs['home_dir']+'/'+obsid_)
                filenames,temp = get_filenames()
                filenames['evt2_repro'] = os.getcwd()+'/repro/acisf'+obsid_+'_repro_evt2.fits'
                filenames['evt2_repro_uncontam'] = filenames['evt2_repro'].split('.')[0]+'_uncontam.fits'
                filenames['evt_bkgsub_img'] = obsid_+'_blank_particle_bkgsub.img'
                filenames['evt_uncontam_img'] = 'evt_uncontam.img'
            #Clean up data
            os.chdir(inputs['home_dir']+'/'+obsid_+'/repro')
            print("    Creating Annuli...")
            annuli_data,max_rad,cen_ra,cen_dec = create_annuli(main_out,filenames['evt_bkgsub_img'],[cen_x,cen_y],[edge_x,edge_y],int(inputs['num_ann_guess']),int(inputs['threshold']))
            create_src_img(filenames['evt_bkgsub_img'],[cen_x,cen_y],[edge_x,edge_y])
    #--------------------------------Multiple Obsid Scenario--------------------------------------#
    if inputs['merge'].lower() == 'true':
        print("#-----Multiple Observation Mode----#")
        #We must clean each observation first :)
        print("Beginning cleaning process for each individual obsid...")
        for obsid_ in inputs['dir_list']: #left as a list to keep input deck the same and sample :)
            '''main_out = open(inputs['home_dir'] + "/" + obsid_ + "/decisions.txt", 'w+')
            os.chdir(inputs['home_dir'] + '/' + obsid_ + '/Background')
            print("We are on obsid %s"%obsid_)
            main_out.write('Obsid %s'%obsid_)
            print("    Now let us pick our src and background ccd...")
            #Lets take a look at each ccd and pick our background and src ccds
            display_ccds(ccds,obsid_)
            plt.imshow(mpimg.imread('ccds.png')) #the next few lines are just a bunch of minor decisions and pop-ups
            plt.ion()
            plt.show()
            msg = "Which CCD should be used for Background Flare Extraction?"
            bkg_ccd = gui.buttonbox(msg, choices=ccds[obsid_])
            main_out.write("The background CCD chosen is CCD#%s\n"%bkg_ccd)
            #msg = "Which CCD should be used for Source Centroid Extraction?"
            #src_ccd = gui.buttonbox(msg, choices=ccds[obsid_])
            #main_out.write("The source CCD chosen is CCD#%s\n"%src_ccd)
            plt.close() #don't forget to close
            print("    We can now create a lightcurve for the background...")
            bkg_clean_srcs(bkg_ccd)
            bkg_lightcurve(bkg_ccd)
            cen_x,cen_y = basic_centroid_guess(src_ccd)# currently not actually used
            print("    We need to clean our diffuse emission...")
            filenames = FaintCleaning(inputs['home_dir'],obsid_,bkg_ccd,cen_x,cen_y,ccds[obsid_])
            #We have to create bkg-subtracted images for each obsid because we need them for our merged image!
            print("    We will now choose the extent of the source and any point sources on the src ccd...")
            os.chdir(inputs['home_dir'] + '/' + obsid_ + '/repro')
            print("    Creating Clean Image...")
            create_clean_img_merge(filenames)
            print("    Running Background Subtraction...")
            run_bkg_sub(filenames['evt2_repro_uncontam'], filenames['evt_uncontam_img'], obsid_, filenames)
            main_out.close()'''
        print("Beginning Merged Calculations...")
        print("    Merging obsids...")
        '''filenames,temp = get_filenames()
        filenames['evt2_repro'] = os.getcwd()+'/repro/acisf'+obsid_+'_repro_evt2.fits'
        filenames['evt2_repro_uncontam'] = filenames['evt2_repro'].split('.')[0]+'_uncontam.fits'
        filenames['evt_bkgsub_img'] = obsid_+'_blank_particle_bkgsub.img'
        filenames['evt_uncontam_img'] = 'evt_uncontam.img'''
        os.chdir(inputs['home_dir'])
        if not os.path.exists(inputs['home_dir']+'/'+inputs['merge_name']):
            os.makedirs(inputs['home_dir']+'/'+inputs['merge_name'])
        #merge_objects(inputs['dir_list'], inputs['merge_name'], clean='yes')
        os.chdir(inputs['home_dir']+'/'+inputs['merge_name'])
        print("    Choosing extent of source and contaminating point sources")
        main_out = open(os.getcwd() + "/decisions.txt", 'w+')
        #edge_x,edge_y = display_merge(inputs['home_dir']+'/'+inputs['merge_name'],'merged_evt.fits')
        edge_x,edge_y = 3937.56,4017.19
        main_out.write('The edge point is chosen to be %.2f,%.2f \n' % (edge_x, edge_y))
        os.chdir(inputs['home_dir']+'/'+inputs['merge_name'])
        print("    Calculating centroid position")
        #cen_x,cen_y = merged_centroid('merged_evt')
        cen_x,cen_y = 4093.00,3978.00
        main_out.write('The center point is chosen to be %.2f,%.2f \n' % (float(cen_x), float(cen_y)))
        print("    Creating annuli...")
        annuli_data,max_rad,cen_ra,cen_dec = create_annuli(main_out,inputs['home_dir']+'/'+inputs['merge_name']+'/merged_evt',[cen_x,cen_y],[edge_x,edge_y],int(inputs['num_ann_guess']),int(inputs['threshold']))
        #create_src_img(inputs['home_dir']+'/'+inputs['merge_name']+'/merged_evt.img',[cen_x,cen_y],[edge_x,edge_y])
    #---------------------------------Spectral Extraction------------------------------------------#
    main_out.write("The centroid's coordinates in ra/dec are: ra=%s dec=%s \n"%(str(cen_ra),str(cen_dec)))
    main_out.write("The radius of interest extends to %.2f arcsec \n"%max_rad)
    #Create nice image of source
    print("Beginning Spectra Extraction...")
    total_ann_num = len(annuli_data.keys())
    print("    We have a total of %i annuli..."%total_ann_num)
    if inputs['debug'].lower() == 'false':
        '''if inputs['merge'].lower() == 'true': #Move annuli data to each obsid
            annuli_obs(inputs['home_dir'],inputs['dir_list'],cen_ra,cen_dec)
        spec_create(inputs['home_dir'],inputs['dir_list'],total_ann_num,list(annuli_data.values()))
        for obsid_ in inputs['dir_list']:
            prefix = inputs['home_dir']+'/'+obsid_+'/repro/Annuli/Annulus_'
            deproj_final(prefix,'.pi',1,total_ann_num,0,prefix,'.deproj')
        os.chdir(inputs['home_dir'])'''
        Temperatures, Temp_min, Temp_max, Abundances, Ab_min, Ab_max, Norms, Norm_min, Norm_max, Fluxes = PrimeFitting(inputs['home_dir'],inputs['merge_name'],inputs['dir_list'],'repro/Annuli/Annulus','temperatures',list(annuli_data.values()),total_ann_num,inputs['redshift'],inputs['n_h'],inputs['temp_guess'],inputs['sigma'])
    if inputs['debug'].lower() == 'true':
        temperature_data = pd.read_csv(inputs['home_dir']+'/'+obsid_+'/repro/Fits/temperatures.csv')
        Temperatures = temperature_data['Temperature']; Temp_min = temperature_data['Temp_min']; Temp_max = temperature_data['Temp_max']
        Abundances = temperature_data['Abundance']; Ab_min = temperature_data['Ab_min']; Ab_max = temperature_data['Ab_max']
        Norms = temperature_data['Norm']; Norm_min = temperature_data['Norm_min']; Norm_max = temperature_data['Norm_max']
        Fluxes = temperature_data['Flux']
    print("Postprocessing and creating plots...")
    Annuli = PostProcess(annuli_data.keys(), list(annuli_data.values()), Temperatures, Temp_min, Temp_max,
                             Abundances, Ab_min, Ab_max, Norms, Norm_min, Norm_max, Fluxes, inputs['redshift'])
    all_profiles(inputs['home_dir']+'/'+inputs['merge_name']+'/Fits',inputs['home_dir']+'/'+inputs['merge_name']+'/Fits',inputs['redshift'])
    main_out.close()
    return None
main()
