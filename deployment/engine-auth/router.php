<?php
// Authentication-only entry point for the native multiOTP Windows client.
// Keep the vendor web administration endpoint outside the web document root.
header('Cache-Control: no-store');
if ($_SERVER['REQUEST_URI'] === '/health' && $_SERVER['REQUEST_METHOD'] === 'GET') {
    header('Content-Type: application/json');
    echo '{"status":"ok"}';
    exit;
}
if (parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH) !== '/auth' || $_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(404);
    exit;
}
if (intval($_SERVER['CONTENT_LENGTH'] ?? 0) > 65536) {
    http_response_code(413);
    exit;
}
$class_file = getenv('BLISS_ENGINE_CLASS');
$state_dir = getenv('BLISS_ENGINE_STATE');
$secret = getenv('BLISS_ENGINE_SHARED_SECRET');
if (!$class_file || !$state_dir || !$secret || strlen($secret) < 32) {
    http_response_code(503);
    exit;
}
$data = $_POST['data'] ?? '';
if (!is_string($data) || strlen($data) > 65536 || strpos($data, '<multiOTP') === false) {
    http_response_code(400);
    exit;
}
require_once($class_file);
$multiotp = new Multiotp('DefaultCliEncryptionKey', false, rtrim($state_dir, '/\\') . '/');
$multiotp->ForceNoDisplayLog();
$multiotp->SetServerSecret($secret);
$multiotp->SetServerCacheLevel(0);
header('Content-Type: application/xml; charset=utf-8');
$multiotp->XmlServer($data);
