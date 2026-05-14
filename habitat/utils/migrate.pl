#!/usr/bin/env perl
#
# Habitat data migration tool.
#
# Copies every wiki table from --source to --dest, applying the
# current schema (via Habitat::Store::init_schema) to the destination
# first. Source and destination can be any combination of SQLite and
# Postgres; the DBI URL string determines the driver.
#
# Typical uses:
#
#   # in-place SQLite cleanup (rebuild new db file from old):
#   perl utils/migrate.pl \
#       --source 'dbi:SQLite:dbname=old/habitatdb.db' \
#       --dest   'dbi:SQLite:dbname=new/habitatdb.db'
#
#   # migrate SQLite -> Postgres:
#   perl utils/migrate.pl \
#       --source 'dbi:SQLite:dbname=db/habitatdb.db' \
#       --dest   'dbi:Pg:dbname=habitat;host=localhost' \
#       --dest-user habitat
#
# The script does NOT modify the source DB. To verify before
# committing to it, run with --dry-run; rows are still read but the
# destination is opened read-only.

use strict;
use warnings;
use FindBin qw($Bin);
use lib "$Bin/../lib";
use Getopt::Long;
use DBI;
use Habitat::Store ();

my (
    $source_dsn, $source_user, $source_pass,
    $dest_dsn,   $dest_user,   $dest_pass,
    $dry_run,    $batch_size,  $verbose, $help,
);
$batch_size = 500;
$dest_user  = '';
$dest_pass  = '';
$source_user = '';
$source_pass = '';

GetOptions(
    "source=s"      => \$source_dsn,
    "source-user=s" => \$source_user,
    "source-pass=s" => \$source_pass,
    "dest=s"        => \$dest_dsn,
    "dest-user=s"   => \$dest_user,
    "dest-pass=s"   => \$dest_pass,
    "dry-run"       => \$dry_run,
    "batch=i"       => \$batch_size,
    "verbose|v"     => \$verbose,
    "help|h"        => \$help,
) or usage(2);

usage(0) if $help;
usage(2) if ( !$source_dsn || !$dest_dsn );

sub usage {
    my ($exit) = @_;
    print STDERR <<"USAGE";
usage: $0 --source DSN --dest DSN [opts]
options:
  --source DSN        DBI connect string for the source DB
  --source-user U     source DB user (default empty)
  --source-pass P     source DB password (default empty)
  --dest DSN          DBI connect string for the destination DB
  --dest-user U       destination DB user (default empty)
  --dest-pass P       destination DB password (default empty)
  --dry-run           open dest read-only; report intended actions only
  --batch N           rows per INSERT batch (default $batch_size)
  --verbose | -v      print every table's per-row count
DSN examples:
  dbi:SQLite:dbname=/path/to/habitatdb.db
  dbi:Pg:dbname=habitat;host=localhost;port=5432
USAGE
    exit $exit;
}

# Tables migrated, in safe-load order. login_attempts is optional
# (Stage 1 addition; may be absent on older snapshots).
# Each entry is { source => 'src_name', dest => 'dst_name' }; for tables
# whose name is unchanged the two are equal.
my @TABLES = (
    # The legacy "user" table is reserved in Postgres; we now call it
    # "users". migrate.pl picks up "user" from the source and writes
    # to "users" in the destination.
    { source => 'user',           dest => 'users' },
    { source => 'page',           dest => 'page' },
    { source => 'deletedpage',    dest => 'deletedpage' },
    { source => 'html',           dest => 'html' },
    { source => 'rclog',          dest => 'rclog' },
    { source => 'lock',           dest => 'lock' },
    { source => 'watch',          dest => 'watch' },
    { source => 'system',         dest => 'system' },
    { source => 'pagelog',        dest => 'pagelog' },
    { source => 'userlog',        dest => 'userlog' },
    { source => 'login_attempts', dest => 'login_attempts' },
);

# Also accept new-style sources that already have the renamed tables.
# Walk both source candidates per logical table.
my %ALIAS_SOURCES = (
    'users' => [ 'users', 'user' ],
);

# Per-table column-name remaps from the legacy schema to the current
# one. Keyed by DESTINATION table name. Map { src_col => dst_col };
# undef value would drop a column.
my %COLUMN_RENAME = (
    watch => { user => 'username' },
);

sub log_msg { print STDERR "[migrate] @_\n" }

# ----------------------------------------------------------------
# Open both connections
# ----------------------------------------------------------------
log_msg "source: $source_dsn";
log_msg "dest  : $dest_dsn" . ( $dry_run ? "  (dry-run)" : "" );

my $src = DBI->connect(
    $source_dsn, $source_user, $source_pass,
    { RaiseError => 1, AutoCommit => 1, PrintError => 0 }
) or die "source connect failed: $DBI::errstr\n";

my $dst = DBI->connect(
    $dest_dsn, $dest_user, $dest_pass,
    { RaiseError => 1, AutoCommit => 0, PrintError => 0 }
) or die "dest connect failed: $DBI::errstr\n";

# ----------------------------------------------------------------
# Provision the destination schema
# ----------------------------------------------------------------
unless ($dry_run) {
    log_msg "applying schema to destination via Habitat::Store::init_schema";
    Habitat::Store::init_schema($dst);
    $dst->commit;
}

# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

# DBD-portable column-list extraction. Uses prepare+statement_handle
# rather than catalog tables so it works on both SQLite and Pg without
# special-casing.
sub get_columns {
    my ( $dbh, $table ) = @_;
    my $sth = eval { $dbh->prepare("SELECT * FROM $table WHERE 1=0") } or return ();
    eval { $sth->execute };
    return () if $@;
    my $names = $sth->{NAME_lc} || [];
    $sth->finish;
    return @$names;
}

sub table_exists {
    my ( $dbh, $table ) = @_;
    my @cols = get_columns( $dbh, $table );
    return @cols ? 1 : 0;
}

sub row_count {
    my ( $dbh, $table ) = @_;
    my ($n) = $dbh->selectrow_array("SELECT COUNT(*) FROM $table");
    return defined($n) ? $n : 0;
}

# ----------------------------------------------------------------
# Per-table copy
# ----------------------------------------------------------------
my %report;

for my $tbl_spec (@TABLES) {
    my $src_table = $tbl_spec->{source};
    my $dst_table = $tbl_spec->{dest};

    # Source may carry either the legacy or the new table name (e.g.
    # "user" or "users"). Prefer the one that exists.
    if ( my $aliases = $ALIAS_SOURCES{$dst_table} ) {
        my $found;
        for my $cand (@$aliases) {
            if ( table_exists( $src, $cand ) ) { $found = $cand; last; }
        }
        $src_table = $found if defined $found;
    }

    my $label = $src_table eq $dst_table ? $dst_table : "$src_table -> $dst_table";

    if ( !table_exists( $src, $src_table ) ) {
        log_msg "skip $label (not present in source)";
        next;
    }
    if ( !table_exists( $dst, $dst_table ) ) {
        log_msg "skip $label (not present in destination — schema mismatch?)";
        next;
    }

    my @src_cols = get_columns( $src, $src_table );
    my @dst_cols = get_columns( $dst, $dst_table );
    my %dst_set  = map { $_ => 1 } @dst_cols;

    # For each source column, decide where its value should go in dest.
    # Apply per-(dest-table) column renames first.
    my $rename = $COLUMN_RENAME{$dst_table} || {};
    my ( @src_keep, @dst_keep );
    for my $col (@src_cols) {
        my $dest_col = exists $rename->{$col} ? $rename->{$col} : $col;
        next unless defined $dest_col;        # explicit drop
        next unless $dst_set{$dest_col};       # column doesn't exist in dest
        push @src_keep, $col;
        push @dst_keep, $dest_col;
    }
    if ( !@src_keep ) {
        log_msg "skip $label (no overlapping columns after renames)";
        next;
    }

    my $src_count = row_count( $src, $src_table );
    log_msg sprintf( "copy %s : %d rows, columns: %s",
        $label, $src_count,
        join( ",", map { $src_keep[$_] . ($src_keep[$_] eq $dst_keep[$_] ? "" : "->$dst_keep[$_]") } 0 .. $#src_keep ) );

    next if ( $src_count == 0 );

    my $src_col_list = join( ",", @src_keep );
    my $dst_col_list = join( ",", @dst_keep );
    my $placeholders = join( ",", ("?") x scalar(@src_keep) );

    my $select = $src->prepare("SELECT $src_col_list FROM $src_table");
    my $insert;
    unless ($dry_run) {
        $insert = $dst->prepare("INSERT INTO $dst_table ($dst_col_list) VALUES ($placeholders)");
    }
    $select->execute;

    my $batched = 0;
    my $total   = 0;
    while ( my $row = $select->fetchrow_arrayref ) {
        if ( !$dry_run ) {
            $insert->execute(@$row);
        }
        $total++;
        $batched++;
        if ( $batched >= $batch_size ) {
            $dst->commit unless $dry_run;
            log_msg "  $label: ${total}/${src_count}..." if $verbose;
            $batched = 0;
        }
    }
    $dst->commit unless $dry_run;

    my $dst_count = $dry_run ? '(dry-run)' : row_count( $dst, $dst_table );
    $report{$label} = { src => $src_count, dst => $dst_count };
    log_msg sprintf( "done %s : src=%d dst=%s", $label, $src_count, $dst_count );
}

# ----------------------------------------------------------------
# Summary
# ----------------------------------------------------------------
print "\n--- migration summary ---\n";
printf "%-30s %-12s %-12s\n", "table", "source", "dest";
for my $label ( sort keys %report ) {
    printf "%-30s %-12s %-12s\n",
        $label, $report{$label}{src}, $report{$label}{dst};
}

$src->disconnect;
$dst->disconnect unless $dry_run;
exit 0;
