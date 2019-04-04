'''
Calculate all additional parameters for each annulus:
    - Electron Density
    - Pressure
    - Entropy
    - Cooling time
'''
import numpy as np
from Misc.LSCalc import ls_calc, ds_calc
class annulus:
    '''
    Class used to store all important information for the annulus including data
    from fits and to-be-calculated information
    '''
    def __init__(self,r_in,r_out,temp,temp_min,temp_max,abund,abund_min,abund_max,norm,norm_min,norm_max,flux):
        self.r_in = r_in
        self.r_out = r_out
        self.temp = [temp+temp_min,temp,temp+temp_max]
        self.temp_ergs = [val*1.60218e-9 for val in self.temp]
        self.abund = [abund+abund_min,abund,abund+abund_max]
        self.norm = [norm+norm_min,norm,norm+norm_max]
        self.flux = flux
        self.lum = 0
        self.dens = []
        self.press = []
        self.entropy = []
        self.t_cool = []
        self.vol = 0
        self.Da = 0
        self.dl = 0
    def calc_D(self,z):
        '''
        Calculate comoving distance in kpc
        '''
        dist = ds_calc(z)
        self.Da = dist[0]*3.086e21 #conversion to cm from kpc
        self.dl = dist[1]*3.086e21 #conversion to cm from kpc
    def calc_lum(self):
        '''
        Calculate luminosity from flux
        '''
        self.lum = 10**(self.flux)*4*np.pi*self.dl**2
    def calc_vol(self,z):
        '''
        Calculate volume given inner and outer radii
        '''
        dist_out = ls_calc(z,self.r_out)*3.086e21 #conversion to cm from kpc
        dist_in = ls_calc(z,self.r_in)*3.086e21 #conversion to cm from kpc
        self.vol = (4/3)*np.pi*(dist_out**3-dist_in**3)
    def calc_dens(self,z):
        '''
        Calculate electron density and errors
        '''
        const = 1e7*np.sqrt(4*np.pi)
        red_dep = self.Da*(1+z)
        for i in range(3):
            norm_vol = np.sqrt((1.2*self.norm[i])/self.vol)
            self.dens.append(const*red_dep*norm_vol)
    def calc_press(self):
        '''
        Calculate pressure and errors
        '''
        self.press = [2*self.temp_ergs[i]*self.dens[i] for i in range(3)]
    def calc_entropy(self):
        '''
        Calculate entropy and errors
        '''
        self.entropy = [self.temp[i]*self.dens[i]**(-2/3) for i in range(3)]
    def calc_tcool(self):
        '''
        Calculate cooling time and errors
        '''
        for i in range(3):
            t_sec = (5/2)*((1.91*self.dens[i]*self.temp_ergs[i]*self.vol)/self.lum)
            self.t_cool.append(t_sec*3.17098e-8*1e-9) #year -> Gigayears


def PostProcess(regions,annuli_data,Temperatures,Temp_min,Temp_max,Abundances,Ab_min,Ab_max,Norms,Norm_min,Norm_max,Fluxes,redshift):
    '''
    Create the csv files containing fit information and errors
    '''
    Annuli = []
    for bound in [Temp_min,Temp_max,Norm_min,Norm_max]:
        for i in range(len(bound)):
            if bound[i] == None:
                bound[i] = 0.0
            else:
                bound[i] = float(bound[i])
    #Create csv storage files
    file_to_write = open("Fits/annuli_data.csv",'w+')
    file_to_write.write("Region,Temperature,Abundance,Density,Pressure,Entropy,T_Cool\n")
    file_min = open("Fits/annuli_data_min.csv",'w+')
    file_min.write("Region,Temperature,Abundance,Density,Pressure,Entropy,T_Cool\n")
    file_max = open("Fits/annuli_data_max.csv",'w+')
    file_max.write("Region,Temperature,Abundance,Density,Pressure,Entropy,T_Cool\n")
    #Go through each annuli
    for ann in range(len(annuli_data)):
        region = ''
        if ann == 0:
            Annuli.append(annulus(0.0,annuli_data[ann],Temperatures[ann],Temp_min[ann],Temp_max[ann],Abundances[ann],Ab_min[ann],Ab_max[ann],Norms[ann],Norm_min[ann],Norm_max[ann],Fluxes[ann]))
            region = '0.0-'+str(annuli_data[ann])
        if ann > 0:
            Annuli.append(annulus(annuli_data[ann-1],annuli_data[ann],Temperatures[ann],Temp_min[ann],Temp_max[ann],Abundances[ann],Ab_min[ann],Ab_max[ann],Norms[ann],Norm_min[ann],Norm_max[ann],Fluxes[ann]))
            region = str(annuli_data[ann-1])+'-'+str(annuli_data[ann])
        #Calculate stuff
        Annuli[ann].calc_D(redshift)
        Annuli[ann].calc_lum()
        Annuli[ann].calc_vol(redshift)
        Annuli[ann].calc_dens(redshift)
        Annuli[ann].calc_press()
        Annuli[ann].calc_entropy()
        Annuli[ann].calc_tcool()
        #Write to files
        file_to_write.write(region + "," + str(Annuli[ann].temp[1]) + "," + str(Annuli[ann].abund[1])+ "," + str(Annuli[ann].dens[1])+ "," + str(Annuli[ann].press[1]) + "," + str(Annuli[ann].entropy[1]) + "," + str(Annuli[ann].t_cool[1])+ "\n")
        file_min.write(region + "," + str(Annuli[ann].temp[0]) + "," + str(Annuli[ann].abund[0])+ "," + str(Annuli[ann].dens[0])+ "," + str(Annuli[ann].press[0]) + "," + str(Annuli[ann].entropy[0]) + "," + str(Annuli[ann].t_cool[0])+ "\n")
        file_max.write(region + "," + str(Annuli[ann].temp[2]) + "," + str(Annuli[ann].abund[2])+ "," + str(Annuli[ann].dens[2])+ "," + str(Annuli[ann].press[2]) + "," + str(Annuli[ann].entropy[2]) + "," + str(Annuli[ann].t_cool[2])+ "\n")
    #Clean up
    file_to_write.close()
    file_min.close()
    file_max.close()
    return Annuli
