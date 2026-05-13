# Habitat test suite

Characterization tests for the wiki. Each file documents the current
behavior of a specific module or layer so that subsequent refactors
(stages 4 and beyond) can be verified by re-running the suite.

## Running

```sh
cd habitat/
prove test/*.t              # run everything
prove -v test/01_store.t    # one file, verbose
prove -j 4 test/*.t         # parallel
```

Total runtime is a few seconds. No external services needed: every
test that touches the database uses an in-memory SQLite handle that
the harness creates fresh and applies the production schema to.

## Dependencies

All standard Debian/Ubuntu packages:

```
libtest-simple-perl       # Test::More (often already core)
libdbi-perl
libdbd-sqlite3-perl
libplack-perl
libhttp-message-perl      # HTTP::Request::Common
libcgi-emulate-psgi-perl
libcgi-compile-perl
libcrypt-bcrypt-perl
libhtml-scrubber-perl
libdigest-sha-perl        # core
```

Plus the wiki's own runtime modules (CGI.pm, Crypt::Bcrypt, JSON::PP,
etc.). Tests fail to load if any are missing — the error message
names the module.

## What each file covers

| File | Subject |
|---|---|
| `HabitatHarness.pm` | Shared bootstrap: chdir, idempotent index.cgi load, fresh in-memory SQLite + schema, frozen `$Now` and `$SiteSecret` for reproducible HMAC tokens |
| `01_store.t` | `Habitat::Store` helpers: `SafeIdent`, `ReadDBItems`, `WriteDBItems`, `DeleteDBItems`, `CopyDBItems`. Identifier whitelisting, bind-value safety, empty-condition safety guards, error cases |
| `02_crypto.t` | `RandomBytes`/`RandomHex` CSPRNG, `Hmac` (HMAC-SHA256), `ConstantEq` timing-safe compare. Determinism, secret rotation, undef/length edge cases |
| `03_password.t` | `HashPassword` (bcrypt $2b$), `VerifyPassword` legacy-crypt() fallback, `IsLegacyPasswordHash`, `UpgradePasswordHashDB` opportunistic migration on login |
| `04_session.t` | `SignSessionToken`/`VerifySessionToken` HMAC-signed cookie format, expiry, tamper rejection, secret rotation, `IsRequestSecure` HTTPS detection |
| `05_csrf.t` | `GenCSRFToken`/`VerifyCSRFToken` UserID binding, expiry, secret rotation, anonymous-uid coverage |
| `06_captcha.t` | `PrintCaptcha`/`VerifyCaptcha` HMAC-signed challenge replacing the legacy DES path. Operand range, embedded-answer signing, expiry, tamper detection |
| `07_throttle.t` | `EnsureLoginThrottleTable`, `LoginThrottleBlocked`/`Hit`/`Clear`. Counter progression, independent keys, window expiry, no-op safety on empty/undef keys |
| `08_evallocalrules.t` | Stage 0 JSON regex pipeline replacing `eval(STRING) $LateRules`. Substitution, backreferences (`$1`, `\1`), flags, error handling. **Verifies that user-supplied `to` strings are NEVER eval'd as Perl** (backticks, `@{[...]}`, `$ENV{...}` are literal) |
| `09_validid.t` | `ValidId` page-name gatekeeper, `FreeToNormal` canonicalization. Accepted/rejected shapes, SQLi-shaped names, behavior under both `$UpperFirst`/`$FreeUpper` settings |
| `10_quote_scrub.t` | `QuoteHtml` entity escaping, `ScrubRawHtml` (HTML::Scrubber wrapper). Allowed tags survive, dangerous tags/`on*` handlers/`javascript:` URLs stripped, allow-listed data-image URLs kept |
| `20_http_psgi.t` | End-to-end via `Plack::Test` (no real server): basic browse paths return 200, state isolation between consecutive requests, CSRF enforcement on POST, generic-error login + throttle table population |

## Design notes

- **Frozen time and pinned secret.** Stage-1 tokens (session, CSRF,
  captcha) bind to `$Now` and `$SiteSecret`. The harness's
  `freeze_time()` and `set_test_secret()` make those reproducible so
  tests don't flake on slow machines.

- **Schema in code, not on disk.** `HabitatHarness::apply_schema()`
  carries a copy of `db/gendb.sql` as Perl string. If you change the
  production schema, update both — the test harness is intentionally
  not reading the .sql file so tests don't fail if the on-disk schema
  drifts during a refactor.

- **Idempotent loader.** `HabitatHarness::load_wiki()` is safe to
  call multiple times within a single test process. The HTTP test
  (`20_http_psgi.t`) deliberately lets `app.psgi` compile the wiki
  itself rather than pre-loading via the harness, avoiding double
  compilation.

- **Pre-existing warnings filtered.** The legacy render path emits
  `Use of uninitialized value` warnings from untouched code paths
  (~50 per page render). The HTTP test silences those at the
  `$SIG{__WARN__}` boundary so real test output stays readable.
  These are slated for cleanup in a later stage but are noise here.

## Adding a test

The bare minimum:

```perl
#!/usr/bin/env perl
use strict;
use warnings;
use FindBin qw($Bin);
use lib $Bin;
use Test::More;
use HabitatHarness;

HabitatHarness::load_wiki();
HabitatHarness::set_test_secret();    # if you need HMAC stability
HabitatHarness::fresh_test_db();      # if you need DB

# ... assertions ...

done_testing;
```

Functions defined in `index.cgi` are callable as
`HabitatEngine::FuncName(...)`. Things in `lib/Habitat/Store.pm` are
callable either as `Habitat::Store::FuncName(...)` or imported via
`use Habitat::Store qw(FuncName)`.

Tests should pin `local $HabitatEngine::Whatever = ...` for any
config flag they care about, then call `HabitatEngine::InitLinkPatterns()`
again if they changed pattern-relevant flags (`$FreeLinks`,
`$UseSubpage`, etc.). See `09_validid.t` for the pattern.
