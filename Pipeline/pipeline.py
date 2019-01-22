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
import easygui as gui
from shutil import copyfile
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from Preliminary.unzip import unzip
from Misc.filenames import get_filenames
from Misc.read_input import read_input_file
from Preliminary.CCD_split import split_ccds
from Preliminary.chips_ccd import display_ccds
from Preliminary.Centroid import basic_centroid
from Preliminary.FaintCleaning import FaintCleaning
from Preliminary.CreateLightcurves import bkg_clean_srcs,bkg_lightcurve
#------------------------------------------------------------------------------#
#------------------------------------PROGRAM-----------------------------------#
def main():
    #Read input file
    print("Reading Input File and Running Preliminary Steps...")
    inputs = read_input_file(sys.argv[1],float(sys.argv[2]))
    os.chdir(inputs['home_dir'])
    #Unzip all relavent files
    unzip(inputs['home_dir'],inputs['dir_list'])
    #Create event for each ccd
    print("    Generating fits and image files for each individual CCD...")
    ccds = split_ccds(inputs['home_dir'],inputs['dir_list'])
    if inputs['debug'].lower() == 'true':
        display_ccds(ccds)
    imgplot = plt.imshow(mpimg.imread('ccds.png'))
    plt.ion()
    plt.show()
    msg = "   Which CCD should be used for Background Flare Extraction?"
    bkg_ccd = '6'#gui.buttonbox(msg, choices=ccds)
    msg = "   Which CCD should be used for Source Centroid Extraction?"
    src_ccd = '2'#gui.buttonbox(msg, choices=ccds)
    plt.close()
    #Find background Flares
    #bkg_clean_srcs(bkg_ccd)
    #bkg_lightcurve(bkg_ccd)
    #Choose Centroid
    cen_x,cen_y = 4475.9697746,4428.467026#basic_centroid(src_ccd)
    #Clean up data
    os.chdir(inputs['home_dir'])
    FaintCleaning(inputs['home_dir'],inputs['dir_list'],bkg_ccd,cen_x,cen_y)
    return None
main()
