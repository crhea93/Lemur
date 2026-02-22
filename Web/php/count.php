
<?php



$servername = getenv('DB_HOST') ?: "localhost";
$username = getenv('DB_USER') ?: "";
$password = getenv('DB_PASSWORD') ?: "";
$dbname = getenv('DB_NAME') ?: "id9499302_lemur_db";

// Create connection
$conn = new mysqli($servername, $username, $password, $dbname);
// Check connection
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

$sql = "SELECT COUNT(*) FROM Clusters";
$result = $conn->query($sql);

if ($result->num_rows > 0) {
    while($row = $result->fetch_assoc()) {
        echo json_encode($row['COUNT(*)']);
        }
} else {
    echo "Couldn't Find Clusters";
}

$conn->close();
