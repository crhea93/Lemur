-- MySQL dump 10.13  Distrib 5.1.73, for redhat-linux-gnu (x86_64)
--
-- Host: localhost    Database: carterrhea
-- ------------------------------------------------------
-- Server version	5.1.73

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
) ENGINE=MyISAM DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `Clusters`
--

LOCK TABLES `Clusters` WRITE;
/*!40000 ALTER TABLE `Clusters` DISABLE KEYS */;
INSERT INTO `Clusters` VALUES (0,'Abell133',0.0566,'01:02:41.957','-21:52:54.95',232.12,232.12,0.169,0.154,0.152),(1,'AS780',0.236,'14:59:28.765','-18:10:45.21',111.09,175.68,0.105,0.104,0.104);
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
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `Obsids`
--

LOCK TABLES `Obsids` WRITE;
/*!40000 ALTER TABLE `Obsids` DISABLE KEYS */;
INSERT INTO `Obsids` VALUES (1,9428),(0,2203);
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
) ENGINE=InnoDB DEFAULT CHARSET=latin1 COMMENT='Contains Region info';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `Region`
--

LOCK TABLES `Region` WRITE;
/*!40000 ALTER TABLE `Region` DISABLE KEYS */;
INSERT INTO `Region` VALUES (1,1,-15158,3.23265,0,0,0.63566,0,0,0.0009361,-5.26748e-05,5.26748e-05,-12.0358,3.40282e+38,0.642321,NULL,0.0652843,0.063421,0.067096,6.76252e-10,6.5695e-10,6.95018e-10,19.9382,20.3268,19.5777,0.960188,0.932782,0.986834,1,0,15.3527),(1,2,-49885.1,3.56256,-0.649961,0.649961,0.588506,-0.238318,0.238318,0.00109161,-8.00465e-05,8.00465e-05,-11.9598,3.40282e+38,0.653617,NULL,0.0388612,0.0374092,0.0402608,4.43629e-10,3.49141e-10,5.43458e-10,31.0517,26.0393,35.8609,1.7403,1.36964,2.13192,0,15.3527,24.9481),(1,3,-171800,4.03769,-0.327803,0.327803,0.663539,-0.19415,0.19415,0.000955033,-6.11181e-05,6.11181e-05,-11.9823,3.40282e+38,0.578543,NULL,0.0195869,0.0189498,0.0202039,2.5342e-10,2.25272e-10,2.82625e-10,55.5677,52.1944,58.8495,3.60565,3.20516,4.02118,0,24.9481,38.3817),(1,4,-827085,5.70622,-0.736192,0.736192,0.525146,-0.198969,0.198969,0.00101764,-5.69157e-05,5.69157e-05,-11.9134,3.40282e+38,0.651164,NULL,0.00921489,0.0089535,0.00946908,1.68492e-10,1.42591e-10,1.95478e-10,129.824,115.265,143.938,9.84966,8.33554,11.4272,0,38.3817,63.3298);
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
) ENGINE=MyISAM DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `csb`
--

LOCK TABLES `csb` WRITE;
/*!40000 ALTER TABLE `csb` DISABLE KEYS */;
INSERT INTO `csb` VALUES ('AS780',NULL,0.105,0.1,0.11,0.104,0.099,0.11,0.104,0.099,0.109),('Abell133',0,0.169,0.164,0.175,0.154,0.148,0.16,0.152,0.146,0.158);
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
) ENGINE=MyISAM DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `r_cool`
--

LOCK TABLES `r_cool` WRITE;
/*!40000 ALTER TABLE `r_cool` DISABLE KEYS */;
INSERT INTO `r_cool` VALUES (1,NULL,111.09,175.68,118.32,103.79,189.03,165.67),(0,NULL,232.117,232.117,232.117,232.117,232.117,232.117);
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

-- Dump completed on 2019-05-14 11:03:54
