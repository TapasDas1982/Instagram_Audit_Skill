<?php
/**
 * Download a .docx audit report by audit ID.
 *
 * DELIVERY NOTE: This file belongs in Tapash's PHP studio admin panel repo
 * alongside ig-audits.php. It reads report_path from the ig_audit database
 * and streams the file as a browser download.
 *
 * Usage: download_report.php?audit_id=42
 *
 * Security:
 *   - audit_id is cast to int and validated before any DB call.
 *   - The file path comes entirely from the database, never from user input.
 *   - PDO prepared statements are used throughout.
 *
 * Compatibility: PHP 7.4+
 */

// --- Bootstrap existing admin panel config (provides $db PDO) ---
require_once __DIR__ . '/../config.php';

/**
 * Redirect back to the audit listing with an error notice.
 *
 * @param string $message  Human-readable error text (not shown in production; logged here).
 */
function fail_redirect(string $message): void {
    // Log the error server-side without exposing internal paths to the browser.
    error_log('download_report.php: ' . $message);
    header('Location: ig-audits.php?error=' . urlencode('Download failed. Please try again.'));
    exit;
}

// --- Validate audit_id ---
if (!isset($_GET['audit_id']) || !ctype_digit((string) $_GET['audit_id'])) {
    fail_redirect('Missing or non-integer audit_id in request.');
}
$audit_id = (int) $_GET['audit_id'];
if ($audit_id <= 0) {
    fail_redirect("audit_id {$audit_id} is out of range.");
}

// --- Fetch report_path from database ---
$stmt = $db->prepare(
    'SELECT report_path FROM audits WHERE id = :audit_id LIMIT 1'
);
$stmt->bindValue(':audit_id', $audit_id, PDO::PARAM_INT);
$stmt->execute();
$row = $stmt->fetch(PDO::FETCH_ASSOC);

if ($row === false) {
    fail_redirect("No audit row found for id={$audit_id}.");
}

$report_path = (string) ($row['report_path'] ?? '');
if ($report_path === '') {
    fail_redirect("report_path is empty for audit id={$audit_id}.");
}

// --- Verify the file exists and is readable ---
if (!file_exists($report_path)) {
    fail_redirect("Report file not found on disk: {$report_path}");
}
if (!is_readable($report_path)) {
    fail_redirect("Report file is not readable: {$report_path}");
}

// Sanity-check that the path ends in .docx (defence-in-depth; path came from DB)
if (strtolower(pathinfo($report_path, PATHINFO_EXTENSION)) !== 'docx') {
    fail_redirect("Unexpected file extension for audit id={$audit_id}.");
}

// --- Stream the file as a download ---
$filename    = "ig_audit_{$audit_id}.docx";
$file_size   = (int) filesize($report_path);

// Discard any previously buffered output so headers can be sent cleanly
if (ob_get_level()) {
    ob_end_clean();
}

header('Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document');
header('Content-Disposition: attachment; filename="' . $filename . '"');
header('Content-Length: ' . $file_size);
header('Cache-Control: private, no-store, no-cache, must-revalidate');
header('Pragma: no-cache');

readfile($report_path);
exit;
