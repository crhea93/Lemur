'''
Add an entry to the database
'''

def add_cluster_db(mydb,mycursor,cluster_name,redshift):
    '''
    Add information to cluster table
    :param mydb: my database name
    :param mycursor: cursor name
    :param cluster_name: name of cluster
    :param redshift: redshift of cluster
    :return: none
    '''

    #Check if cluster is already in table
    mycursor.execute(
        "SELECT COUNT(*) FROM Clusters Where Name = %s",
        (cluster_name,)
    )
    (number_of_rows,) = mycursor.fetchone()
    # gets the number of rows affected by the command executed
    mycursor.nextset()
    if number_of_rows == 0:
        # if the cluster doesnt yet exist
        # Lets get the number of clusters current in set
        mycursor.execute("SELECT COUNT(*) FROM Clusters")
        (number_of_rows_curr,) = mycursor.fetchone()
        sql = "INSERT INTO Clusters (ID,Name,redshift) VALUES (%s,%s,%s)"
        val = (number_of_rows_curr,cluster_name, redshift)
        mycursor.execute(sql, val)
        print("Added cluster to database")
    else:
        #Cluster exists
        sql = "UPDATE Clusters SET Name=%s,redshift=%s WHERE Name = %s"
        val = (cluster_name, redshift, cluster_name)
        mycursor.execute(sql, val)
        print("Updated cluster in database")
    mydb.commit()
    return None

def add_coord(mydb,mycursor,cluster_name,ra,dec):
    '''
    Add information to cluster table
    :param mydb: my database name
    :param mycursor: cursor name
    :param cluster_name: name of cluster
    :param ra: right ascension in fk5 J2000
    :param dec: declination in fk5 J2000
    :return: none
    '''

    sql = "UPDATE Clusters SET RightAsc= %s, Declination=%s WHERE Name = %s"
    val = (str(ra), str(dec), cluster_name)
    mycursor.execute(sql, val)
    print("Updated cluster coordinates in database")
    mydb.commit()
    return None

def add_r_cool(mydb,mycursor,cluster_name,R_cool_3,R_cool_7):
    '''
    Add information to cluster table
    :param mydb: my database name
    :param mycursor: cursor name
    :param cluster_name: name of cluster
    :param R_cool_3: Cooling radius at 3 Gyr
    :param R_cool_7: Cooling radius at 7.7 Gyr
    :return: none
    '''
    sql = "UPDATE Clusters SET R_cool_3= %s, R_cool_7=%s WHERE Name = %s"
    val = (str(round(R_cool_3,2)), str(round(R_cool_7,2)), cluster_name)
    mycursor.execute(sql, val)
    print("Updated cluster coordinates in database")
    mydb.commit()
    return None

def add_obsid_db(mydb,mycursor,cluster_name,obsid):
    '''
    Add/update obsid for cluster
    :param mydb: my database name
    :param mycursor: my cursor name
    :param cluster_name: name of cluster
    :param obsid: obsid of cluster
    :return: none
    '''
    #Get ID for cluster from Clusters table
    mycursor.execute("SELECT ID FROM Clusters WHERE Name = %s",(cluster_name,))
    (id,) = mycursor.fetchone()
    mycursor.nextset()
    #Check if obsid is already associated with cluster id in obsids table
    mycursor.execute("SELECT COUNT(*) FROM Obsids Where ClusterNumber = %s",(id,))
    (number_of_rows,) = mycursor.fetchone()
    # gets the number of rows affected by the command executed
    mycursor.nextset()
    if number_of_rows == 0:
        #If the obsid isnt added yet...
        sql = "INSERT INTO Obsids (ClusterNumber, Obsid) VALUES (%s,%s)"
        vals = (id, obsid)
        mycursor.execute(sql,vals)
        print("Added OBSID to database")
    else:
        pass
    mydb.commit()
    return None

def add_fit_db(mydb,mycursor,clust_name,reg_id,area,temp,temp_min,temp_max,abund,ab_min,ab_max,norm,norm_min,norm_max,flux,redchisq,agn_):
    '''
    Add fit parameters to database containing regions for each cluster
    :param clust_name: name of cluster
    :param reg_id: id of region (annulus)
    :param area: inner and outer radius of cluster separated by a hyphen
    :param temp: temperature value from fit
    :param temp_min: lower error value for temperature
    :param temp_max: upper error value for temperature
    :param abund: metal abundance value from fit
    :param ab_min: lower error value for metal abundance
    :param ab_max: upper error value for metal abundance
    :param norm: normalization parameter from fit
    :param norm_min: lower error value for normalization
    :param norm_max: upper error value for normalization
    :param flux: flux value from fit
    :param redchisq: reduced chi square value from fit
    :param agn_: is an AGN present in this region
    '''
    #Get ID for cluster from Clusters table
    mycursor.execute("SELECT ID FROM Clusters WHERE Name = %s",(clust_name,))
    (id,) = mycursor.fetchone()
    mycursor.nextset()
    #Check if obsid is already associated with cluster id in obsids table
    mycursor.execute("SELECT COUNT(*) FROM Region Where idCluster = %s AND idRegion = %s",(id,reg_id))
    (number_of_rows,) = mycursor.fetchone()
    # gets the number of rows affected by the command executed
    mycursor.nextset()
    if number_of_rows == 0:
        # if the cluster doesnt yet exist
        sql = "INSERT INTO Region (idCluster,idRegion,Area,Temp,Temp_min,Temp_max,Abundance,Ab_min,Ab_max,Norm,Norm_min,Norm_max,Flux,ReducedChiSquare,AGN) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        val = (id,int(reg_id),area,temp,temp_min,temp_max,abund,ab_min,ab_max,norm,norm_min,norm_max,flux,redchisq,agn_)
        mycursor.execute(sql, val)
    else:
        #Cluster exists
        sql = "UPDATE Region SET Area=%s,Temp=%s,Temp_min=%s,Temp_max=%s,Abundance=%s,Ab_min=%s,Ab_max=%s,Norm=%s,Norm_min=%s,Norm_max=%s,Flux=%s,ReducedChiSquare=%s,AGN=%s WHERE idCluster = %s AND idRegion = %s"
        val = (area,temp,temp_min,temp_max,abund,ab_min,ab_max,norm,norm_min,norm_max,flux,redchisq,agn_,id,int(reg_id))
        mycursor.execute(sql, val)
    mydb.commit()
    return None
