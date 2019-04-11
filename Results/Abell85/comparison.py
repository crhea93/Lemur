'''
Program to verify that we are recovering an appropriate luminosity value
'''
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


fig,ax = plt.subplots()
#Read in Data
Abell85_lit = pd.read_csv("Abell85_lit.csv")
Abell85_lit_rad = Abell85_lit['Radius']; Abell85_lit_temp = Abell85_lit['Temperature']

Abell85 = pd.read_csv("Abell85.csv")
Abell85_rad = Abell85['Region']; Abell85_temp = Abell85['Temperature']
region = []
for reg in Abell85_rad:
    region.append(float(reg.split('-')[-1]))
plt.scatter(Abell85_lit_rad,Abell85_lit_temp,label='Archival')
plt.scatter(region,Abell85_temp,label='Pipeline Results')
plt.xlabel(r'R (kpc)')
plt.ylabel(r'kT (keV)')
xmin, xmax = ax.get_xlim()
ax.set_xticks(np.round(np.linspace(xmin, xmax, 10), 1))
plt.title("Abell 85 Temperature Profile")
plt.legend()
plt.savefig('Abell85_comparison.png')
