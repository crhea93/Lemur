'''
Main file for testing our database commands

'''
import mysql.connector
from Add_new import add_obsid_db,add_cluster_db
#import data base
mydb = mysql.connector.connect(
  host="localhost",
  user="carterrhea93",
  passwd="----",
  database='Lemur_DB'
)
mycursor = mydb.cursor()
add_cluster_db(mydb,mycursor,'Ophiuchus','10:49','+56:40',0.5)
add_obsid_db(mydb,mycursor,'Ophiuchus',2021)
mycursor.close()
mydb.close()
