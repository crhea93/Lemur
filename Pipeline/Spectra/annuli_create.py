'''
Create annuli from background subtracted image containing a minimum number of counts
'''
import os
import shutil
from pycrates import *
import numpy as np

from ciao_contrib.smooth import *
from ciao_contrib.runtool import *
from crates_contrib.utils import *
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS
from astropy.convolution import Gaussian2DKernel, convolve
import matplotlib.pyplot as plt
def max_counts(image):
    '''Maximum counts in image'''
    dmstat.punlearn()
    dmstat.infile = image
    dmstat.centroid = True
    dmstat()
    return int(dmstat.out_max)

def max_coord(image,coord):
    '''Maximum coordinate value in image'''
    dmstat.punlearn()
    dmstat.infile = image+'[cols '+coord+']'
    dmstat()
    return float(dmstat.out_max)

def min_coord(image,coord):
    '''Minimum coordinate value in image'''
    dmstat.punlearn()
    dmstat.infile = image+'[cols '+coord+']'
    dmstat()
    return float(dmstat.out_min)


def check_counts(evt2,region):
    '''
    Check to see if the proposed annulus contains enough counts
    PARAMETERS:
        evt2 - evt file name
        region - proposed annulus region file name
    '''
    dmextract.punlearn()
    #make sure we are reading the right format
    if evt2.split('.')[-1] == 'img':
        dmextract.infile = evt2.split('.')[0]+".img[bin sky=region("+region+")]"
    elif evt2.split('.')[-1] == 'fits':
        '''dmcopy.punlearn()
        dmcopy.infile = evt2
        dmcopy.outfile = evt2.split('.')[0]+".img"
        dmcopy.option = "IMAGE"
        dmcopy.clobber = True
        dmcopy()'''
        dmextract.infile = evt2.split('.')[0]+".fits[bin sky=region("+region+")]"
    else:
        dmextract.infile = evt2+'.img'+"[bin sky=region("+region+")]"
    dmextract.outfile = 'temp.fits'
    dmextract.clobber = True
    dmextract()
    #calculate number of counts
    dmstat.punlearn()
    dmstat.infile = "temp.fits[cols counts]"
    dmstat()
    counts = dmstat.out_mean.split(',')[0]
    return float(counts)


def annuli_obs(home_dir,obsids,exp_corr,cen_ra,cen_dec,merge_bool):
    '''
    Create annuli for an observation
    PARAMETERS:
        home_dir - directory of Chandra data
        obsids - list of observation IDS
        exp_corr - name of exposure corrected file
        cen_ra - ra for X-ray centroid
        cen_dec - dec for X-ray centroid
    '''
    for obsid in obsids:
        #Change to image coordinates for each obsid
        evt2 = home_dir+'/'+obsid+'/repro/acisf'+obsid+'_repro_evt2_uncontam'
        #calculate image units from ra/dec
        '''dmcoords.punlearn()
        dmcoords.infile = evt2 + '.fits'  # OBSID+'_broad_thresh.img'
        dmcoords.option = 'cel'
        dmcoords.ra = cen_ra
        dmcoords.dec = cen_dec
        dmcoords()
        x = dmcoords.x
        y = dmcoords.y'''
        #Copy annuli into obsid directory
        new_loc = home_dir+'/'+obsid+'/repro/Annuli'
        if os.path.isdir(new_loc):
            shutil.rmtree(new_loc)
        shutil.copytree(os.getcwd()+'/Annuli',new_loc)
        #Update x and y coordinates for specific obsid
        '''for file in os.listdir(new_loc):
            if file.endswith('.reg'):
                with open(new_loc+'/'+file,'r') as text_file:
                    filedata = text_file.read()
                with open(new_loc + '/' + file, 'r') as text_file:
                    file_line_data = text_file.readlines()
                #Change each annulus x and y coordinates
                x_merg = str(file_line_data[2].split('(')[1].split(',')[0])
                y_merg = str(file_line_data[2].split('(')[1].split(',')[1])
                filedata = filedata.replace(x_merg,str(x))
                filedata = filedata.replace(y_merg,str(y))
                with open(new_loc+'/'+file,'w') as text_file:
                    text_file.write(filedata)'''

        #Copy the additional files too
        if merge_bool == False:
            add_files = ['bkg.reg']
            with open(home_dir+'/'+obsid+'/repro/'+'pt_srcs.reg','r') as text_file:
                filedata = text_file.readlines()
                if len(filedata) > 2: #only add pt_src to change coordinates if there are pt sources!
                    add_files.append('pt_srcs.reg')
                    add_files.append('AGN.reg')
            for file_add in add_files:
                shutil.copyfile(os.getcwd()+'/'+file_add,home_dir+'/'+obsid+'/repro/'+file_add)
                #move_reg(home_dir,obsid,exp_corr,home_dir+'/'+obsid+'/repro',file_add)

    return None

def move_reg(home_dir,obsid,exp_sub,new_loc,file):
    # We first need to get the logical coordinates from our file
    with open(new_loc+'/'+file,'r') as text_file:
        filedata = text_file.read()
    with open(new_loc + '/' + file, 'r') as text_file:
        file_line_data = text_file.readlines()
    cen_x = str(file_line_data[2].split('(')[1].split(',')[0])
    cen_y = str(file_line_data[2].split('(')[1].split(',')[1])
    evt2 = home_dir+'/'+obsid+'/repro/acisf'+obsid+'_repro_evt2_uncontam'
    #calculate raédec from physical units of the exposure corrected image
    dmcoords.punlearn()
    dmcoords.infile = exp_sub  # OBSID+'_broad_thresh.img'
    dmcoords.option = 'logical'
    dmcoords.logicalx = cen_x
    dmcoords.logicaly = cen_y
    dmcoords()
    ra = dmcoords.ra
    dec = dmcoords.dec
    #calculate image units from ra/dec of the exposure corrected image to the
    # fits file for spectral extraction
    dmcoords.punlearn()
    dmcoords.infile = evt2+'.fits'  # OBSID+'_broad_thresh.img'
    dmcoords.option = 'cel'
    dmcoords.ra = ra
    dmcoords.dec = dec
    dmcoords()
    x = dmcoords.x
    y = dmcoords.y
    #Update x and y coordinates for specific obsid
    filedata = filedata.replace(cen_x,str(x))
    filedata = filedata.replace(cen_y,str(y))
    #Write new file
    with open(new_loc+'/'+file,'w') as text_file:
        text_file.write(filedata)
    return None

def write_reg(region,num,reg_all):
    '''
    Write region to file
    PARAMETERS:
        region - string detailing region
        num - annulus number
        reg_all - file containing list of all regions
    '''
    with open('Annuli/Annulus_'+str(num)+'.reg','w+') as file:
        file.write("# Region file format: DS9 version 4.1 \n")
        file.write("physical \n")
        file.write(region)
    reg_all.write(region+'\n')
    return None

def create_annuli(main_out,evt2,centrd,edge,num_ann,threshold):
    '''
    Create annuli containing minimum number of counts
    PARAMETERS:
        main_out - main output file for relevant information
        evt2 - event file name
        centrd - X-ray centroid [x_coord,y_coord] in physical units
        edge - maximum radius
        num_ann - maximum number of annuli
        threshold - minimum number of counts per annulus
    Event is in physical/sky units
    '''
    #Clear Annuli directory
    if os.path.exists(os.getcwd()+'/Annuli'):
        shutil.rmtree(os.getcwd()+'/Annuli')
    os.makedirs(os.getcwd()+'/Annuli')
    reg_all = open('Annuli/reg_all.reg','w+')
    reg_all.write("# Region file format: DS9 version 4.1 \n")
    reg_all.write("physical \n")
    #Prepare for annuli creation
    #get centroid points
    dmcoords.punlearn()
    dmcoords.infile = evt2
    dmcoords.option = 'cel'
    dmcoords.ra = centrd[0]
    dmcoords.dec = centrd[1]
    dmcoords()
    cen_x = dmcoords.x
    cen_y = dmcoords.y
    #get edge points
    dmcoords.punlearn()
    dmcoords.infile = evt2
    dmcoords.option = 'cel'
    dmcoords.ra = edge[0]
    dmcoords.dec = edge[1]
    dmcoords()
    edge_x = dmcoords.x
    edge_y = dmcoords.y
    annuli_num = 1
    annuli_data = dict()
    inner_ann = 0
    max_rad = np.sqrt((float(cen_x)-float(edge_x))**2+(float(cen_y)-float(edge_y))**2)
    max_rad = 0.492*max_rad
    none_enough = True #Did we create a single annulus??
    region = None # Simply initializing
    for step in range(num_ann-1):
        #Try to make a new annulus
        new_rad = (step+1)*max_rad/num_ann
        with open('test.reg','w+') as new_reg:
            new_reg.write("# Region file format: DS9 version 4.1 \n")
            new_reg.write("physical \n")
            new_reg.write('annulus(%s,%s,%.3f'%(centrd[0],centrd[1],inner_ann)+'"'+',%.3f'%(new_rad)+'")')
        # Make sure there are enough counts in annulus. If not then extend annulus
        if check_counts(evt2,'test.reg') > threshold:
            annuli_data[annuli_num] = new_rad
            write_reg('annulus(%s,%s,%.3f'%(centrd[0],centrd[1],inner_ann)+'"'+',%.3f'%(new_rad)+'")',annuli_num,reg_all)
            inner_ann = new_rad
            annuli_num += 1
            none_enough = False
    if none_enough == True:
        #we stil havent made a single annulus! So let's just make one at the max distanc
        annuli_data[annuli_num] = new_rad
        write_reg('annulus(%s,%s,%.3f'%(centrd[0],centrd[1],inner_ann)+'"'+',%.3f'%(new_rad)+'")',annuli_num,reg_all)
        annuli_num += 1
    reg_all.close()
    main_out.write("We have a total of %i annuli \n" % annuli_num)
    return annuli_data,max_rad




def create_src_img(repro_img,centrd,edge):
    '''
    Create nice background subtracted image with the centroid marked
    '''
    #Change ra dec to physical coordinates for center
    dmcoords.punlearn()
    dmcoords.infile = repro_img#OBSID+'_broad_thresh.img'
    dmcoords.option = 'cel'
    dmcoords.celfmt = 'hms'
    dmcoords.ra = centrd[0]
    dmcoords.dec = centrd[1]
    dmcoords()
    cen_x = dmcoords.x
    cen_y = dmcoords.y
    cen_logx = dmcoords.logicalx
    cen_logy = dmcoords.logicaly
    #Same for edge
    dmcoords.punlearn()
    dmcoords.infile = repro_img#OBSID+'_broad_thresh.img'
    dmcoords.option = 'cel'
    dmcoords.celfmt = 'hms'
    dmcoords.ra = edge[0]
    dmcoords.dec = edge[1]
    dmcoords()
    edge_x = dmcoords.x
    edge_y = dmcoords.y
    #Be sure that repro_img is the exposure corrected one!
    hdu = fits.open(repro_img)[0]
    wcs = WCS(hdu.header)
    max_rad = np.sqrt((float(cen_x) - float(edge_x)) ** 2 + (float(cen_y) - float(edge_y)) ** 2)
    max_rad = 0.492*max_rad #convert to arcesc from physical/sky units
    ax = plt.subplot(projection=wcs)
    image_data = fits.getdata(repro_img)
    kernel = Gaussian2DKernel(x_stddev=3)
    astropy_conv = convolve(image_data, kernel)
    #get background info
    ax.imshow(np.arcsinh(astropy_conv), cmap='gist_heat',vmin=0,vmax=np.max(np.arcsinh(astropy_conv))/10)
    circle = plt.Circle((cen_logx, cen_logy), max_rad, color='green', fill=False)
    ax.add_artist(circle)
    scale = 5
    plt.xlabel('RA J2000')
    plt.ylabel("DEC J2000")
    plt.savefig('bkgsub_exp.png',bbox_inches='tight')
    #Create background region
    reg_bkg = open('bkg.reg','w+')
    reg_bkg.write("# Region file format: DS9 version 4.1 \n")
    reg_bkg.write("physical \n")
    reg_bkg.write('annulus(%s,%s,%f'%(centrd[0],centrd[1],1.1*max_rad)+'"'+',%f'%(1.5*max_rad)+'")')
    reg_bkg.close()
    return None
