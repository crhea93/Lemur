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
#----------------------------------GENERAL IMPORTS-----------------------------#
import os
import sys
import shutil
import pandas as pd
import easygui as gui
import mysql.connector
from shutil import copyfile
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from ciao_contrib.runtool import *
#----------------------------------MISC IMPORTS--------------------------------#
from Misc.move import move_files
from Misc.R_cool import R_cool_calc
from Misc.Profiles import all_profiles
from Misc.PlotToWeb import plots_to_web
from Misc.filenames import get_filenames
from Misc.Post_Process import PostProcess
from Misc.AdditionalPlots import bkg_image
from Misc.RaDec import get_RaDec,get_RaDec_log
from Misc.read_input import read_input_file, read_password
from Misc.Bkg_sub import run_bkg_sub, create_clean_img, exp_corr, create_clean_img_merge
#-------------------------------PRELIMINARY IMPORTS----------------------------#
from Preliminary.unzip import unzip
from Preliminary.Merge import merge_objects
from Preliminary.CCD_split import split_ccds
from Preliminary.FaintCleaning import FaintCleaning
from Preliminary.CreateLightcurves import bkg_clean_srcs, bkg_lightcurve
from Preliminary.chips_ccd import AGN,display_ccds, display_entire, display_merge
from Preliminary.Centroid import basic_centroid, basic_centroid_guess, merged_centroid
#----------------------------------SPECTRAL IMPORTS----------------------------#
from Spectra.Fit_Temp import PrimeFitting
from Spectra.Batch_Spec import spec_create
from Spectra.deproject_mod import deproj_final
from Spectra.annuli_create import create_annuli,create_src_img, annuli_obs
#--------------------------SURFACE BRIGHTNESS IMPORTS---------------------------#
from SurfaceBrightness.Coeff_SB import CSB_calc
from SurfaceBrightness.SBProfile import SB_profile
from SurfaceBrightness.CSB_bounds_merged import calculate_bounds
#---------------------------------DATABASE IMPORTS-----------------------------#
from Database.Add_new import add_cluster_db,add_obsid_db,add_fit_db, add_coord, add_r_cool, add_csb,get_id
#------------------------------------------------------------------------------#
#------------------------------------------------------------------------------#
print('Connecting to Database...')
mydb = mysql.connector.connect(
  host="localhost",
  user="carterrhea",
  passwd='ILoveLuci3!',
  database='carterrhea'
)
mycursor = mydb.cursor()
print(" Connected to Database!")
#------------------------------------------------------------------------------#
#------------------------------------PROGRAM-----------------------------------#
def run_pipeline():
    #---------------------------Global Imports--------------------------------#
    global max_rad, cen_x, cen_y, edge_x, edge_y, filenames, annuli_data
    global Temperatures, Abundances, Norms, Fluxes, obsid_, main_out
    global Temp_min, Temp_max, Ab_min, Ab_max, Norm_min, Norm_max
    #---------------------------Read in data----------------------------------#
    print("Reading Input File and Running Preliminary Steps...")
    inputs,merge_bool = read_input_file(sys.argv[1])
    print("#-------STARTING ANALYSIS ON %s-------#"%inputs['name'])
    #inputs,merge_bool = read_input_file(input_file)
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
                #bkg_ccd, src_ccd = 'ccd1', 'ccd0'
                main_out_obsid.write("The background CCD chosen is CCD#%s\n"%bkg_ccd)
                main_out_obsid.write("The source CCD chosen is CCD#%s\n"%src_ccd)
                if inputs['cleaning'].lower() == 'true':
                    print("    We can now create a lightcurve for the background...")
                    bkg_clean_srcs(bkg_ccd)
                    bkg_lightcurve(bkg_ccd,obsid_)
                    cen_x,cen_y = basic_centroid_guess(src_ccd) #Currently not actually used
                    print("    We need to clean our diffuse emission...")
                    filenames = FaintCleaning(inputs['home_dir'],obsid_,bkg_ccd,cen_x,cen_y,ccds[obsid_])
                if inputs['cleaning'].lower() == 'false':
                    os.chdir(inputs['home_dir']+'/'+obsid_)
                    filenames,temp = get_filenames()
                    filenames['evt2_repro'] = os.getcwd()+'/repro/acisf'+obsid_+'_repro_evt2.fits'
                    os.chdir(inputs['home_dir']+'/'+obsid_+'/repro')
                print("    We will now choose the extent of the source and any point sources on the src ccd...")
                fluximage(filenames['evt2_repro'],inputs['home_dir']+'/'+inputs['name']+'/',clobber='yes')
                filenames['exp_corr'] = inputs['home_dir']+'/'+inputs['name']+'/broad_flux.img'
                #Here we calculate three things: Extent of diffuse emission, BKG region, Contaminating Pt Srcs
                edge_x,edge_y,agn_ = display_entire(inputs['home_dir'],obsid_,filenames['exp_corr'])
                edge_ra,edge_dec = get_RaDec_log(filenames['exp_corr'],edge_x,edge_y)
                main_out_obsid.write("The edge's X,Y sky coordinates are: %s,%s \n"%(edge_ra,edge_dec))
                os.chdir(inputs['home_dir']+'/'+obsid_+'/Background')
                print("    We will now calculate the centroid...")
                #Just a quick calculation of the centroid based off the pixel with the most counts in a region of choice (deteremined in this step by the user)
                cen_ra, cen_dec = basic_centroid(src_ccd)
                #Change to logical coordinates in exp_corr image for consistency
                #cen_ra,cen_dec = get_RaDec(src_ccd+'.img',cen_x,cen_y)
                main_out_obsid.write("The centroid's X,Y sky coordinates are: %s,%s \n"%(str(cen_ra),str(cen_dec)))
                #We can now get a pretty picture with all of our information and run the background subtraction
                if inputs['cleaning'].lower() == 'true':
                    os.chdir(inputs['home_dir']+'/'+obsid_+'/repro')
                    print("    Creating Clean Image...")
                    create_clean_img(filenames)
                    print("    Running Background Subtraction...")
                    run_bkg_sub(filenames['evt2_repro_uncontam'],filenames['evt_uncontam_img'],obsid_,filenames)
                if inputs['cleaning'].lower() == 'false':
                    filenames['evt2_repro_uncontam'] = filenames['evt2_repro'].split('.')[0]+'_uncontam.fits'
                    filenames['evt_bkgsub_img'] = inputs['home_dir']+'/'+obsid_+'/repro/'+obsid_+'_blank_particle_bkgsub.img'
                    filenames['evt_uncontam_img'] = inputs['home_dir']+'/'+obsid_+'/repro/'+'evt_uncontam.img'
                #exp_corr(filenames) #exposure correct bkg sub image and update
            if inputs['debug'].lower() == 'true': #Abell 85 or ophiuchus
                agn_ = AGN(False)
                bkg_ccd = '3'
                src_ccd = '0'
                edge_ra,edge_dec = '00:41:57.968', '-09:17:14.871'  #abell85
                cen_ra,cen_dec =  '00:41:50.232','-09:18:09.29'  #abell 85
                os.chdir(inputs['home_dir']+'/'+obsid_)
                filenames,temp = get_filenames()
                filenames['evt2_repro'] = os.getcwd()+'/repro/acisf'+obsid_+'_repro_evt2.fits'
                filenames['exp_corr'] = inputs['home_dir']+'/'+inputs['name']+'/'+'broad_flux.img'
                filenames['evt2_repro_uncontam'] = filenames['evt2_repro'].split('.')[0]+'_uncontam.fits'
                filenames['evt_bkgsub_img'] = os.getcwd()+'/repro/'+obsid_+'_blank_particle_bkgsub.img'
                filenames['evt_uncontam_img'] = os.getcwd()+'/repro/'+'evt_uncontam.img'
            #Clean up data
            os.chdir(inputs['home_dir']+'/'+obsid_+'/repro')
            #if os.path.exists(inputs['home_dir']+'/'+inputs['name']):
            #    shutil.rmtree(inputs['home_dir']+'/'+inputs['name'])
            if not os.path.exists(inputs['home_dir']+'/'+inputs['name']):
                os.makedirs(inputs['home_dir']+'/'+inputs['name'])
            print("Moving Files")
            move_files(inputs['home_dir']+'/'+inputs['name'],filenames)#move needed files to merged folder
            os.chdir(inputs['home_dir']+'/'+inputs['name'])
    #--------------------------------Multiple Obsid Scenario--------------------------------------#
    if merge_bool == True:
        print("#-----Multiple Observation Mode----#")
        #We must clean each observation first :)
        print("Beginning cleaning process for each individual obsid...")
        for obsid_ in inputs['dir_list']: #left as a list to keep input deck the same and sample :)
            add_obsid_db(mydb,mycursor,inputs['name'],obsid_)
            if inputs['cleaning'].lower() == 'true':
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
                bkg_lightcurve(bkg_ccd,obsid_)
                print("    We need to clean our diffuse emission...")
                filenames = FaintCleaning(inputs['home_dir'],obsid_,bkg_ccd,0,0,ccds[obsid_])
                #We have to create bkg-subtracted images for each obsid because we need them for our merged image!
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
            filenames['evt_bkgsub_img'] = inputs['home_dir']+'/'+inputs['name']+'/broad_flux.img'
            filenames['evt_uncontam_img'] = inputs['home_dir']+'/'+inputs['name']+'/broad_flux.img'
        if inputs['debug'].lower() == 'false':
            print("Beginning Merged Calculations...")
            print("    Merging obsids...")
            os.chdir(inputs['home_dir'])
            merge_objects(inputs['dir_list'], inputs['name'], clean='yes')
            os.chdir(inputs['home_dir']+'/'+inputs['name'])
            print("    Choosing extent of source and contaminating point sources")
            edge_x,edge_y,agn_ = display_merge(inputs['home_dir']+'/'+inputs['name'],'broad_flux.img')
            edge_ra,edge_dec = get_RaDec_log('broad_flux.img',edge_x,edge_y)
            main_out.write('The edge point is chosen to be %s,%s \n' % (edge_ra, edge_dec))
            os.chdir(inputs['home_dir']+'/'+inputs['name'])
            print("    Calculating centroid position")
            cen_ra,cen_dec = merged_centroid('broad_flux.img')
            #cen_ra,cen_dec = get_RaDec('broad_flux.img',cen_x,cen_y)
            main_out.write('The center point is chosen to be %s,%s \n' % (cen_ra, cen_dec))
        if inputs['debug'].lower() == 'true': #Abell 133
            agn_ = AGN(False)
            #main_out = open(os.getcwd() + "/decisions.txt", 'w+')
            os.chdir(inputs['home_dir']+'/'+inputs['dir_list'][0]) #Doesnt matter which since we only want merged info
            filenames,temp = get_filenames()
            filenames['evt2_repro'] = inputs['home_dir']+'/'+inputs['name']+'/merged_evt.fits'
            filenames['evt2_repro_uncontam'] = filenames['evt2_repro'].split('.')[0]+'_uncontam.fits'
            filenames['evt_bkgsub_img'] = inputs['home_dir']+'/'+inputs['name']+'/broad_flux.img'
            filenames['evt_uncontam_img'] = inputs['home_dir']+'/'+inputs['name']+'/broad_flux.img' #Cleaned bkg image is just merged for merged scenario
            cen_ra,cen_dec = '01:02:41.957', '-21:52:54.95'
            edge_ra,edge_dec = '01:02:34.328', '-21:52:40.53'
            os.chdir(inputs['home_dir']+'/'+inputs['name'])
            main_out.write('The edge point is chosen to be %s,%s \n' % (edge_ra, edge_dec))
            main_out.write('The center point is chosen to be %s,%s \n' % (cen_ra, cen_dec))
    filenames['exp_corr'] = inputs['home_dir']+'/'+inputs['name']+'/broad_flux.img' #Need this defined
    #Calculate additional needed parameters
    #bkg_image(os.getcwd(),filenames['exp_corr'],os.getcwd()+'/bkg.reg',filenames)
    create_src_img(filenames['exp_corr'],[cen_ra,cen_dec],[edge_ra,edge_dec])
    add_coord(mydb,mycursor,inputs['name'],cen_ra,cen_dec)
    #Get cluster ID
    cluster_id = get_id(mydb,mycursor,inputs['name'])
    #---------------------------------Spectral Extraction------------------------------------------#
    if inputs['spectra_calc'].lower() == 'true':
        print("#-----Spectral Extraction Mode----#")
        #Create annuli and source image
        print("Creating Annuli for Spectral Extraction")
        if merge_bool == True:
            annuli_data,max_rad = create_annuli(main_out,inputs['home_dir']+'/'+inputs['name']+'/merged_evt.fits',[cen_ra,cen_dec],[edge_ra,edge_dec],int(inputs['num_ann_guess']),int(inputs['threshold']))
        else:
            annuli_data,max_rad = create_annuli(main_out,filenames['evt_bkgsub_img'],[cen_ra,cen_dec],[edge_ra,edge_dec],int(inputs['num_ann_guess']),int(inputs['threshold']))
        #Create nice image of source
        print("Beginning Spectra Extraction...")
        total_ann_num = len(annuli_data.keys())
        print("    We have a total of %i annuli..."%total_ann_num)
        if inputs['spec_create'].lower() == 'true':
            annuli_obs(inputs['home_dir'],inputs['dir_list'],filenames['exp_corr'],cen_ra,cen_dec,merge_bool)
            spec_create(inputs['home_dir'],inputs['dir_list'],total_ann_num,list(annuli_data.values()))
            for obsid_ in inputs['dir_list']:
                prefix = inputs['home_dir']+'/'+obsid_+'/repro/Annuli/Annulus_'
                deproj_final(prefix,'.pi',1,total_ann_num,0,prefix,'.deproj')
        os.chdir(inputs['home_dir'])
        if inputs['spec_fit'].lower() == 'true':
            Annuli_ = PrimeFitting(mydb,mycursor,cluster_id,inputs['home_dir'],inputs['name'],inputs['dir_list'],'repro/Annuli/Annulus','temperatures',list(annuli_data.values()),total_ann_num,inputs['redshift'],inputs['n_h'],inputs['temp_guess'],inputs['sigma'],agn_,inputs['name'])
            print("Postprocessing and creating plots...")
            PostProcess(Annuli_,inputs['redshift'],inputs['home_dir']+'/'+inputs['name']+'/Fits')
        all_profiles(mydb,mycursor,inputs['home_dir']+'/'+inputs['name']+'/Fits',inputs['home_dir']+'/'+inputs['name']+'/Fits/Plots',inputs['redshift'],cluster_id)
    #----------------------------------Surface Brightness------------------------------------------#
    os.chdir(inputs['home_dir']+'/'+inputs['name'])
    filenames['exp_map'] = os.getcwd()+'/broad_thresh.expmap'
    filenames['bkg'] = os.getcwd()+'/bkg.reg'
    if inputs['surface_brightness_calc'].lower() == 'true':
        print("#-----Surface Brightness Mode----#")
        SB_profile(inputs['home_dir']+'/'+inputs['name']+'/SurfaceBrightness/',filenames['evt2_repro'],filenames['exp_map'],filenames['bkg'],cen_ra,cen_dec,inputs['redshift'])
        print('Calculating Surface Brightess Coefficient')
        CSB_calc(inputs['home_dir'],inputs['name'],inputs['dir_list'],cen_ra,cen_dec,filenames['bkg'],inputs['redshift'],merge_bool)
        calculate_bounds(mydb,mycursor,cluster_id,inputs['home_dir']+'/'+inputs['name']+'/SurfaceBrightness',inputs['name'])
    #---------------------------------Additional Calculations--------------------------------------#
    R_cool_calc(mydb,mycursor,cluster_id,inputs['name'],inputs['home_dir']+'/'+inputs['name']+'/Fits',inputs['redshift'],main_out)
    #--------------------------FINISH---------------------------------#
    plots_to_web(inputs['home_dir'],inputs['dir_list'],inputs['name'],inputs['web_dir']+'/'+inputs['name'])
    main_out.close()
    return None
run_pipeline()
#main()
