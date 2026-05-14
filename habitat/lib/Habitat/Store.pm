package Habitat::Store;
#
# Generic SQL helpers used by the rest of Habitat. Every cross-table
# read/write/delete in the wiki should eventually flow through one of
# these — direct $dbh->prepare/do/selectall_arrayref calls scattered
# elsewhere in index.cgi are legacy and slated for migration through
# this module in Stage 4 (schema cleanup + Postgres dialect support).
#
# Database handle plumbing
# ------------------------
# The handle lives in $HabitatEngine::dbh (the main script's package).
# We don't keep our own copy here — that way reconnects (PSGI
# ping-and-reconnect in InitWikiEnv) are picked up automatically with
# no extra wiring. The _dbh() accessor is the single point of coupling
# and is the obvious thing to revisit if Store later grows into a
# proper standalone module.
#
# All write/delete/copy helpers commit eagerly; callers don't need to
# wrap individual operations. Bind values are accepted as trailing
# args and passed straight to DBI's prepare/execute pair, so SQL
# strings stay free of user input.

use strict;
use warnings;
use Exporter qw(import);

our @EXPORT_OK = qw(
    SafeIdent
    ReadDBItems
    WriteDBItems
    DeleteDBItems
    CopyDBItems
    dialect
    regex_op
    init_schema
);

sub _dbh {
    no warnings 'once';    # $HabitatEngine::dbh is declared via use vars in index.cgi
    return $HabitatEngine::dbh;
}

# Commit only if the handle is in manual-transaction mode. Calling
# commit() under AutoCommit=1 emits a "commit ineffective" warning
# without changing behavior. SQLite defaults to AutoCommit=1; tests
# and production typically don't open an explicit transaction here.
sub _commit_if_needed {
    my ($dbh) = @_;
    return if ( !defined($dbh) || $dbh->{AutoCommit} );
    $dbh->commit;
}

# ----------------------------------------------------------------
# Dialect detection
# ----------------------------------------------------------------
#
# Two supported drivers: SQLite (the historical default) and Pg.
# dialect() returns 'sqlite' or 'pg'; everything dialect-specific
# branches off this single inspection.
#
# Callers in index.cgi that need a dialect-aware piece of SQL pull
# it from one of these helpers rather than embedding the SQL inline.
# The point is to keep the dialect surface small and centralized so
# adding a third driver (or fixing a portability bug) only touches
# Store.pm.

sub dialect {
    my $dbh = $_[0] || _dbh();
    return 'sqlite' if ( !defined($dbh) );
    my $name = eval { $dbh->{Driver}{Name} } || '';
    return 'pg' if ( $name eq 'Pg' );
    return 'sqlite';
}

# Regex match operator. SQLite has no built-in; the wiki registers a
# custom REGEXP UDF at connect time (see InitWikiEnv). Postgres uses
# the `~` infix operator.
sub regex_op {
    return ( dialect() eq 'pg' ) ? '~' : 'REGEXP';
}

# Build an UPSERT statement for the given table and field list.
#   $fields: comma-separated column list ("id,data,time").
#   $keys  : conflict-key list (defaults to the FIRST column of $fields,
#            which matches the wiki's convention for all REPLACE INTO
#            call sites).
# SQLite path uses REPLACE INTO (delete + insert, available since 3.0).
# Postgres path uses INSERT ... ON CONFLICT ... DO UPDATE SET col=EXCLUDED.col
# for each non-key column.
sub _build_upsert_sql {
    my ( $dbh, $table, $fields, $keys ) = @_;
    my @cols = split /\s*,\s*/, $fields;
    my $placeholders = join ',', ('?') x scalar(@cols);

    if ( dialect($dbh) eq 'pg' ) {
        my @keylist = split /\s*,\s*/, ( defined($keys) && $keys ne '' ? $keys : $cols[0] );
        my %is_key = map { $_ => 1 } @keylist;
        my @updates = map { "$_ = EXCLUDED.$_" } grep { !$is_key{$_} } @cols;
        my $set_clause = @updates ? "DO UPDATE SET " . join( ',', @updates ) : "DO NOTHING";
        return
            "INSERT INTO $table ($fields) VALUES ($placeholders) "
          . "ON CONFLICT ("
          . join( ',', @keylist )
          . ") $set_clause";
    }
    return "REPLACE INTO $table ($fields) VALUES ($placeholders)";
}

# Identifier whitelist for any value we have to interpolate directly
# into SQL (table names, column names) — DBI placeholders can't bind
# identifiers. Anything outside [A-Za-z_][A-Za-z0-9_]* is rejected.
sub SafeIdent {
    my ($name) = @_;
    return ( defined($name) && $name =~ /\A[A-Za-z_][A-Za-z0-9_]*\z/ );
}

# WriteDBItems($table, "col1,col2,...", $doreplace, @values)
#   - $fields: comma-separated identifier list; each part validated.
#   - $doreplace: 1 for upsert (REPLACE INTO or ON CONFLICT DO UPDATE),
#                 0 for plain INSERT.
#   - @values: one bound parameter per column listed in $fields.
# The dialect-specific upsert SQL is built by _build_upsert_sql so this
# function stays driver-agnostic.
sub WriteDBItems {
    my ( $dbname, $fields, $doreplace, @vals ) = @_;
    my $dbh = _dbh();
    die("ERROR: database uninitialized!") if ( !defined($dbh) || $dbh eq "" || $dbname eq "" );
    die("WriteDBItems: unsafe table name '$dbname'") if ( !SafeIdent($dbname) );
    $fields = "*" if ( $fields eq "" );
    foreach my $f ( split( /\s*,\s*/, $fields ) ) {
        die("WriteDBItems: unsafe field name '$f'") if ( $f ne '*' && !SafeIdent($f) );
    }
    my $sql;
    if ($doreplace) {
        $sql = _build_upsert_sql( $dbh, $dbname, $fields );
    } else {
        my $holder = $fields;
        $holder =~ s/[0-9a-zA-Z_]+/?/g;
        $sql = "INSERT INTO $dbname ($fields) VALUES ($holder)";
    }
    my $sth = $dbh->prepare($sql)
      or die "Can't prepare: " . $dbh->errstr;
    $sth->execute(@vals) or die "Can't execute: " . $dbh->errstr;
}

# CopyDBItems($from_table, $to_table, $where_clause, @binds)
#   Emits `insert into $to select * from $from where $where`.
#   Empty $where is a no-op (refuses to copy the whole table).
#
# The previous `REPLACE INTO ... SELECT *` form was SQLite-specific
# AND a no-op for "merge"-style semantics because the wiki's archival
# tables (deletedpage, deleted$pagedb) carry no UNIQUE constraint.
# Plain INSERT works identically on both dialects.
sub CopyDBItems {
    my ( $db1, $db2, $conditions, @binds ) = @_;
    my $dbh = _dbh();
    die("ERROR: database uninitialized!")
      if ( !defined($dbh) || $dbh eq "" || $db1 eq "" || $db2 eq "" );
    die("CopyDBItems: unsafe table name") if ( !SafeIdent($db1) || !SafeIdent($db2) );
    return 0 if ( $conditions eq "" );
    my $sth = $dbh->prepare("INSERT INTO $db2 SELECT * FROM $db1 WHERE $conditions");
    $sth->execute(@binds) or die "Can't execute: " . $dbh->errstr;
    _commit_if_needed($dbh);
    return defined($sth) ? $sth : 0;
}

# DeleteDBItems($table, $where_clause, @binds)
#   Empty $where is intentionally a no-op (refuses to wipe a table).
sub DeleteDBItems {
    my ( $dbname, $conditions, @binds ) = @_;
    my $dbh = _dbh();
    die("ERROR: database uninitialized!")
      if ( !defined($dbh) || $dbh eq "" || $dbname eq "" );
    die("DeleteDBItems: unsafe table name '$dbname'") if ( !SafeIdent($dbname) );
    return 0 if ( $conditions eq "" );
    my $sth = $dbh->prepare("delete from $dbname where $conditions;");
    $sth->execute(@binds) or die "Can't execute: " . $dbh->errstr;
    _commit_if_needed($dbh);
    return defined($sth) ? $sth : 0;
}

# ReadDBItems($table, $fields, $row_glue, $col_glue, $where_clause, @binds)
#   Returns rows joined by $row_glue, columns within a row joined by
#   $col_glue. Designed to fit the wiki's existing usage where callers
#   immediately split the result back into rows/cols.
sub ReadDBItems {
    my ( $dbname, $fields, $glue1, $glue2, $conditions, @binds ) = @_;
    my $dbh = _dbh();
    die("ERROR: database uninitialized!")
      if ( !defined($dbh) || $dbh eq "" || $dbname eq "" );
    die("ReadDBItems: unsafe table name '$dbname'") if ( !SafeIdent($dbname) );
    $fields = "*" if ( $fields eq "" );
    my $sql = "select $fields from $dbname";
    $sql .= " where $conditions" if ( $conditions ne "" );
    my $sth = $dbh->selectall_arrayref( $sql, undef, @binds );
    my @res;
    if ( defined $sth && defined $sth->[0] ) {
        foreach my $rec (@$sth) {
            push( @res, join( $glue2, @{$rec} ) ) if ( @{$rec} > 0 );
        }
    }
    return join( $glue1, @res );
}

1;
