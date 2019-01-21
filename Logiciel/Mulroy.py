'''
This python file replicates the Mass-Luminosity relation for M_500(10**14 M_s) and L_500(10**12 L_s)
in figure 2 on page 5 of https://arxiv.org/pdf/1407.1767.pdf
The data was taken from table 1 on page 3
'''

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import chisquare
from matplotlib.lines import Line2D
from astropy.modeling import fitting
from astropy.modeling import Fittable1DModel, Parameter
from astropy.stats.info_theory import bayesian_info_criterion_lsq

#-------------------------INPUTS---------------------------#
output_dir = '../Results/'
#----------------------------------------------------------#

class Cluster:
    def __init__(self,clus):
        self.name = clus['Name']
        self.redshift = clus['Redshift']
        self.M_500 = clus['M_500']
        self.M_upper = clus['M_upper']
        self.M_lower = clus['M_lower']
        self.L_500 = clus['L_500']
        self.L_upper = clus['L_upper']
        self.L_lower = clus['L_lower']
        self.T = clus['Tx']
        self.T_upper = clus['Tx_upper']
        self.T_lower = clus['Tx_lower']
        self.CoolCore = clus['CoolCore']

def temp_mass(temp,temp_up,temp_low):
    M = .255*temp**1.58  #10^14 Solar Masses
    M_up = .284*temp_up**1.64
    M_low = .230*temp_low**1.51

    return np.round(M,2),np.round(M_up-M,2),np.round(M-M_low,2)


fig,ax = plt.subplots()
#Read in Data
Lit_df = pd.read_csv("Clusters.csv")
Lit_df = Lit_df.fillna(0)
#Calculate Each Group
L = Lit_df['L_500']
M = Lit_df['M_500']
T = Lit_df['Tx']
clusters = []
for index, row in Lit_df.iterrows():
    clusters.append(Cluster(row))
#Create Color sets for error bar plotting
colors_dic = {'NCC':'red','CC':'blue','none':'green'}
def pltcolor(lst):
    cols=[]
    for l in lst:
        l = str(l)
        if l.upper()=='NCC':
            cols.append(colors_dic['NCC'])
        elif l.upper()=='CC':
            cols.append(colors_dic['CC'])
        else:
            cols.append(colors_dic['none'])
    return cols
# Create the colors list using the function above

# Define Model
class ScalingRel(Fittable1DModel):
    a = Parameter()
    b = Parameter()
    @staticmethod
    def evaluate(x, a, b):
        return a * x ** b
    @staticmethod
    def fit_deriv(x, a, b):
        a_der = x**b
        b_der = a*b*x**(b-1)
        return [a_der, b_der]
ScalingRelation = ScalingRel(a=0.5,b=0.9)
fit_t = fitting.LevMarLSQFitter()

#If we have temperature instead of mass lets quickly calculate the relavent masses
for cluster in clusters:
    if cluster.M_500 == 0:
        cluster.M_500,cluster.M_upper,cluster.M_lower = temp_mass(cluster.T,cluster.T+cluster.T_upper,cluster.T-cluster.T_lower)
        #xcluster.L_500 = 10*cluster.L_500
#Group stability class
groups = {}
for cluster in clusters:
    if cluster.CoolCore not in groups.keys():
        groups[cluster.CoolCore] = [cluster]
    if cluster.CoolCore in groups.keys():
        groups[cluster.CoolCore].append(cluster)
cols=pltcolor(groups.keys())
#Min/Max info
M_max = Lit_df['M_500'].max()
M_min = Lit_df['M_500'].min()
T_max = Lit_df['Tx'].max()
T_min = Lit_df['Tx'].min()
L_max = Lit_df['L_500'].max()
L_min = Lit_df['L_500'].min()
#Plotting and Fitting for each Category
lum = np.linspace(L_min-1,L_max+1) #Just for plotting
print("Plotting Groups")
grouped = Lit_df.groupby('CoolCore')
Stab_fits = {}
Stab_counts = {}
for group_name,members in groups.iteritems():
    if len(members) > 1: #Only plot if more than one cluster in a group
        L_500 = [cluster.L_500 for cluster in members]
        M_500 = [cluster.M_500 for cluster in members]
        L_upper = [cluster.L_upper for cluster in members]
        L_lower = [cluster.L_lower for cluster in members]
        M_upper = [cluster.M_upper for cluster in members]
        M_lower = [cluster.M_lower for cluster in members]
        print("Plotting %s"%group_name)
        #plot the error bars
        plt.errorbar(L_500, M_500,xerr=(L_lower, L_upper),yerr=(M_lower,M_upper),fmt='s',markersize=0,ecolor=colors_dic[group_name])
        #plot the group itself
        for cluster in members:
            plt.scatter(L_500,M_500,color=colors_dic[group_name])
        #group.plot(ax=ax, kind='scatter', x='L_500', y='M_500',color=colors_dic[key])
        #fit the group and calculate fitting parameters
        t_grp = fit_t(ScalingRelation, L_500, M_500)
        print("We calculate a to be %.2f"%t_grp.parameters[0])
        print("We calculate b to be %.2f"%t_grp.parameters[1])
        #plotting stuff
        plt.plot(lum, t_grp(lum), label=group_name,color=colors_dic[group_name])
        plt.title("NIR Luminosity-Mass Relation for Cluster Type: %s"%group_name)
        plt.xlabel(r"$L/L_{\odot}$")
        plt.ylabel(r"$M/M_{\odot}$")
        plt.ylim(M_min,M_max)
        plt.xlim(L_min,L_max)
        plt.savefig(output_dir+"Lit_Galaxies_"+group_name+".png")
        plt.clf()
        #Set up Values for Statistics
        Stab_fits[group_name] = float(np.sum((t_grp(L_500) - L_500)**2))
        Stab_counts[group_name] = len(M_500)
        chi_sq = chisquare(t_grp(L_500),f_exp=L_500)[0]
        print("Our Reduced Chi Square is %.2f"%(chi_sq/(len(L_500)-1)))
        print("")



print("Plotting Best Fit")

#Plotting Stuff
L = [cluster.L_500 for cluster in clusters]
M = [cluster.M_500 for cluster in clusters]
L_up = [cluster.L_upper for cluster in clusters]
L_down = [cluster.L_lower for cluster in clusters]
M_up = [cluster.M_upper for cluster in clusters]
M_down = [cluster.M_lower for cluster in clusters]
t = fit_t(ScalingRelation, L,M)
# Plot the data with the best-fit model
print("We calculate a to be %.2f"%t.parameters[0])
print("We calculate b to be %.2f"%t.parameters[1])
plt.errorbar(L,M,xerr=(L_down,L_up),yerr=(M_down,M_up),fmt='o',markersize=2,ecolor=cols)
plt.plot(lum, t(lum), label='Best Fit', color='lightblue')
#grouped = Lit_df.groupby('CoolCore')
#for key, group in grouped:
#    group.plot(ax=ax, kind='scatter', x='L_500', y='M_500', label=key, color=colors_dic[key],legend=True)


plt.title("NIR Luminosity-Mass Relation for CC/NCC/Unclassified")
plt.xlabel(r"$L_K(r<500)/10^{12}L_{\odot}$")
plt.ylabel(r"$M_{500}/10^{14}M_{\odot}$")
plt.ylim(M_min-1,M_max+1)
plt.xlim(L_min-1,L_max+1)
#Legend Info
custom_lines = [Line2D([0], [0], color='blue', lw=1),
                Line2D([0], [0], color='red', lw=1),
                Line2D([0], [0], color='green', lw=1),
                Line2D([0], [0], color='lightblue', lw=1)]
plt.legend(custom_lines, ['CC', 'NCC', 'Unknown','Fit'])
plt.savefig(output_dir+"Lit_Galaxies_All.png")
#Set up Values for Statistics
Stab_fits['total'] = np.sum((t(L) - L)**2)
Stab_counts['total'] = len(L)
chi_sq = chisquare(t(L),f_exp=L)[0]
print("Our Reduced Chi Square is %.2f"%(chi_sq/(len(L)-1)))
print("")

#Calculate BICS'''

bic_stable = bayesian_info_criterion_lsq(Stab_fits['NCC'], 2, Stab_counts['NCC'])
bic_cool = bayesian_info_criterion_lsq(Stab_fits['CC'], 2, Stab_counts['CC'])
bic_total = bayesian_info_criterion_lsq(Stab_fits['total'], 2, Stab_counts['total'])
print("The difference between the ungrouped BIC and the Cool Core Cluster BIC is : %.1f"%(bic_total-bic_cool))
print("The difference between the ungrouped BIC and the Stable Cluster BIC is : %.1f"%(bic_total-bic_stable))
