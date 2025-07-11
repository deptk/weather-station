<?php
// Настройки подключения к БД
$host = 'localhost';
$db   = 'YOU_DB_NAME';
$user = 'YOU_USER';
$pass = 'YOU_PASSWORD';
$port = '5432';

// Чтение JSON из POST
$json = file_get_contents('php://input');
$data = json_decode($json, true);

// Проверка данных
if (!isset($data['outdoor']) || !isset($data['indoor']) || !isset($data['pressure_mmhg']) || !isset($data['pressure_hpa'])) {
	http_response_code(400);
	echo json_encode(['status' => 'error', 'message' => 'Missing fields']);
	exit;
}

try {
	// Подключение к PostgreSQL через PDO
	$pdo = new PDO("pgsql:host=$host;port=$port;dbname=$db", $user, $pass);
	$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

	// Подготовка запроса
	$stmt = $pdo->prepare("INSERT INTO weather_data (outdoor_temp, indoor_temp, pressure_mmhg, pressure_hpa) VALUES (:outdoor, :indoor, :pressure_mmhg, :pressure_hpa)");
	$stmt->execute([
		':outdoor' => $data['outdoor'],
		':indoor' => $data['indoor'],
		':pressure_mmhg' => $data['pressure_mmhg'],
		':pressure_hpa' => $data['pressure_hpa']
	]);

	echo json_encode(['status' => 'ok']);
} catch (PDOException $e) {
	http_response_code(500);
	echo json_encode(['status' => 'error', 'message' => $e->getMessage()]);
}
?>
