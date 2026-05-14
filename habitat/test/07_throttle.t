#!/usr/bin/env perl
# Stage 1 per-(username | IP) login throttle. Counters live in the
# auto-created login_attempts table; reset on successful login.

use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
HabitatHarness::fresh_test_db();
HabitatHarness::freeze_time(1_700_000_000);

# Use a low limit so the test stays compact; restore after each scope.
no warnings 'once';
local $HabitatEngine::LoginMaxAttempts    = 3;
local $HabitatEngine::LoginThrottleWindow = 60;

# ----------------------------------------------------------------
# Table is created lazily on first use
# ----------------------------------------------------------------
my $dbh = $HabitatEngine::dbh;
$dbh->do("DROP TABLE IF EXISTS login_attempts");
HabitatEngine::EnsureLoginThrottleTable();
my ($tbl) = $dbh->selectrow_array(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='login_attempts'");
is( $tbl, "login_attempts", "EnsureLoginThrottleTable creates the table on demand" );

# Idempotent
HabitatEngine::EnsureLoginThrottleTable();
HabitatEngine::EnsureLoginThrottleTable();
($tbl) = $dbh->selectrow_array(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='login_attempts'");
is( $tbl, "login_attempts", "calling EnsureLoginThrottleTable repeatedly is safe" );

# ----------------------------------------------------------------
# Hit + Blocked progression
# ----------------------------------------------------------------
$dbh->do("DELETE FROM login_attempts");

my $k = 'ip:127.0.0.1';
is( HabitatEngine::LoginThrottleBlocked($k), 0, "starts unblocked" );

HabitatEngine::LoginThrottleHit($k);
is( HabitatEngine::LoginThrottleBlocked($k), 0, "1 hit < limit" );

HabitatEngine::LoginThrottleHit($k);
is( HabitatEngine::LoginThrottleBlocked($k), 0, "2 hits < limit" );

HabitatEngine::LoginThrottleHit($k);
is( HabitatEngine::LoginThrottleBlocked($k), 1, "3 hits at limit -> blocked" );

HabitatEngine::LoginThrottleHit($k);
is( HabitatEngine::LoginThrottleBlocked($k), 1, "overshoot stays blocked" );

# Independent keys do not interfere
my $k2 = 'ip:10.0.0.1';
is( HabitatEngine::LoginThrottleBlocked($k2), 0, "different IP unaffected by another's failures" );

# ----------------------------------------------------------------
# Clear resets the counter
# ----------------------------------------------------------------
HabitatEngine::LoginThrottleClear($k);
is( HabitatEngine::LoginThrottleBlocked($k), 0, "successful login clears the throttle window" );

HabitatEngine::LoginThrottleHit($k);
is( HabitatEngine::LoginThrottleBlocked($k), 0, "first failure after clear is counted from zero" );

# ----------------------------------------------------------------
# Window expiry: hits older than $LoginThrottleWindow get a fresh start
# ----------------------------------------------------------------
$dbh->do("DELETE FROM login_attempts");
HabitatEngine::LoginThrottleHit($k);
HabitatEngine::LoginThrottleHit($k);
HabitatEngine::LoginThrottleHit($k);
is( HabitatEngine::LoginThrottleBlocked($k), 1, "blocked after 3 failures in window" );

# Advance clock past the window
HabitatHarness::freeze_time( 1_700_000_000 + 61 );
is( HabitatEngine::LoginThrottleBlocked($k), 0, "block lifts after the window has elapsed" );

# A fresh hit after window expiry restarts the count, doesn't add to old
HabitatEngine::LoginThrottleHit($k);
is( HabitatEngine::LoginThrottleBlocked($k),
    0, "new hit after window starts fresh count, not at 4" );

# ----------------------------------------------------------------
# Empty / undef inputs are no-ops (safety guards)
# ----------------------------------------------------------------
my $rows_before = $dbh->selectrow_array("SELECT COUNT(*) FROM login_attempts");
HabitatEngine::LoginThrottleHit("");
HabitatEngine::LoginThrottleHit(undef);
HabitatEngine::LoginThrottleClear("");
HabitatEngine::LoginThrottleClear(undef);
my $rows_after = $dbh->selectrow_array("SELECT COUNT(*) FROM login_attempts");
is( $rows_before, $rows_after, "empty/undef keys are no-ops" );

is( HabitatEngine::LoginThrottleBlocked(""),    0, "empty key not blocked" );
is( HabitatEngine::LoginThrottleBlocked(undef), 0, "undef key not blocked" );

done_testing;
