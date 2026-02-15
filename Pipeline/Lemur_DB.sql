-- MySQL dump 10.13  Distrib 5.7.24, for Linux (x86_64)
--
-- Host: 127.0.0.1    Database: carterrhea
-- ------------------------------------------------------
-- Server version	11.8.3-MariaDB-0+deb13u1 from Debian

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `Clusters`
--

DROP TABLE IF EXISTS `Clusters`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `Clusters` (
  `ID` int(11) NOT NULL,
  `Name` varchar(20) NOT NULL,
  `redshift` float NOT NULL,
  `RightAsc` varchar(20) DEFAULT NULL,
  `Declination` varchar(20) DEFAULT NULL,
  `R_cool_3` float DEFAULT NULL,
  `R_cool_7` float DEFAULT NULL,
  `csb_ct` float DEFAULT NULL,
  `csb_pho` float DEFAULT NULL,
  `csb_flux` float DEFAULT NULL
) ENGINE=MyISAM DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `Clusters`
--

LOCK TABLES `Clusters` WRITE;
/*!40000 ALTER TABLE `Clusters` DISABLE KEYS */;
INSERT INTO `Clusters` VALUES (0,'Abell133',0.0566,'01:02:43.636','-21:53:15.24',0,0,NULL,NULL,NULL),(1,'NGC1399',0.004755,'03:37:51.772','-35:18:22.92',0,0,NULL,NULL,NULL);
/*!40000 ALTER TABLE `Clusters` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `Obsids`
--

DROP TABLE IF EXISTS `Obsids`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `Obsids` (
  `ClusterNumber` int(11) DEFAULT NULL,
  `Obsid` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `Obsids`
--

LOCK TABLES `Obsids` WRITE;
/*!40000 ALTER TABLE `Obsids` DISABLE KEYS */;
INSERT INTO `Obsids` VALUES (0,2203),(0,9897),(1,319),(1,320),(1,239);
/*!40000 ALTER TABLE `Obsids` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `Region`
--

DROP TABLE IF EXISTS `Region`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `Region` (
  `idCluster` int(11) NOT NULL,
  `idRegion` int(11) NOT NULL,
  `Area` float NOT NULL,
  `Temp` float NOT NULL,
  `Temp_min` float NOT NULL,
  `Temp_max` float NOT NULL,
  `Abundance` float NOT NULL,
  `Ab_min` float NOT NULL,
  `Ab_max` float NOT NULL,
  `Norm` float NOT NULL,
  `Norm_min` float NOT NULL,
  `Norm_max` float NOT NULL,
  `Flux` float NOT NULL,
  `Luminosity` float DEFAULT NULL,
  `ReducedChiSquare` float NOT NULL,
  `Agn_bool` tinyint(1) DEFAULT NULL,
  `Density` float DEFAULT NULL,
  `Dens_min` float DEFAULT NULL,
  `Dens_max` float DEFAULT NULL,
  `Pressure` float DEFAULT NULL,
  `Press_min` float DEFAULT NULL,
  `Press_max` float DEFAULT NULL,
  `Entropy` float DEFAULT NULL,
  `Entropy_min` float DEFAULT NULL,
  `Entropy_max` float DEFAULT NULL,
  `T_cool` float DEFAULT NULL,
  `T_cool_min` float DEFAULT NULL,
  `T_cool_max` float DEFAULT NULL,
  `AGN` tinyint(1) DEFAULT NULL,
  `R_in` float DEFAULT NULL,
  `R_out` float DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci COMMENT='Contains Region info';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `Region`
--

LOCK TABLES `Region` WRITE;
/*!40000 ALTER TABLE `Region` DISABLE KEYS */;
/*!40000 ALTER TABLE `Region` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `csb`
--

DROP TABLE IF EXISTS `csb`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `csb` (
  `ClusterName` varchar(20) DEFAULT NULL,
  `ID` int(11) DEFAULT NULL,
  `csb_ct` float DEFAULT NULL,
  `csb_ct_l` float NOT NULL,
  `csb_ct_u` float NOT NULL,
  `csb_pho` float NOT NULL,
  `csb_pho_l` float NOT NULL,
  `csb_pho_u` float NOT NULL,
  `csb_flux` float DEFAULT NULL,
  `csb_flux_l` float DEFAULT NULL,
  `csb_flux_u` float DEFAULT NULL
) ENGINE=MyISAM DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `csb`
--

LOCK TABLES `csb` WRITE;
/*!40000 ALTER TABLE `csb` DISABLE KEYS */;
/*!40000 ALTER TABLE `csb` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `r_cool`
--

DROP TABLE IF EXISTS `r_cool`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `r_cool` (
  `ID` int(11) DEFAULT NULL,
  `ClusterName` varchar(20) DEFAULT NULL,
  `r_cool_3` float DEFAULT NULL,
  `r_cool_7` float DEFAULT NULL,
  `r_cool_3_l` float DEFAULT NULL,
  `r_cool_3_u` float DEFAULT NULL,
  `r_cool_7_l` float DEFAULT NULL,
  `r_cool_7_u` float DEFAULT NULL
) ENGINE=MyISAM DEFAULT CHARSET=latin1 COLLATE=latin1_swedish_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `r_cool`
--

LOCK TABLES `r_cool` WRITE;
/*!40000 ALTER TABLE `r_cool` DISABLE KEYS */;
INSERT INTO `r_cool` VALUES (0,'Abell133',0,0,0,0,0,0),(1,'NGC1399',0,0,0,0,0,0);
/*!40000 ALTER TABLE `r_cool` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-02-13 21:54:06
