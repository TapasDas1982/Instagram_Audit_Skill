<?php
/**
 * Instagram Audit Admin Panel — ig-audits.php
 *
 * DELIVERY NOTE: This file belongs in Tapash's PHP studio admin panel repo,
 * NOT in the Instagram_Audit_Skill Python repo. Copy it to admin/ in the
 * PHP project. It reads from the shared MySQL ig_audit database.
 *
 * Prerequisites:
 *   - MySQL ig_audit schema applied (db/schema.sql from Python project)
 *   - $db PDO object available (from the existing admin panel's config.php)
 *   - Fancybox CSS/JS loaded in the admin layout (or add CDN links below)
 *
 * Compatibility: PHP 7.4+
 */

// --- Bootstrap existing admin panel config (provides $db PDO) ---
require_once __DIR__ . '/../config.php';

// --- Pagination ---
$per_page = 20;
$page     = max(1, (int) ($_GET['page'] ?? 1));
$offset   = ($page - 1) * $per_page;

// --- Count total active owned accounts (for pagination) ---
$count_stmt = $db->query(
    "SELECT COUNT(*) FROM accounts WHERE account_type = 'owned' AND is_active = 1"
);
$total_accounts = (int) $count_stmt->fetchColumn();
$total_pages    = max(1, (int) ceil($total_accounts / $per_page));
$page           = min($page, $total_pages);
$offset         = ($page - 1) * $per_page;

// --- Main query: latest audit per active owned account ---
//
// The sub-select fetches the second-most-recent overall_score for trend comparison.
// All user input is bound via PDO prepared statements.
$sql = "
    SELECT
        a.id            AS account_id,
        a.username,
        a.display_name,
        a.studio_location,
        au.id           AS audit_id,
        au.audit_date,
        au.overall_score,
        au.scores_json,
        au.findings_json,
        au.report_path,
        (
            SELECT overall_score
            FROM   audits
            WHERE  account_id = a.id
            ORDER  BY audit_date DESC
            LIMIT  1 OFFSET 1
        ) AS prev_score
    FROM  accounts a
    LEFT  JOIN audits au
        ON au.id = (
            SELECT id
            FROM   audits
            WHERE  account_id = a.id
            ORDER  BY audit_date DESC
            LIMIT  1
        )
    WHERE  a.account_type = 'owned'
      AND  a.is_active = 1
    ORDER  BY a.studio_location, a.username
    LIMIT  :lim OFFSET :off
";

$stmt = $db->prepare($sql);
$stmt->bindValue(':lim', $per_page, PDO::PARAM_INT);
$stmt->bindValue(':off', $offset,   PDO::PARAM_INT);
$stmt->execute();
$accounts = $stmt->fetchAll(PDO::FETCH_ASSOC);

// --- Helpers ---

/**
 * Return an HTML score badge with inline colour coding.
 * Green >= 70, Yellow 50–69, Red < 50.
 */
function score_badge(float|null $score): string {
    if ($score === null) {
        return '<span style="color:#888">—</span>';
    }
    if ($score >= 70) {
        $bg = '#2e7d32'; // green
    } elseif ($score >= 50) {
        $bg = '#f57f17'; // amber
    } else {
        $bg = '#c62828'; // red
    }
    $s = htmlspecialchars(number_format($score, 1), ENT_QUOTES, 'UTF-8');
    return "<span style='background:{$bg};color:#fff;padding:2px 8px;border-radius:4px;font-weight:bold;font-size:0.85em'>{$s}</span>";
}

/**
 * Return a trend arrow comparing current vs previous overall score.
 * Returns plain UTF-8 text (safe to echo directly).
 */
function trend_arrow(float|null $current, float|null $prev): string {
    if ($current === null || $prev === null) {
        return '—';
    }
    $diff = $current - $prev;
    if ($diff > 2.0)  return '↑';
    if ($diff < -2.0) return '↓';
    return '→';
}

/**
 * Decode a JSON column, returning [] on any failure.
 */
function safe_json(string|null $json): array {
    if ($json === null || $json === '') return [];
    $decoded = json_decode($json, true);
    return is_array($decoded) ? $decoded : [];
}

/**
 * Render a per-dimension scorecard HTML table from scores_json.
 * scores_json shape: {"engagement": 75.4, "reels": 60.1, ...}
 */
function render_scorecard(array $scores): string {
    if (empty($scores)) return '<p><em>No score data.</em></p>';
    $html  = '<table style="border-collapse:collapse;width:100%">';
    $html .= '<tr style="background:#f0f4ff"><th style="text-align:left;padding:6px 10px;border:1px solid #ccc">Dimension</th>'
           . '<th style="text-align:right;padding:6px 10px;border:1px solid #ccc">Score / 100</th></tr>';
    foreach ($scores as $dim => $val) {
        $dim_safe = htmlspecialchars(ucfirst((string) $dim), ENT_QUOTES, 'UTF-8');
        $val_safe = htmlspecialchars(is_numeric($val) ? number_format((float) $val, 1) : '—', ENT_QUOTES, 'UTF-8');
        $html .= "<tr><td style='padding:5px 10px;border:1px solid #ccc'>{$dim_safe}</td>"
               . "<td style='text-align:right;padding:5px 10px;border:1px solid #ccc'>{$val_safe}</td></tr>";
    }
    $html .= '</table>';
    return $html;
}

/**
 * Render top-5 findings HTML from findings_json.
 * findings_json shape: {"engagement": [{severity, title, evidence, action, impact, ease}, ...], ...}
 */
function render_top_findings(array $findings_by_dim, int $limit = 5): string {
    if (empty($findings_by_dim)) return '<p><em>No findings data.</em></p>';

    // Flatten across dimensions, preserving dimension label
    $flat = [];
    foreach ($findings_by_dim as $dim => $items) {
        if (!is_array($items)) continue;
        foreach ($items as $f) {
            if (!is_array($f)) continue;
            $f['_dim'] = $dim;
            $flat[]    = $f;
        }
    }

    // Exclude "positive" findings for the top-issues list
    $issues = array_filter($flat, fn($f) => ($f['severity'] ?? '') !== 'positive');
    $issues = array_slice(array_values($issues), 0, $limit);

    if (empty($issues)) return '<p><em>No actionable findings.</em></p>';

    $severity_color = [
        'critical' => '#c62828',
        'warning'  => '#e65100',
        'info'     => '#1565c0',
        'positive' => '#2e7d32',
    ];

    $html = '<ol style="padding-left:1.2em">';
    foreach ($issues as $f) {
        $sev    = htmlspecialchars((string) ($f['severity'] ?? 'info'), ENT_QUOTES, 'UTF-8');
        $title  = htmlspecialchars((string) ($f['title']    ?? ''), ENT_QUOTES, 'UTF-8');
        $evid   = htmlspecialchars((string) ($f['evidence'] ?? ''), ENT_QUOTES, 'UTF-8');
        $action = htmlspecialchars((string) ($f['action']   ?? ''), ENT_QUOTES, 'UTF-8');
        $dim    = htmlspecialchars(ucfirst((string) ($f['_dim'] ?? '')), ENT_QUOTES, 'UTF-8');
        $color  = $severity_color[$f['severity'] ?? ''] ?? '#555';

        $html .= "<li style='margin-bottom:10px'>"
               . "<strong style='color:{$color}'>[{$sev}]</strong> {$title}"
               . ($evid   ? "<br><span style='font-size:0.9em;color:#555'>Evidence: {$evid}</span>"   : '')
               . ($action ? "<br><span style='font-size:0.9em;color:#333'>Action: {$action}</span>"  : '')
               . "<br><span style='font-size:0.8em;color:#888'>{$dim}</span>"
               . "</li>\n";
    }
    $html .= '</ol>';
    return $html;
}

?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Audits — Twist N Turns Admin</title>

    <!-- Fancybox 4 (modal/lightbox for account detail overlay) -->
    <link  rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fancyapps/ui@5/dist/fancybox/fancybox.css">
    <script src="https://cdn.jsdelivr.net/npm/@fancyapps/ui@5/dist/fancybox/fancybox.umd.js" defer></script>

    <style>
        body   { font-family: Arial, sans-serif; color: #222; background: #f8f9fa; }
        h1     { color: #2e5bba; }
        .card  { background: #fff; border-radius: 6px; box-shadow: 0 1px 4px rgba(0,0,0,.1);
                 padding: 20px 24px; margin-bottom: 24px; }
        table  { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px 12px; vertical-align: middle; }
        th     { background: #f0f4ff; font-weight: bold; text-align: left; }
        tr:nth-child(even) td { background: #fafafa; }
        .btn   { display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 0.82em;
                 text-decoration: none; font-weight: bold; cursor: pointer; border: none; }
        .btn-view { background: #2e5bba; color: #fff; }
        .btn-dl   { background: #37474f; color: #fff; }
        .btn:hover { opacity: .85; }
        .pagination { margin-top: 16px; }
        .pagination a  { margin: 0 3px; padding: 4px 10px; border: 1px solid #ccc; border-radius: 3px;
                          text-decoration: none; color: #2e5bba; }
        .pagination a.active { background: #2e5bba; color: #fff; border-color: #2e5bba; }
        /* Modal content (inside Fancybox) */
        .fb-modal { padding: 20px; min-width: 420px; max-width: 680px; }
        .fb-modal h3 { margin-top: 0; color: #2e5bba; }
        .fb-modal h4 { margin: 16px 0 6px; }
    </style>
</head>
<body>

<div class="card">
    <h1>Instagram Audits</h1>
    <p>Latest audit per active owned account &mdash; <?= htmlspecialchars(date('Y-m-d'), ENT_QUOTES, 'UTF-8') ?></p>

    <?php if (empty($accounts)): ?>
        <p><em>No active owned accounts found. Run the Python batch runner to populate the database.</em></p>
    <?php else: ?>

    <table>
        <thead>
            <tr>
                <th>Location</th>
                <th>Account</th>
                <th>Last Audit</th>
                <th>Overall Score</th>
                <th>vs Last Month</th>
                <th>Status</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
        <?php foreach ($accounts as $row):
            $has_audit = ($row['audit_id'] !== null);
            $score     = $has_audit ? (float) $row['overall_score'] : null;
            $prev      = ($row['prev_score'] !== null) ? (float) $row['prev_score'] : null;
            $trend     = trend_arrow($score, $prev);
            $audit_date = $has_audit
                ? htmlspecialchars($row['audit_date'], ENT_QUOTES, 'UTF-8')
                : '—';

            // Determine status badge
            if (!$has_audit) {
                $status_html = '<span style="color:#888">No audit</span>';
            } elseif ($score !== null && $score >= 70) {
                $status_html = '<span style="color:#2e7d32;font-weight:bold">Healthy</span>';
            } elseif ($score !== null && $score >= 50) {
                $status_html = '<span style="color:#f57f17;font-weight:bold">Needs work</span>';
            } else {
                $status_html = '<span style="color:#c62828;font-weight:bold">Critical</span>';
            }

            // Encode modal data as JSON for Fancybox inline content
            $scores_arr   = safe_json($row['scores_json']);
            $findings_arr = safe_json($row['findings_json']);
            $modal_id     = 'modal-' . (int) $row['account_id'];
            $display_name = htmlspecialchars(
                $row['display_name'] ?: $row['username'], ENT_QUOTES, 'UTF-8'
            );
        ?>
            <tr>
                <td><?= htmlspecialchars((string)($row['studio_location'] ?? '—'), ENT_QUOTES, 'UTF-8') ?></td>
                <td>
                    <strong>@<?= htmlspecialchars($row['username'], ENT_QUOTES, 'UTF-8') ?></strong>
                    <?php if ($row['display_name'] && $row['display_name'] !== $row['username']): ?>
                        <br><small style="color:#666"><?= $display_name ?></small>
                    <?php endif; ?>
                </td>
                <td><?= $audit_date ?></td>
                <td><?= score_badge($score) ?></td>
                <td style="font-size:1.2em; text-align:center"><?= htmlspecialchars($trend, ENT_QUOTES, 'UTF-8') ?></td>
                <td><?= $status_html ?></td>
                <td>
                    <?php if ($has_audit): ?>
                        <!-- "View Details" triggers Fancybox inline modal -->
                        <a class="btn btn-view"
                           data-fancybox
                           data-src="#<?= htmlspecialchars($modal_id, ENT_QUOTES, 'UTF-8') ?>"
                           href="javascript:;">View Details</a>
                        &nbsp;
                        <!-- "Download Report" streams the .docx from server -->
                        <a class="btn btn-dl"
                           href="download_report.php?audit_id=<?= (int) $row['audit_id'] ?>">
                            Download .docx
                        </a>
                    <?php else: ?>
                        <span style="color:#aaa;font-size:.85em">No audit yet</span>
                    <?php endif; ?>
                </td>
            </tr>

            <?php if ($has_audit): ?>
            <!-- Hidden modal content — shown by Fancybox when "View Details" is clicked -->
            <div id="<?= htmlspecialchars($modal_id, ENT_QUOTES, 'UTF-8') ?>"
                 class="fb-modal"
                 style="display:none">
                <h3>@<?= htmlspecialchars($row['username'], ENT_QUOTES, 'UTF-8') ?></h3>
                <p style="color:#555">
                    Audit date: <?= $audit_date ?>
                    &nbsp;|&nbsp; Overall: <?= score_badge($score) ?>
                    &nbsp;|&nbsp; Trend: <?= htmlspecialchars($trend, ENT_QUOTES, 'UTF-8') ?>
                </p>

                <h4>Dimension Scores</h4>
                <?= render_scorecard($scores_arr) ?>

                <h4>Top 5 Actionable Findings</h4>
                <?= render_top_findings($findings_arr, 5) ?>
            </div>
            <?php endif; ?>

        <?php endforeach; ?>
        </tbody>
    </table>

    <!-- Pagination -->
    <?php if ($total_pages > 1): ?>
    <div class="pagination">
        <?php for ($p = 1; $p <= $total_pages; $p++): ?>
            <a href="?page=<?= $p ?>"
               class="<?= ($p === $page) ? 'active' : '' ?>">
               <?= $p ?>
            </a>
        <?php endfor; ?>
    </div>
    <?php endif; ?>

    <?php endif; // accounts not empty ?>
</div>

<script>
    // Initialise Fancybox after DOM is ready (the deferred script loads after body)
    document.addEventListener('DOMContentLoaded', function () {
        if (typeof Fancybox !== 'undefined') {
            Fancybox.bind('[data-fancybox]', {
                dragToClose: false,
                animated: true,
            });
        }
    });
</script>

</body>
</html>
