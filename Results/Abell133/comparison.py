'''
Program to verify that we are recovering an appropriate luminosity value
'''
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


fig,ax = plt.subplots()
#Read in Data
Abell133_lit = pd.read_csv("Abell133_lit.csv")
Abell133_lit_rad = Abell133_lit['Radius']; Abell133_lit_temp = Abell133_lit['Temperature']

Abell133 = pd.read_csv("Abell133.csv")
Abell133_rad = Abell133['Region']; Abell133_temp = Abell133['Temperature']
region = []
for reg in Abell133_rad:
    region.append(float(reg.split('-')[-1]))
plt.scatter(Abell133_lit_rad,Abell133_lit_temp,label='Archival')
plt.scatter(region,Abell133_temp,label='Pipeline Results')
plt.xlabel(r'R (kpc)')
plt.ylabel(r'kT (keV)')
xmin, xmax = ax.get_xlim()
ax.set_xticks(np.round(np.linspace(xmin, xmax, 10), 1))
plt.title("Abell 133 Temperature Profile")
plt.legend()
plt.savefig('Abell133_comparison.png')
