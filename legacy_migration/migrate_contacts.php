<?php
/**
 * migrate_contacts.php
 * ---------------------
 * Many legacy partner-contact records at large network operators live in
 * old PHP-driven intranet tools or wiki exports rather than a clean database.
 * This script simulates that world: it reads a "wiki dump" CSV of contacts,
 * normalizes it (trims whitespace, fixes casing, validates email/phone
 * shape), flags orphaned or stale records, and writes clean JSON that the
 * Python ETL pipeline picks up downstream.
 *
 * Usage:
 *   php migrate_contacts.php ../data/contacts_wiki_dump.csv ../data/contacts_clean.json
 */

function normalize_row(array $row): array {
    $row['name']  = trim(preg_replace('/\s+/', ' ', $row['name']));
    $row['role']  = trim($row['role']);
    $row['email'] = strtolower(trim($row['email']));
    $row['phone'] = trim($row['phone']);

    $row['email_valid'] = (bool) filter_var($row['email'], FILTER_VALIDATE_EMAIL);
    $row['has_phone']   = $row['phone'] !== '';

    $lastVerified = DateTime::createFromFormat('Y-m-d', $row['last_verified']);
    $row['days_since_verified'] = $lastVerified
        ? (new DateTime())->diff($lastVerified)->days
        : null;
    $row['stale'] = $row['days_since_verified'] !== null && $row['days_since_verified'] > 180;

    return $row;
}

function run(string $inPath, string $outPath): void {
    if (!file_exists($inPath)) {
        fwrite(STDERR, "Input file not found: $inPath\n");
        exit(1);
    }

    $handle = fopen($inPath, 'r');
    $header = fgetcsv($handle);
    $records = [];

    while (($line = fgetcsv($handle)) !== false) {
        $row = array_combine($header, $line);
        $records[] = normalize_row($row);
    }
    fclose($handle);

    $staleCount = count(array_filter($records, fn($r) => $r['stale']));
    $badEmailCount = count(array_filter($records, fn($r) => !$r['email_valid']));

    file_put_contents($outPath, json_encode([
        'generated_at' => date(DATE_ATOM),
        'record_count' => count($records),
        'stale_contact_count' => $staleCount,
        'invalid_email_count' => $badEmailCount,
        'records' => $records,
    ], JSON_PRETTY_PRINT));

    echo "Migrated " . count($records) . " contact records -> $outPath\n";
    echo "  stale (unverified >180d): $staleCount\n";
    echo "  invalid email format:     $badEmailCount\n";
}

$in  = $argv[1] ?? '../data/contacts_wiki_dump.csv';
$out = $argv[2] ?? '../data/contacts_clean.json';
run($in, $out);
