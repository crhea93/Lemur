-- D1 schema for the API routes used by this project.
-- Keeps table names/columns aligned with api/app.py and Web UI expectations.

CREATE TABLE IF NOT EXISTS Clusters (
    ID INTEGER PRIMARY KEY,
    Name TEXT NOT NULL UNIQUE,
    redshift REAL,
    RightAsc TEXT,
    Declination TEXT,
    R_cool_3 REAL,
    R_cool_7 REAL,
    csb_ct REAL,
    csb_pho REAL,
    csb_flux REAL
);

CREATE TABLE IF NOT EXISTS Obsids (
    ClusterNumber INTEGER,
    Obsid INTEGER
);

CREATE TABLE IF NOT EXISTS Region (
    idCluster INTEGER NOT NULL,
    idRegion INTEGER NOT NULL,
    Area REAL,
    Temp REAL,
    Temp_min REAL,
    Temp_max REAL,
    Abundance REAL,
    Ab_min REAL,
    Ab_max REAL,
    Norm REAL,
    Norm_min REAL,
    Norm_max REAL,
    Flux REAL,
    Luminosity REAL,
    ReducedChiSquare REAL,
    Agn_bool INTEGER,
    Density REAL,
    Dens_min REAL,
    Dens_max REAL,
    Pressure REAL,
    Press_min REAL,
    Press_max REAL,
    Entropy REAL,
    Entropy_min REAL,
    Entropy_max REAL,
    T_cool REAL,
    T_cool_min REAL,
    T_cool_max REAL,
    AGN INTEGER,
    R_in REAL,
    R_out REAL,
    PRIMARY KEY (idCluster, idRegion)
);

CREATE INDEX IF NOT EXISTS idx_clusters_name ON Clusters (Name);
CREATE INDEX IF NOT EXISTS idx_obsids_cluster ON Obsids (ClusterNumber);
CREATE INDEX IF NOT EXISTS idx_region_cluster ON Region (idCluster);
