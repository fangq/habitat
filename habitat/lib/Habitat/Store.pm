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

# ----------------------------------------------------------------
# Schema bootstrap
# ----------------------------------------------------------------
#
# init_schema($dbh_opt) creates every table and index the wiki needs,
# idempotently. Safe to call on a fresh install (provisions the
# schema) or on an existing one (CREATE IF NOT EXISTS skips the
# work). Used by:
#   - the test harness (in-memory SQLite per test)
#   - utils/migrate.pl    (Stage 4 migration script)
#   - first-run setup     (when $DataDir/<dbfile> doesn't exist yet)
#
# The schema below is the SINGLE source of truth — db/gendb.sql is
# retained as historical documentation but the code path uses this
# function. To extend the schema, change the @ddl list here and the
# test harness picks it up automatically.

sub init_schema {
    my $dbh = $_[0] || _dbh();
    die("init_schema: no \$dbh") if ( !defined($dbh) );

    # SQLite and Postgres accept the same DDL for the column types we
    # use here (varchar(N), integer, text). The only difference is the
    # auto-increment column on `user`, which we just declare as an
    # ordinary INTEGER PRIMARY KEY — the wiki has always picked user
    # ids manually via GetNewUserIdDB, so neither dialect needs a
    # serial/autoincrement.
    my @ddl = (
        q{CREATE TABLE IF NOT EXISTS page (
            id varchar(512), version integer,
            author varchar(32), revision integer, tupdate integer, tcreate integer,
            ip varchar(32), host varchar(64), summary varchar(128), text text,
            minor integer, newauthor integer, data varchar(32), tag varchar(32)
        )},
        q{CREATE INDEX IF NOT EXISTS page_id ON page (id)},
        q{CREATE UNIQUE INDEX IF NOT EXISTS page_id_rev ON page (id, revision)},

        q{CREATE TABLE IF NOT EXISTS deletedpage (
            id varchar(512), version integer,
            author varchar(32), revision integer, tupdate integer, tcreate integer,
            ip varchar(32), host varchar(64), summary varchar(128), text text,
            minor integer, newauthor integer, data varchar(32), tag varchar(32)
        )},

        q{CREATE TABLE IF NOT EXISTS user (
            id integer PRIMARY KEY,
            name varchar(32), pass varchar(255),
            randkey varchar(255), groupid varchar(255), lang varchar(8),
            email varchar(64), param varchar(32), createtime integer,
            stylesheet varchar(128), createip varchar(32), tzoffset integer,
            pagecreate varchar(512), pagemodify varchar(512)
        )},

        q{CREATE TABLE IF NOT EXISTS html (
            id varchar(512) PRIMARY KEY, time integer, text text
        )},

        q{CREATE TABLE IF NOT EXISTS rclog (
            time integer, id varchar(512), summary varchar(128),
            isedit integer, host varchar(64), kind varchar(8),
            userid integer, name varchar(32), revision integer, isadmin integer
        )},
        q{CREATE INDEX IF NOT EXISTS rclog_time ON rclog (time)},
        q{CREATE INDEX IF NOT EXISTS rclog_id   ON rclog (id)},

        q{CREATE TABLE IF NOT EXISTS lock (
            id varchar(512) PRIMARY KEY, tag varchar(32)
        )},

        # The original UseModWiki schema named this column "user", which
        # is a reserved word in Postgres (yields CURRENT_USER unless
        # quoted). Renamed to "username" so the wiki's SQL stays portable
        # without per-call-site quoting. The migration script handles
        # the ALTER TABLE for existing SQLite installs.
        q{CREATE TABLE IF NOT EXISTS watch (
            page varchar(512), username varchar(32)
        )},
        q{CREATE INDEX IF NOT EXISTS watch_page ON watch (page)},

        q{CREATE TABLE IF NOT EXISTS system (
            id varchar(64) PRIMARY KEY, data text, time integer
        )},

        q{CREATE TABLE IF NOT EXISTS pagelog (
            id varchar(512) PRIMARY KEY, lastvisit integer, visit integer,
            x integer, y integer, z integer
        )},

        q{CREATE TABLE IF NOT EXISTS userlog (
            id integer, time integer, ip varchar(32),
            action varchar(8), target varchar(255)
        )},

        # Stage 1 throttle table; previously auto-created lazily.
        q{CREATE TABLE IF NOT EXISTS login_attempts (
            key text PRIMARY KEY,
            count integer NOT NULL,
            first_ts integer NOT NULL,
            last_ts integer NOT NULL
        )},
    );

    for my $stmt (@ddl) {
        eval { $dbh->do($stmt) };
        die("init_schema: $@\n  while executing:\n$stmt\n") if $@;
    }
    return 1;
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
