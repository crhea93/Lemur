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
    debug -- If set to True then we are using OBSID 15173 (Abell 85 or Abell 133). Normally set to False :)


VERSIONS (and submission date):
v0 - 01/11/19 - basic pipeline for single observations
v1 - 04/11/19 - fully functioning pipeline for single/multiple observations
v1.1 - 04/25/19 - Considerably more modular and addition of AGN and surface brightness calculations

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
import mysql.connector
from Misc.move import move_files
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from Preliminary.unzip import unzip
from Misc.Post_Process import PostProcess
from Misc.filenames import get_filenames
from Misc.read_input import read_input_file, read_password
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
from Preliminary.chips_ccd import AGN,display_ccds, display_entire, display_merge
from Preliminary.CreateLightcurves import bkg_clean_srcs, bkg_lightcurve
from SurfaceBrightness.SBProfile import SB_profile
from ciao_contrib.runtool import *
from Misc.RaDec import get_RaDec
from Misc.R_cool import R_cool_calc
from Database.Add_new import add_cluster_db,add_obsid_db,add_fit_db, add_coord
#------------------------------------------------------------------------------#
mydb = mysql.connector.connect(
  host="localhost",
  port='3306',
  user="crhea93",
  passwd='ILoveLuci3!',
  database='Lemur_DB'
)
mycursor = mydb.cursor()
#------------------------------------PROGRAM-----------------------------------#
def main():
    #---------------------------Global Imports--------------------------------#
    global max_rad, cen_x, cen_y, edge_x, edge_y, filenames, annuli_data, Temperatures, Abundances, Norms, Fluxes, obsid_, main_out
    global Temp_min, Temp_max, Ab_min, Ab_max, Norm_min, Norm_max
    #---------------------------Read in data----------------------------------#
    print("Reading Input File and Running Preliminary Steps...")
    inputs,merge_bool = read_input_file(sys.argv[1])
    os.chdir(inputs['home_dir'])
    add_cluster_db(mydb,mycursor,inputs['name'],inputs['redshift'])
    #Unzip all relavent files
    unzip(inputs['home_dir'],inputs['dir_list'])
    print("Generating fits and image files for each individual CCD...")
    ccds = split_ccds(inputs['home_dir'],inputs['dir_list'])
    if not os.path.exists(inputs['home_dir']+'/'+inputs['name']):
        os.makedirs(inputs['home_dir']+'/'+inputs['name'])
    main_out = open(inputs['home_dir']+'/'+inputs['name'] + "/Additional.txt", 'w+')
    #-------------------------Single Obsid Scenario------------------------------#
    if merge_bool == False:
        print("#-----Single Observation Mode----#")
        for obsid_ in inputs['dir_list']: #left as a list to keep input deck the same and sample :)
            add_obsid_db(mydb,mycursor,inputs['name'],obsid_)
            main_out_obsid = open(inputs['home_dir'] +"/"+obsid_+ "/decisions.txt", 'w+')
            if inputs['debug'].lower() == 'false':
                os.chdir(os.getcwd() + '/' + obsid_ + '/Background')
                print("    Now let us pick our src and background ccd...")
                #Lets take a look at each ccd and pick our background and src ccds
                bkg_ccd, src_ccd = display_ccds(ccds,obsid_)
                main_out_obsid.write("The background CCD chosen is CCD#%s\n"%bkg_ccd)
                main_out_obsid.write("The source CCD chosen is CCD#%s\n"%src_ccd)
                if inputs['cleaning'].lower() == 'true':
                    print("    We can now create a lightcurve for the background...")
                    bkg_clean_srcs(bkg_ccd)
                    bkg_lightcurve(bkg_ccd)
                    cen_x,cen_y = basic_centroid_guess(src_ccd) #Currently not actually used
                    print("    We need to clean our diffuse emission...")
                    filenames = FaintCleaning(inputs['home_dir'],obsid_,bkg_ccd,cen_x,cen_y,ccds[obsid_])
                if inputs['cleaning'].lower() == 'false':
                    os.chdir(inputs['home_dir']+'/'+obsid_)
                    filenames,temp = get_filenames()
                    filenames['evt2_repro'] = os.getcwd()+'/repro/acisf'+obsid_+'_repro_evt2.fits'
                print("    We will now choose the extent of the source and any point sources on the src ccd...")
                #Here we calculate three things: Extent of diffuse emission, BKG region, Contaminating Pt Srcs
                edge_x,edge_y,agn_ = display_entire(inputs['home_dir'],obsid_,filenames['evt2_repro'])
                main_out_obsid.write('The edge point is chosen to be %.2f,%.2f'%(edge_x,edge_y))
                os.chdir(inputs['home_dir']+'/'+obsid_+'/Background')
                print("    We will now calculate the centroid...")
                #Just a quick calculation of the centroid based off the pixel with the most counts in a region of choice (deteremined in this step by the user)
                cen_x, cen_y = basic_centroid(src_ccd)
                main_out_obsid.write("The centroid's X,Y physical coordinates are: %s,%s"%(str(cen_x),str(cen_y)))
                #We can now get a pretty picture with all of our information and run the background subtraction
                if inputs['cleaning'].lower() == 'true':
                    os.chdir(inputs['home_dir']+'/'+obsid_+'/repro')
                    print("    Creating Clean Image...")
                    create_clean_img(filenames)
                    print("    Running Background Subtraction...")
                    run_bkg_sub(filenames['evt2_repro_uncontam'],filenames['evt_uncontam_img'],obsid_,filenames)
                #exp_corr(filenames) #exposure correct bkg sub image and update
            if inputs['debug'].lower() == 'true': #Abell 85 or ophiuchus
                agn_ = AGN(True) #Abell85 - False; Ophiuchus -True
                agn_.set_AGN(4077.05,4253.87,5.43)
                bkg_ccd = '3'
                src_ccd = '0'
                cen_x,cen_y = 3971, 4623 #abell85
                edge_x,edge_y = 3702.52166296, 4730.89657697 #abell 85
                #cen_x,cen_y = 4076,4255 #ophiuchus
                #edge_x,edge_y = 4010,4207 #ophiuchus
                #cen_x,cen_y = 4172,4475 #random
                #edge_x,edge_y = 4091.91,4457.37 #random
                os.chdir(inputs['home_dir']+'/'+obsid_)
                filenames,temp = get_filenames()
                filenames['evt2_repro'] = os.getcwd()+'/repro/acisf'+obsid_+'_repro_evt2.fits'
                filenames['evt2_repro_uncontam'] = filenames['evt2_repro'].split('.')[0]+'_uncontam.fits'
                filenames['evt_bkgsub_img'] = os.getcwd()+'/repro/'+obsid_+'_blank_particle_bkgsub.img'
                filenames['evt_uncontam_img'] = os.getcwd()+'/repro/'+'evt_uncontam.img'
            #Clean up data
            os.chdir(inputs['home_dir']+'/'+obsid_+'/repro')
            if not os.path.exists(inputs['home_dir']+'/'+inputs['name']):
                os.makedirs(inputs['home_dir']+'/'+inputs['name'])
            move_files(inputs['home_dir']+'/'+inputs['name'],filenames)#move needed files to merged folder
            os.chdir(inputs['home_dir']+'/'+inputs['name'])
            #create exposure map
            fluximage(filenames['evt2_repro'],os.getcwd(),clobber='yes')
            main_out_obsid.close()
    #--------------------------------Multiple Obsid Scenario--------------------------------------#
    if merge_bool == True:
        print("#-----Multiple Observation Mode----#")
        #We must clean each observation first :)\
        if inputs['cleaning'].lower() == 'true':
            print("Beginning cleaning process for each individual obsid...")
            for obsid_ in inputs['dir_list']: #left as a list to keep input deck the same and sample :)
                main_out_obsid = open(inputs['home_dir'] + "/" + obsid_ + "/decisions.txt", 'w+')
                os.chdir(inputs['home_dir'] + '/' + obsid_ + '/Background')
                print("We are on obsid %s"%obsid_)
                main_out_obsid.write('Obsid %s'%obsid_)
                print("    Now let us pick our background ccd...")
                #Lets take a look at each ccd and pick our background and src ccds
                bkg_ccd = display_ccds(ccds,obsid_,Merge=True)
                main_out_obsid.write("The background CCD chosen is CCD#%s\n"%bkg_ccd)
                print("    We can now create a lightcurve for the background...")
                bkg_clean_srcs(bkg_ccd)
                bkg_lightcurve(bkg_ccd)
                #cen_x,cen_y = basic_centroid_guess(src_ccd)# currently not actually used
                print("    We need to clean our diffuse emission...")
                filenames = FaintCleaning(inputs['home_dir'],obsid_,bkg_ccd,0,0,ccds[obsid_])
                #We have to create bkg-subtracted images for each obsid because we need them for our merged image!
                #print("    We will now choose the extent of the source and any point sources on the src ccd...")
                os.chdir(inputs['home_dir'] + '/' + obsid_ + '/repro')
                print("    Creating Clean Image...")
                create_clean_img_merge(filenames)
                print("    Running Background Subtraction...")
                run_bkg_sub(filenames['evt2_repro_uncontam'], filenames['evt_uncontam_img'], obsid_, filenames)
                main_out_obsid.close()
        if inputs['cleaning'].lower() == 'false':
            os.chdir(inputs['home_dir']+'/'+inputs['dir_list'][0])
            filenames,temp = get_filenames()
            filenames['evt2_repro'] = inputs['home_dir']+'/'+inputs['name']+'/merged_evt.fits'
            filenames['evt2_repro_uncontam'] = filenames['evt2_repro'].split('.')[0]+'_uncontam.fits'
            filenames['evt_bkgsub_img'] = inputs['home_dir']+'/'+inputs['name']+'/merged_evt.fits'
            filenames['evt_uncontam_img'] = inputs['home_dir']+'/'+inputs['name']+'/merged_evt.fits'
        if inputs['debug'].lower() == 'false':
            print("Beginning Merged Calculations...")
            print("    Merging obsids...")
            os.chdir(inputs['home_dir'])
            merge_objects(inputs['dir_list'], inputs['name'], clean='yes')
            os.chdir(inputs['home_dir']+'/'+inputs['name'])
            print("    Choosing extent of source and contaminating point sources")
            edge_x,edge_y,agn_ = display_merge(inputs['home_dir']+'/'+inputs['name'],'merged_evt.fits')
            main_out.write('The edge point is chosen to be %.2f,%.2f \n' % (edge_x, edge_y))
            os.chdir(inputs['home_dir']+'/'+inputs['name'])
            print("    Calculating centroid position")
            cen_x,cen_y = merged_centroid('merged_evt')
            main_out.write('The center point is chosen to be %.2f,%.2f \n' % (float(cen_x), float(cen_y)))
        if inputs['debug'].lower() == 'true': #Abell 133
            agn_ = AGN(False)
            #main_out = open(os.getcwd() + "/decisions.txt", 'w+')
            os.chdir(inputs['home_dir']+'/'+inputs['dir_list'][0]) #Doesnt matter which since we only want merged info
            filenames,temp = get_filenames()
            filenames['evt2_repro'] = inputs['home_dir']+'/'+inputs['name']+'/merged_evt.fits'
            filenames['evt2_repro_uncontam'] = filenames['evt2_repro'].split('.')[0]+'_uncontam.fits'
            filenames['evt_bkgsub_img'] = inputs['home_dir']+'/'+inputs['name']+'/merged_evt.fits'
            filenames['evt_uncontam_img'] = inputs['home_dir']+'/'+inputs['name']+'/merged_evt.fits' #Cleaned bkg image is just merged for merged scenario
            cen_x,cen_y = 4154.00,4001.00
            edge_x,edge_y = 4209.13,4081.13
            os.chdir(inputs['home_dir']+'/'+inputs['name'])
            main_out.write('The edge point is chosen to be %.2f,%.2f \n' % (edge_x, edge_y))
            main_out.write('The center point is chosen to be %.2f,%.2f \n' % (float(cen_x), float(cen_y)))
    #Calculate additional needed parameters
    cen_ra,cen_dec = get_RaDec(filenames['evt_uncontam_img'],cen_x,cen_y)
    add_coord(mydb,mycursor,cluster_name,cen_ra,cen_dec)
    #---------------------------------Spectral Extraction------------------------------------------#
    if inputs['spectra_calc'].lower() == 'true':
        print("#-----Spectral Extraction Mode----#")
        #Create annuli and source image
        print("Creating Annuli for Spectral Extraction")
        if merge_bool == True:
            annuli_data,max_rad = create_annuli(main_out,inputs['home_dir']+'/'+inputs['name']+'/merged_evt',[cen_x,cen_y],[edge_x,edge_y],int(inputs['num_ann_guess']),int(inputs['threshold']))
            create_src_img(inputs['home_dir']+'/'+inputs['name']+'/merged_evt.img',[cen_x,cen_y],[edge_x,edge_y])
        else:
            annuli_data,max_rad = create_annuli(main_out,filenames['evt_bkgsub_img'],[cen_x,cen_y],[edge_x,edge_y],int(inputs['num_ann_guess']),int(inputs['threshold']))
            create_src_img(filenames['evt_bkgsub_img'],[cen_x,cen_y],[edge_x,edge_y])
        main_out.write("The centroid's coordinates in ra/dec are: ra=%s dec=%s \n"%(str(cen_ra),str(cen_dec)))
        main_out.write("The radius of interest extends to %.2f arcsec \n"%max_rad)
        #Create nice image of source
        print("Beginning Spectra Extraction...")
        total_ann_num = len(annuli_data.keys())
        print("    We have a total of %i annuli..."%total_ann_num)
        annuli_obs(inputs['home_dir'],inputs['dir_list'],cen_ra,cen_dec)
        spec_create(inputs['home_dir'],inputs['dir_list'],total_ann_num,list(annuli_data.values()))
        for obsid_ in inputs['dir_list']:
            prefix = inputs['home_dir']+'/'+obsid_+'/repro/Annuli/Annulus_'
            deproj_final(prefix,'.pi',1,total_ann_num,0,prefix,'.deproj')
        os.chdir(inputs['home_dir'])
        Annuli_ = PrimeFitting(inputs['home_dir'],inputs['name'],inputs['dir_list'],'repro/Annuli/Annulus','temperatures',list(annuli_data.values()),total_ann_num,inputs['redshift'],inputs['n_h'],inputs['temp_guess'],inputs['sigma'],agn_,inputs['name'])
        print("Postprocessing and creating plots...")
        PostProcess(Annuli_,inputs['redshift'],inputs['home_dir']+'/'+inputs['name']+'/Fits')
        all_profiles(inputs['home_dir']+'/'+inputs['name']+'/Fits',inputs['home_dir']+'/'+inputs['name']+'/Fits/Plots',inputs['redshift'])
    #----------------------------------Surface Brightness------------------------------------------#
    os.chdir(inputs['home_dir']+'/'+inputs['name'])
    filenames['exp_map'] = os.getcwd()+'/broad_thresh.expmap'
    filenames['bkg'] = os.getcwd()+'/bkg.reg'
    if inputs['surface_brightness_calc'].lower() == 'true':
        print("#-----Surface Brightness Mode----#")
        SB_profile(inputs['home_dir']+'/'+inputs['name']+'/SurfaceBrightness',filenames['evt_bkgsub_img'],filenames['exp_map'],filenames['bkg'],cen_ra,cen_dec,inputs['redshift'])
    #---------------------------------Additional Calculations--------------------------------------#
    R_cool_calc(inputs['home_dir']+'/'+inputs['name']+'/Fits',inputs['redshift'],main_out)

    #--------------------------FINISH---------------------------------#
    main_out.close()
    return None
main()
