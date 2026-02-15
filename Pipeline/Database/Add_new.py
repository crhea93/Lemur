"""
Add an entry to the database
"""


def add_cluster_db(mydb, mycursor, cluster_name, redshift):
    """
    Add information to cluster table
    :param mydb: my database name
    :param mycursor: cursor name
    :param cluster_name: name of cluster
    :param redshift: redshift of cluster
    :return: none
    """

    # Check if cluster is already in table
    mycursor.execute("SELECT COUNT(*) FROM Clusters Where Name = %s", (cluster_name,))
    (number_of_rows,) = mycursor.fetchone()
    # gets the number of rows affected by the command executed
    mycursor.nextset()
    if number_of_rows == 0:
        # if the cluster doesnt yet exist
        # Lets get the number of clusters current in set
        mycursor.execute("SELECT ID FROM Clusters")
        Ids = mycursor.fetchall()
        ids_ = [id_v[0] for id_v in Ids]
        if not ids_:
            id_ = 0
        else:
            try:
                id_ = next(a for a, b in enumerate(sorted(ids_), ids_[0]) if a != b)
            except StopIteration:
                id_ = len(ids_)
        sql = "INSERT INTO Clusters (ID,Name,redshift) VALUES (%s,%s,%s)"
        val = (id_, cluster_name, redshift)
        mycursor.execute(sql, val)
        print("Added cluster to database")
    else:
        # Cluster exists
        sql = "UPDATE Clusters SET Name=%s,redshift=%s WHERE Name = %s"
        val = (cluster_name, redshift, cluster_name)
        mycursor.execute(sql, val)
        print("Updated cluster in database")
    mydb.commit()
    return None


def add_coord(mydb, mycursor, cluster_name, ra, dec):
    """
    Add information to cluster table
    :param mydb: my database name
    :param mycursor: cursor name
    :param cluster_name: name of cluster
    :param ra: right ascension in fk5 J2000
    :param dec: declination in fk5 J2000
    :return: none
    """

    sql = "UPDATE Clusters SET RightAsc= %s, Declination=%s WHERE Name = %s"
    val = (str(ra), str(dec), cluster_name)
    mycursor.execute(sql, val)
    print("Updated cluster coordinates in database")
    mydb.commit()
    return None


def add_csb(
    mydb,
    mycursor,
    cluster_id,
    cluster_name,
    csb_ct,
    csb_ct_l,
    csb_ct_u,
    csb_pho,
    csb_pho_l,
    csb_pho_u,
    csb_flux,
    csb_flux_l,
    csb_flux_u,
):
    """
    Add information to cluster table
    :param mydb: my database name
    :param mycursor: cursor name
    :param cluster_name: name of cluster
    :param csb_ct: coefficient of surface brightness in cts per sec
    :param csb_pho: coefficient of surface brightness in photons/sec/cm^2
    :return: none
    """
    # update cluster db
    sql = "UPDATE Clusters SET CSB_ct= %s, CSB_pho=%s, csb_flux=%s  WHERE Name = %s"
    val = (str(csb_ct), str(csb_pho), str(csb_flux), cluster_name)
    mycursor.execute(sql, val)
    print("Updated cluster coordinates in database")
    mydb.commit()
    # Check if obsid is already associated with cluster id in obsids table
    mycursor.execute("SELECT COUNT(*) FROM csb Where ClusterName = %s", (cluster_name,))
    (number_of_rows,) = mycursor.fetchone()
    # gets the number of rows affected by the command executed
    mycursor.nextset()
    if number_of_rows == 0:
        # if the cluster doesnt yet exist
        sql = "INSERT INTO csb (ClusterName,ID,csb_ct,csb_ct_l,csb_ct_u,csb_pho,csb_pho_l,csb_pho_u,csb_flux,csb_flux_l,csb_flux_u) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        val = (
            cluster_name,
            cluster_id,
            csb_ct,
            csb_ct_l,
            csb_ct_u,
            csb_pho,
            csb_pho_l,
            csb_pho_u,
            csb_flux,
            csb_flux_l,
            csb_flux_u,
        )
        mycursor.execute(sql, val)
    else:
        # Cluster exists
        sql = "UPDATE csb SET csb_ct=%s,csb_ct_l=%s,csb_ct_u=%s,csb_pho=%s,csb_pho_l=%s,csb_pho_u=%s,csb_flux=%s,csb_flux_l=%s,csb_flux_u=%s WHERE ClusterName = %s"
        val = (
            csb_ct,
            csb_ct_l,
            csb_ct_u,
            csb_pho,
            csb_pho_l,
            csb_pho_u,
            csb_flux,
            csb_flux_l,
            csb_flux_u,
            cluster_name,
        )
        mycursor.execute(sql, val)
    mydb.commit()
    return None


def add_r_cool(
    mydb,
    mycursor,
    cluster_id,
    cluster_name,
    R_cool_3,
    R_cool_3_l,
    R_cool_3_u,
    R_cool_7,
    R_cool_7_l,
    R_cool_7_u,
):
    """
    Add information to cluster table
    :param mydb: my database name
    :param mycursor: cursor name
    :param cluster_name: name of cluster
    :param R_cool_3: Cooling radius at 3 Gyr
    :param R_cool_7: Cooling radius at 7.7 Gyr
    :return: none
    """
    sql = "UPDATE Clusters SET R_cool_3= %s, R_cool_7=%s WHERE ID = %s"
    val = (str(round(R_cool_3, 2)), str(round(R_cool_7, 2)), cluster_id)
    mycursor.execute(sql, val)
    mydb.commit()
    # add all info
    mycursor.execute("SELECT COUNT(*) FROM r_cool Where ID = %s", (cluster_id,))
    (number_of_rows,) = mycursor.fetchone()
    # gets the number of rows affected by the command executed
    mycursor.nextset()
    if number_of_rows == 0:
        sql = "INSERT INTO r_cool (ID,ClusterName,R_cool_3,R_cool_3_l,R_cool_3_u,R_cool_7,R_cool_7_l,R_cool_7_u) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
        val = (
            cluster_id,
            cluster_name,
            str(R_cool_3),
            str(R_cool_3_l),
            str(R_cool_3_u),
            str(R_cool_7),
            str(R_cool_7_l),
            str(R_cool_7_u),
        )
    else:
        sql = "UPDATE r_cool SET R_cool_3= %s,R_cool_3_l= %s,R_cool_3_u= %s, R_cool_7=%s,R_cool_7_l=%s,R_cool_7_u=%s WHERE ID = %s"
        val = (
            str(round(R_cool_3, 2)),
            str(round(R_cool_3_l, 2)),
            str(round(R_cool_3_u, 2)),
            str(round(R_cool_7, 2)),
            str(round(R_cool_7_l, 2)),
            str(round(R_cool_7_u, 2)),
            cluster_id,
        )
    mycursor.execute(sql, val)
    mydb.commit()
    return None


def get_id(mydb, mycursor, cluster_name):
    """
    Get cluster ID from Name
    :param mydb: my database name
    :param mycursor: cursor name
    :param cluster_name: name of cluster
    :return: cluster ID
    """
    sql = "SELECT ID FROM Clusters WHERE Name = %s"
    val = (cluster_name,)
    mycursor.execute(sql, val)
    records = mycursor.fetchall()
    for row in records:
        id = row[0]
    mydb.commit()
    return id


def add_obsid_db(mydb, mycursor, cluster_name, obsid):
    """
    Add/update obsid for cluster
    :param mydb: my database name
    :param mycursor: my cursor name
    :param cluster_name: name of cluster
    :param obsid: obsid of cluster
    :return: none
    """
    # Get ID for cluster from Clusters table
    mycursor.execute("SELECT ID FROM Clusters WHERE Name = %s", (cluster_name,))
    (id,) = mycursor.fetchone()
    mycursor.nextset()
    # Check if obsid is already associated with cluster id in obsids table
    mycursor.execute(
        "SELECT COUNT(*) FROM Obsids Where ClusterNumber = %s AND Obsid=%s",
        (id, str(obsid)),
    )
    (number_of_rows,) = mycursor.fetchone()
    # gets the number of rows affected by the command executed
    mycursor.nextset()
    if number_of_rows == 0:
        # If the obsid isnt added yet...
        sql = "INSERT INTO Obsids (ClusterNumber, Obsid) VALUES (%s,%s)"
        vals = (id, obsid)
        mycursor.execute(sql, vals)
        print("  Added ObsID to database")
    else:
        pass
    mydb.commit()
    return None


def add_fit_db(
    mydb,
    mycursor,
    clust_name,
    reg_id,
    r_in,
    r_out,
    area,
    temp,
    temp_min,
    temp_max,
    abund,
    ab_min,
    ab_max,
    norm,
    norm_min,
    norm_max,
    flux,
    redchisq,
    agn_,
):
    """
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
    """
    # Get ID for cluster from Clusters table
    mycursor.execute("SELECT ID FROM Clusters WHERE Name = %s", (clust_name,))
    (id,) = mycursor.fetchone()
    mycursor.nextset()
    # Check if obsid is already associated with cluster id in obsids table
    mycursor.execute(
        "SELECT COUNT(*) FROM Region Where idCluster = %s AND idRegion = %s",
        (id, reg_id),
    )
    (number_of_rows,) = mycursor.fetchone()
    # gets the number of rows affected by the command executed
    mycursor.nextset()
    if number_of_rows == 0:
        # if the cluster doesnt yet exist
        sql = "INSERT INTO Region (idCluster,idRegion,r_in,r_out,Area,Temp,Temp_min,Temp_max,Abundance,Ab_min,Ab_max,Norm,Norm_min,Norm_max,Flux,ReducedChiSquare,AGN) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        val = (
            id,
            int(reg_id),
            r_in,
            r_out,
            area,
            temp,
            temp_min,
            temp_max,
            abund,
            ab_min,
            ab_max,
            norm,
            norm_min,
            norm_max,
            flux,
            redchisq,
            agn_,
        )
        mycursor.execute(sql, val)
    else:
        # Cluster exists
        sql = "UPDATE Region SET R_in=%s,R_out=%s,Area=%s,Temp=%s,Temp_min=%s,Temp_max=%s,Abundance=%s,Ab_min=%s,Ab_max=%s,Norm=%s,Norm_min=%s,Norm_max=%s,Flux=%s,ReducedChiSquare=%s,AGN=%s WHERE idCluster = %s AND idRegion = %s"
        val = (
            r_in,
            r_out,
            area,
            temp,
            temp_min,
            temp_max,
            abund,
            ab_min,
            ab_max,
            norm,
            norm_min,
            norm_max,
            flux,
            redchisq,
            agn_,
            id,
            int(reg_id),
        )
        mycursor.execute(sql, val)
    mydb.commit()
    return None


def add_fit_additional_db(
    mydb,
    mycursor,
    clust_name,
    reg_id,
    Lum,
    dens,
    dens_min,
    dens_max,
    press,
    press_min,
    press_max,
    entr,
    entr_min,
    entr_max,
    t_cool,
    t_cool_min,
    t_cool_max,
):
    """
    Add fit parameters to database containing regions for each cluster
    :param clust_name: name of cluster
    :param reg_id: id of region (annulus)
    :param Lum: Luminosity of region
    :param dens: Density of region
    :param dens_min: Minimum Density of region
    :param dens_max: Maximum Density of region
    :param press: Pressure of region
    :param press_min: Minimum Pressure of region
    :param press_max: Maximum Pressure of region
    :param entr: Entropy of region
    :param entr_min: Minimum Entropy of region
    :param entr_max: Maximum Entropy of region
    :param t_cool: Cooling Time of region
    :param t_cool_min: Minimum Cooling Time of region
    :param t_cool_max: Maximum Cooling Time of region
    """
    # Get ID for cluster from Clusters table
    mycursor.execute("SELECT ID FROM Clusters WHERE Name = %s", (clust_name,))
    (id,) = mycursor.fetchone()
    mycursor.nextset()
    sql = "UPDATE Region SET Luminosity=%s,Density=%s,Dens_min=%s,Dens_max=%s,Pressure=%s,Press_min=%s,Press_max=%s,Entropy=%s,Entropy_min=%s,Entropy_max=%s,T_cool=%s,T_cool_min=%s,T_cool_max=%s WHERE idCluster = %s AND idRegion = %s"
    val = (
        Lum,
        dens,
        dens_min,
        dens_max,
        press,
        press_min,
        press_max,
        entr,
        entr_min,
        entr_max,
        t_cool,
        t_cool_min,
        t_cool_max,
        id,
        int(reg_id),
    )
    mycursor.execute(sql, val)
    mydb.commit()
    return None
