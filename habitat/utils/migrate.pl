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
    $source_dsn, $source_user, $source_pass, $dest_dsn, $dest_user,
    $dest_pass,  $dry_run,     $batch_size,  $verbose,  $help,
);
$batch_size  = 500;
$dest_user   = '';
$dest_pass   = '';
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
#
# `handler` is an optional code-ref override for tables that need
# more than a column-by-column copy. The `page` table is a notable
# example: the legacy schema had one row per (id, revision); the new
# schema has one row per id in `page` plus historical rows in
# `page_revisions`. See migrate_page() below.
my @TABLES = (
    { source => 'user',           dest => 'users' },
    { source => 'page',           dest => 'page', handler => \&migrate_page },
    { source => 'deletedpage',    dest => 'deletedpage' },
    { source => 'html',           dest => 'html' },
    { source => 'rclog',          dest => 'rclog' },
    { source => 'lock',           dest => 'pagelock' },         # MariaDB reserved word rename
    { source => 'watch',          dest => 'watch' },
    { source => 'system',         dest => 'system' },
    { source => 'pagelog',        dest => 'pagelog' },
    { source => 'userlog',        dest => 'userlog' },
    { source => 'login_attempts', dest => 'login_attempts' },
);

# Also accept new-style sources that already have the renamed tables.
# Walk both source candidates per logical table.
my %ALIAS_SOURCES = (
    'users'    => [ 'users',    'user' ],
    'pagelock' => [ 'pagelock', 'lock' ],
);

# Per-table column-name remaps from the legacy schema to the current
# one. Keyed by DESTINATION table name. Map { src_col => dst_col };
# undef value would drop a column.
my %COLUMN_RENAME = (
    watch => { user => 'username' },

    # Stage 5: prefs blob renamed from `stylesheet`. The TRANSFORMS
    # map (below) handles the FS-joined -> JSON conversion of the
    # value itself.
    users => { stylesheet => 'prefs' },

    # MariaDB-portability rename: `key` and `count` are reserved
    # words on MariaDB/MySQL. Old SQLite/Pg installs of the Stage 1
    # login throttle used the reserved names; the new schema uses
    # attempt_key / attempts so the same SQL works unquoted across
    # all three dialects.
    login_attempts => { key => 'attempt_key', count => 'attempts' },
);

# Per-table per-column value transforms applied during row copy.
# Keyed by DESTINATION table name, then DESTINATION column name.
# The function receives the source value and returns the value to
# insert into the destination.
use JSON::PP;
my %COLUMN_TRANSFORM = (
    users => {
        prefs => sub {
            my ($val) = @_;
            return undef if ( !defined($val) || $val eq '' );

            # Already JSON? Pass through.
            return $val if ( $val =~ /^\s*[\{\[]/ );

            # Legacy $FS2-joined hash (\x1e2 == "\x1e" . "2")
            my $FS2 = "\x1e2";
            my %h   = split( /$FS2/, $val );
            return encode_json( \%h );
        },
    },
);

sub log_msg { print STDERR "[migrate] @_\n" }

# ----------------------------------------------------------------
# Open both connections
# ----------------------------------------------------------------
log_msg "source: $source_dsn";
log_msg "dest  : $dest_dsn" . ( $dry_run ? "  (dry-run)" : "" );

my $src =
  DBI->connect( $source_dsn, $source_user, $source_pass,
    { RaiseError => 1, AutoCommit => 1, PrintError => 0 } )
  or die "source connect failed: $DBI::errstr\n";

my $dst =
  DBI->connect( $dest_dsn, $dest_user, $dest_pass,
    { RaiseError => 1, AutoCommit => 0, PrintError => 0 } )
  or die "dest connect failed: $DBI::errstr\n";

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

# Stage 5 page-table migration. Legacy schema: one row per
# (id, revision) in `page`, possibly with FS4-chained inline diffs in
# the text column representing minor revisions. New schema: one row
# per id in `page` (current snapshot) plus one row per historical
# revision in `page_revisions`.
#
# Per page id:
#   1. Read every row from the source `page` table for that id.
#   2. For the row with the highest revision number, parse out its
#      inline-diff chain (if any) and reconstruct each minor revision
#      as a full-text snapshot.
#   3. Insert the latest reconstructed snapshot into the new `page`
#      table.
#   4. Insert every other reconstructed snapshot, plus every other
#      legacy major-revision row, into `page_revisions` (kind='snapshot').
#
# We don't compute reverse diffs here — Stage 5 ships snapshot
# storage; a future commit can re-encode for compactness.
sub migrate_page {
    my ( $src, $dst, $src_table, $dst_table, $label, $dry_run, $verbose, $report ) = @_;

    # Need PatchText / Text::Patch::patch to walk inline diffs.
    require Text::Patch;

    # FS chars are package globals in the wiki; replicate them here
    # so the migration tool is self-contained.
    my $FS  = "\x1e";
    my $FS4 = $FS . "4";
    my $FS5 = $FS . "5";

    my $rev_table = "${dst_table}_revisions";
    unless ( table_exists( $dst, $rev_table ) ) {
        log_msg "skip $label (destination missing $rev_table — schema mismatch?)";
        return;
    }

    my $src_count = row_count( $src, $src_table );
    log_msg sprintf( "copy %s : %d rows from legacy multi-row schema", $label, $src_count );
    return if ( $src_count == 0 );

    # Group all source rows by id.
    my $sth =
      $src->prepare( "SELECT id, version, author, revision, tupdate, tcreate, ip, host, "
          . "summary, text, minor, newauthor, data, tag "
          . "FROM $src_table ORDER BY id, revision" );
    $sth->execute;

    my %by_id;    # id => arrayref of row hashrefs
    while ( my $r = $sth->fetchrow_arrayref ) {
        my $row = {
            id        => $r->[0],
            version   => $r->[1],
            author    => $r->[2],
            revision  => $r->[3],
            tupdate   => $r->[4],
            tcreate   => $r->[5],
            ip        => $r->[6],
            host      => $r->[7],
            summary   => $r->[8],
            text      => $r->[9],
            minor     => $r->[10],
            newauthor => $r->[11],
            data      => $r->[12],
            tag       => $r->[13],
        };
        push @{ $by_id{ $row->{id} } }, $row;
    }

    # `admin_saved` defaults to 0 for migrated content: the legacy
    # schema has no concept of admin-saved trust, so re-saving a page
    # post-migration is what grants the raw-HTML bypass.
    my $page_ins =
      $dst->prepare( "INSERT INTO $dst_table "
          . "(id, version, author, revision, tupdate, tcreate, ip, host, "
          . " summary, text, minor, newauthor, data, tag, admin_saved) "
          . "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)" );
    my $rev_ins =
      $dst->prepare( "INSERT INTO $rev_table "
          . "(page_id, revision, version, author, tupdate, tcreate, ip, host, "
          . " summary, minor, newauthor, data, kind, text) "
          . "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)" );

    my $total_pages = 0;
    my $total_revs  = 0;
    for my $id ( sort keys %by_id ) {
        my @rows = @{ $by_id{$id} };

        # Reconstruct all revisions for this page. Each legacy row
        # represents the current text at its `revision` value plus
        # optionally an inline FS4-chain of MINOR revisions BELOW
        # that one (since the wiki's "minor edit" path appended
        # diffs to the current row's text).
        my @history;    # ascending list of { revision, text, meta... }
        for my $row (@rows) {
            my @patches = split( /$FS4/, $row->{text} );
            my $base    = $patches[0];                     # snapshot for this row's revision

            # First, push the row's snapshot itself.
            push @history,
              {
                revision  => $row->{revision},
                version   => $row->{version},
                author    => $row->{author},
                tupdate   => $row->{tupdate},
                tcreate   => $row->{tcreate},
                ip        => $row->{ip},
                host      => $row->{host},
                summary   => $row->{summary},
                minor     => $row->{minor},
                newauthor => $row->{newauthor},
                data      => $row->{data},
                tag       => $row->{tag},
                text      => $base,
              };

            # Each subsequent patch reconstructs an EARLIER minor
            # revision (apply, get progressively older text). The
            # legacy format encodes "ts|user|host|summary\x1e5diff";
            # take everything after \x1e5 as the patch payload.
            my $cur_text = $base;
            for ( my $i = 1 ; $i < @patches ; $i++ ) {
                my $part = $patches[$i];
                next if ( $part =~ /$FS5$/ );    # empty diff
                my @half = split( /$FS5/, $part );
                my $diff = $half[-1];
                next if ( $diff eq '' );
                $cur_text = eval { Text::Patch::patch( $cur_text, $diff, STYLE => "Unified" ) };
                last if $@;                      # malformed chain; stop
                push @history,
                  {
                    revision  => $row->{revision} - $i,
                    version   => $row->{version},
                    author    => $row->{author},
                    tupdate   => $row->{tupdate},
                    tcreate   => $row->{tcreate},
                    ip        => $row->{ip},
                    host      => $row->{host},
                    summary   => $row->{summary},
                    minor     => 1,
                    newauthor => 0,
                    data      => $row->{data},
                    tag       => $row->{tag},
                    text      => $cur_text,
                  };
            }
        }

        # Sort by revision ascending, dedupe (legacy rows can have
        # both a major-rev row and an inline-derived row at the same
        # revision number; prefer the major-rev row, which is the
        # snapshot, and which we pushed first).
        my %seen;
        @history =
          grep { !$seen{ $_->{revision} }++ } sort { $a->{revision} <=> $b->{revision} } @history;

        next unless @history;
        my $latest = $history[-1];

        # 1. Write the latest revision to the new `page` table.
        unless ($dry_run) {
            $page_ins->execute(
                $id,                 $latest->{version}, $latest->{author},
                $latest->{revision}, $latest->{tupdate}, $latest->{tcreate},
                $latest->{ip},       $latest->{host},    $latest->{summary},
                $latest->{text},     $latest->{minor},   $latest->{newauthor},
                $latest->{data},     $latest->{tag},
            );
        }
        $total_pages++;

        # 2. Write all earlier revisions to `page_revisions`.
        for my $i ( 0 .. $#history - 1 ) {
            my $h = $history[$i];
            unless ($dry_run) {
                $rev_ins->execute(
                    $id,           $h->{revision}, $h->{version},   $h->{author},
                    $h->{tupdate}, $h->{tcreate},  $h->{ip},        $h->{host},
                    $h->{summary}, $h->{minor},    $h->{newauthor}, $h->{data},
                    'snapshot',    $h->{text},
                );
            }
            $total_revs++;
        }

        log_msg sprintf( "  %s: %d revisions (1 current + %d historical)",
            $id, scalar(@history), scalar(@history) - 1 )
          if $verbose;
    }
    $dst->commit unless $dry_run;

    my $dst_count = $dry_run ? '(dry-run)' : row_count( $dst, $dst_table );
    my $rev_count = $dry_run ? '(dry-run)' : row_count( $dst, $rev_table );
    $report->{$label} = { src => $src_count, dst => "$dst_count page + $rev_count rev" };
    log_msg sprintf( "done %s : src=%d -> %d current rows + %d historical rows",
        $label, $src_count, $total_pages, $total_revs );
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

    # Custom handler? It owns the entire copy logic for this table
    # (including any row counts / reporting it wants in $report).
    if ( my $handler = $tbl_spec->{handler} ) {
        $handler->( $src, $dst, $src_table, $dst_table, $label, $dry_run, $verbose, \%report );
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
        next unless defined $dest_col;      # explicit drop
        next unless $dst_set{$dest_col};    # column doesn't exist in dest
        push @src_keep, $col;
        push @dst_keep, $dest_col;
    }
    if ( !@src_keep ) {
        log_msg "skip $label (no overlapping columns after renames)";
        next;
    }

    my $src_count = row_count( $src, $src_table );
    log_msg sprintf(
        "copy %s : %d rows, columns: %s",
        $label,
        $src_count,
        join( ",",
            map { $src_keep[$_] . ( $src_keep[$_] eq $dst_keep[$_] ? "" : "->$dst_keep[$_]" ) }
              0 .. $#src_keep )
    );

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

    # Pre-compute the transform list, indexed by row position. Most
    # tables have no transforms so this is undef -> array-of-undefs.
    my $xforms        = $COLUMN_TRANSFORM{$dst_table};
    my @xform_fns     = map  { $xforms && $xforms->{$_} } @dst_keep;
    my $has_any_xform = grep { $_ } @xform_fns;

    my $batched = 0;
    my $total   = 0;
    while ( my $row = $select->fetchrow_arrayref ) {
        my @vals = @$row;
        if ($has_any_xform) {
            for my $i ( 0 .. $#vals ) {
                $vals[$i] = $xform_fns[$i]->( $vals[$i] ) if $xform_fns[$i];
            }
        }
        if ( !$dry_run ) {
            $insert->execute(@vals);
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
    printf "%-30s %-12s %-12s\n", $label, $report{$label}{src}, $report{$label}{dst};
}

$src->disconnect;
$dst->disconnect unless $dry_run;
exit 0;
