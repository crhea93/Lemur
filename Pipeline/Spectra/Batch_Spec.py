'''
Batch Specextract for each annuli
'''
import os
from ciao_contrib.runtool import *


def spec_extract(evt_file,obsid,src_reg,bkg_reg):
    '''
    Standard spectral extration from CIAO
    PARAMETERS:
        evt_file - event file name
        src_reg - source region file name
        bkg_reg - background region file name
    '''
    specextract.punlearn()
    specextract.infile = evt_file+'[sky=region('+src_reg+'.reg)]'
    specextract.outroot = src_reg+'_'
    #specextract.bkgfile = evt_file+'[sky=region('+bkg_reg+'.reg)]'
    specextract.bkgfile = obsid+'_blank.evt[sky=region('+src_reg+'.reg)]'
    specextract.clobber = True
    specextract.grouptype = 'NUM_CTS'
    specextract.binspec = 1
    specextract.bkgresp = False #Necessary if using blank sky
    specextract.energy_wmap = '500:14000'
    specextract()
    return None

def spec_create(home_dir,obsids,num_ann,ann_values):
    '''
    Create spectra for each observation using annuli region files
    PARAMETERS:
        home_dir - Primary Chandra data directory
        obsids - list of Chandra observation IDs
        num_ann - Total number of annuli
        ann_values - outer annulus region needed for deprojection
    '''
    for obsid in obsids:
        print("    We are creating spectra for obsid %s"%obsid)
        os.chdir(home_dir+'/'+obsid+'/repro')
        evt_file = 'acisf'+obsid+'_repro_evt2_uncontam.fits'
        #Create spectra for each annuli
        count = 1
        for ann in range(num_ann):
            print("      We are on annulus %s"%int(count))
            spec_extract(evt_file,obsid,'Annuli/Annulus_'+str(count),'bkg_cel')
            dmhedit.punlearn()
            dmhedit.infile = 'Annuli/Annulus_'+str(count)+'.pi'
            dmhedit.filelist = None
            dmhedit.operation = "add"
            dmhedit.key = "XFLT0001"
            dmhedit.value = ann_values[count-1] #Standard name for create_blanksky file
            dmhedit()
            count += 1
