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
from PIL import Image
import easygui as gui
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from Preliminary.unzip import unzip
from Misc.read_input import read_input_file
from Preliminary.Background.CCD_split import split_ccds
from Preliminary.Background.chips_ccd import display_ccds
#------------------------------------------------------------------------------#
debug = False
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
    if debug == False:
        display_ccds(ccds)
    imgplot = plt.imshow(mpimg.imread('ccds.png'))
    plt.ion()
    plt.show()
    msg = "   Which CCD should be used for Background Flare Extraction?"
    reply = gui.buttonbox(msg, choices=ccds)
    plt.close()

    return None
main()
