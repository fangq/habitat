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

# Identifier whitelist for any value we have to interpolate directly
# into SQL (table names, column names) — DBI placeholders can't bind
# identifiers. Anything outside [A-Za-z_][A-Za-z0-9_]* is rejected.
sub SafeIdent {
    my ($name) = @_;
    return ( defined($name) && $name =~ /\A[A-Za-z_][A-Za-z0-9_]*\z/ );
}

# WriteDBItems($table, "col1,col2,...", $doreplace, @values)
#   - $fields: comma-separated identifier list; each part validated.
#   - $doreplace: 1 for REPLACE, 0 for INSERT.
#   - @values: one bound parameter per column listed in $fields.
sub WriteDBItems {
    my ( $dbname, $fields, $doreplace, @vals ) = @_;
    my $dbh = _dbh();
    die("ERROR: database uninitialized!") if ( !defined($dbh) || $dbh eq "" || $dbname eq "" );
    die("WriteDBItems: unsafe table name '$dbname'") if ( !SafeIdent($dbname) );
    $fields = "*" if ( $fields eq "" );
    foreach my $f ( split( /\s*,\s*/, $fields ) ) {
        die("WriteDBItems: unsafe field name '$f'") if ( $f ne '*' && !SafeIdent($f) );
    }
    my $action = $doreplace ? "replace" : "insert";
    my $holder = $fields;
    $holder =~ s/[0-9a-zA-Z_]+/?/g;
    my $sth = $dbh->prepare("$action into $dbname ($fields) values ($holder);")
      or die "Can't prepare: " . $dbh->errstr;
    $sth->execute(@vals) or die "Can't execute: " . $dbh->errstr;
}

# CopyDBItems($from_table, $to_table, $where_clause, @binds)
#   Emits `replace into $to select * from $from where $where`.
#   Empty $where is a no-op (refuses to copy the whole table).
sub CopyDBItems {
    my ( $db1, $db2, $conditions, @binds ) = @_;
    my $dbh = _dbh();
    die("ERROR: database uninitialized!")
      if ( !defined($dbh) || $dbh eq "" || $db1 eq "" || $db2 eq "" );
    die("CopyDBItems: unsafe table name") if ( !SafeIdent($db1) || !SafeIdent($db2) );
    return 0 if ( $conditions eq "" );
    my $sth = $dbh->prepare("replace into $db2 select * from $db1 where $conditions;");
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
