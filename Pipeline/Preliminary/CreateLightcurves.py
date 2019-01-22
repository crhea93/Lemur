'''
Python script to create lightcurves
'''
import os
from ciao_contrib.runtool import *
from pychips import *
from pychips.hlui import *
from pycrates import *
from lightcurves import *
def bkg_clean_srcs(bkg_ccd):
    vtpdetect.punlearn()
    vtpdetect.infile = 'ccd'+bkg_ccd+'.fits'
    vtpdetect.outfile = 'ccd'+bkg_ccd+'_src.fits'
    vtpdetect.regfile = 'ccd'+bkg_ccd+'_src.reg'
    vtpdetect.clobber = True
    vtpdetect()

    dmcopy.punlearn()
    dmcopy.infile = 'ccd'+bkg_ccd+'.fits[exclude sky=region(ccd'+bkg_ccd+'_src.reg)]'
    dmcopy.outfile = 'ccd'+bkg_ccd+'_bkg.fits'
    dmcopy.clobber = True
    dmcopy()

    return None


def bkg_lightcurve(bkg_ccd):
    #Create Lightcurve
    dmextract.punlearn()
    dmextract.infile = 'ccd'+bkg_ccd+'_bkg.fits[bin time=::200]'
    dmextract.outfile = 'ccd'+bkg_ccd+'_bkg.lc'
    dmextract.opt = 'ltc1'
    dmextract.clobber = True
    dmextract()
    #Plot Lightcurve using CHIPS
    make_figure('ccd'+bkg_ccd+'_bkg.lc[cols dt, count_rate]')
    set_curve(["symbol.style", "none"])
    set_plot_title("Light Curve")
    set_plot_xlabel(r"\Delta T (s)")
    set_plot_ylabel("Rate (count s^{-1})")
    set_preference("export.clobber", "yes")
    print_window('ccd'+bkg_ccd+'_bkg_lc.png')
    clear()
    add_window()
    #Clip image
    lc_sigma_clip('ccd'+bkg_ccd+'_bkg.lc','ccd'+bkg_ccd+'_bkg_clean.gti',sigma=10,pattern="none")
    print_window('ccd'+bkg_ccd+'_bkg_cleanedLC.pdf')
    clear()
    add_window()
    return None
