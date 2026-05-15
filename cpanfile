# Habitat CPAN dependencies.
#
# Used by:
#   - .github/workflows/test.yml  (CI installs via `cpanm --installdeps .`)
#   - human installers            (`cpanm --installdeps .` from this dir,
#                                  or `cpanm <module>` per the list below)
#
# The wiki itself (index.cgi) and the PSGI shim share one dep set; tests
# add a few more for harness/HTTP plumbing. Optional modules are gated
# at runtime — the wiki and the test suite both skip cleanly without
# them.

# ---------- Runtime ----------

requires 'CGI';                       # core was dropped from Perl 5.22+
requires 'DBI';
requires 'Crypt::Bcrypt';             # password hashing (Stage 1)
requires 'Digest::SHA';               # core in modern Perl; pin for safety
requires 'HTML::Scrubber';            # XSS guard on raw <html> blocks
requires 'JSON::PP';                  # core; pinned so the prefs JSON path
                                      # never falls back to FS-joined
requires 'Text::Diff';                # page_revisions reverse-diff storage
requires 'Text::Patch';               # diff replay on revision read

# ---------- PSGI deployment (Stage 2) ----------

requires 'CGI::Compile';
requires 'CGI::Emulate::PSGI';
requires 'Plack';

# ---------- Test suite ----------

on 'test' => sub {
    requires 'Test::More';
    requires 'DBD::SQLite';           # default in-memory test DB
    requires 'HTTP::Message';         # HTTP::Request::Common for 20_http_psgi.t
};

# ---------- Optional ----------
#
# These are loaded at runtime via `eval { require ... }`; tests
# skip_all if missing, the wiki falls back to the wiki-rule pipeline.

recommends 'Text::Markdown::Discount'; # <!-- markdown --> rendering (Stage 6)
recommends 'DBD::Pg';                  # Postgres backend (Stage 4); test/40_pg.t
                                       # skips when not installed or no server
