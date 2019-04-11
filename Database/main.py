'''
Main file for testing our database commands

'''
import mysql.connector
from Database.Add_new import add_cluster_db
#import data base
mydb = mysql.connector.connect(
  host="localhost",
  user="crhea93",
  passwd="ILoveLuci3!",
  database='Lemur_DB'
)
mycursor = mydb.cursor()
add_cluster_db(mydb,mycursor,'Ophiuchus')
mycursor.close()
mydb.close()