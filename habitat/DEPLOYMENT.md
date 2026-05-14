# Habitat deployment guide

Habitat ships as both a CGI script (`index.cgi`) and a PSGI app
(`app.psgi`). The same codebase runs under every deployment in this
document — pick whichever your hosting allows.

Performance, roughly (50 sequential `?Home` requests on a single
core):

| Mode | Wall time |
|---|---|
| python3 `http.server --cgi` (dev / fork-per-request) | ~3.3s |
| Apache mod_cgi (fork-per-request) | ~2.0s |
| plackup (single-process PSGI) | ~0.5s |
| Starman 8 workers (preforking PSGI) | ~0.1s |
| Apache + mod_perl (PSGI via Plack::Handler::Apache2) | ~0.3s |
| Apache + mod_fcgid + plackup (FastCGI) | ~0.4s |
| nginx -> Starman behind reverse proxy | ~0.1s |

Roughly, **anything PSGI is 5–30× faster than CGI**. Stage 2 made
this possible; Stage 0+1 are still recommended regardless of mode.

---

## 1. CGI (simplest; works anywhere)

Bundle: `index.cgi` plus the `habitatdb/` data directory, `css/`,
`images/`, and `lib/Habitat/`. Wrap in a `cgi-bin/` directory if your
web server requires it.

### Apache 2 + mod_cgi

```apache
# /etc/apache2/sites-available/habitat.conf
<VirtualHost *:80>
    ServerName wiki.example.com
    DocumentRoot /var/www/habitat

    ScriptAlias /cgi-bin/ /var/www/habitat/
    <Directory /var/www/habitat>
        AllowOverride None
        Options +ExecCGI
        AddHandler cgi-script .cgi
        Require all granted
    </Directory>

    Alias /css/    /var/www/habitat/css/
    Alias /images/ /var/www/habitat/images/
    Alias /fonts/  /var/www/habitat/fonts/
</VirtualHost>
```

```sh
sudo a2enmod cgi
sudo apt install libcgi-pm-perl libdbi-perl libdbd-sqlite3-perl \
                 libhtml-scrubber-perl libcrypt-bcrypt-perl \
                 libtext-diff-perl libtext-patch-perl
sudo a2ensite habitat
sudo systemctl reload apache2
```

The wiki self-bootstraps its SQLite schema on first request. Trailing
slashes matter: `wiki.example.com/cgi-bin/index.cgi?Home`.

### Local dev (no Apache)

The bundled `runlocal.sh` starts a Python CGI server:

```sh
cd habitat/
./runlocal.sh         # serves http://localhost:51712/cgi-bin/index.cgi
./stoplocal.sh        # kill it
```

This is fine for development but **fork-per-request** is slow. Switch
to PSGI as soon as performance matters.

---

## 2. PSGI standalone (recommended)

`app.psgi` is the PSGI entry point. It uses `CGI::Compile` to wrap
`index.cgi` at worker startup so the per-request overhead is just
the request dispatch, not a script compile.

### Local dev — plackup

```sh
sudo apt install libplack-perl libcgi-emulate-psgi-perl libcgi-compile-perl
cd habitat/
./runpsgi.sh          # plackup -p 51712 app.psgi
./stoppsgi.sh
```

### Production — Starman (preforking)

```sh
sudo apt install libstarman-perl
cd habitat/
HABITAT_PSGI_SERVER=Starman HABITAT_WORKERS=8 ./runpsgi.sh
```

Or directly:

```sh
starman --workers 8 --listen 127.0.0.1:51712 --pid /var/run/habitat.pid \
        --daemonize app.psgi
```

Place behind a reverse proxy (next section).

### systemd unit

```ini
# /etc/systemd/system/habitat.service
[Unit]
Description=Habitat wiki (Starman)
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/habitat
ExecStart=/usr/bin/starman --workers 8 --listen 127.0.0.1:51712 \
                           /var/www/habitat/app.psgi
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now habitat
sudo systemctl status habitat
```

---

## 3. nginx + Starman (reverse proxy)

Most production deployments. Starman speaks HTTP on localhost; nginx
serves static assets and forwards dynamic requests.

```nginx
# /etc/nginx/sites-available/habitat
upstream habitat {
    server 127.0.0.1:51712;
}

server {
    listen 443 ssl http2;
    server_name wiki.example.com;

    ssl_certificate     /etc/letsencrypt/live/wiki.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wiki.example.com/privkey.pem;

    root /var/www/habitat;

    # Static assets served by nginx directly (faster, cache-friendly)
    location ~ ^/(css|images|fonts)/ {
        try_files $uri =404;
        expires 30d;
    }

    # Everything else hits the wiki
    location / {
        proxy_pass http://habitat;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    client_max_body_size 5m;       # for uploads
}
```

In your wiki config (`habitatdb/config`):

```perl
# Required when behind a reverse proxy so the wiki trusts X-Forwarded-*
$TrustedProxies = "127.0.0.1";

# Required for HTTPS cookie attributes if you redirect HTTP -> HTTPS
# (the wiki auto-detects HTTPS via X-Forwarded-Proto when the upstream
# is in $TrustedProxies)
```

---

## 4. Apache + mod_perl 2 (PSGI native)

Skip `mod_cgi`; let Apache run the PSGI app in-process.

```apache
<VirtualHost *:80>
    ServerName wiki.example.com
    DocumentRoot /var/www/habitat

    PerlPostConfigRequire /var/www/habitat/app.psgi
    <Location /wiki>
        SetHandler perl-script
        PerlResponseHandler Plack::Handler::Apache2
        PerlSetVar psgi_app /var/www/habitat/app.psgi
    </Location>

    Alias /css/    /var/www/habitat/css/
    Alias /images/ /var/www/habitat/images/
</VirtualHost>
```

```sh
sudo apt install libapache2-mod-perl2 libplack-handler-apache2-perl
```

Restart Apache. The wiki loads once per Apache worker and serves
requests from memory.

---

## 5. Apache + mod_fcgid (FastCGI)

If mod_perl isn't available but FastCGI is:

```apache
<VirtualHost *:80>
    ServerName wiki.example.com
    DocumentRoot /var/www/habitat

    FcgidInitialEnv HABITAT_PORT 51712
    FcgidWrapper /var/www/habitat/app.psgi.fcgi virtual

    ScriptAlias /wiki /var/www/habitat/app.psgi.fcgi
</VirtualHost>
```

`app.psgi.fcgi` is a tiny wrapper:

```perl
#!/usr/bin/env perl
use Plack::Handler::FCGI;
use Plack::Util;
my $app = Plack::Util::load_psgi("/var/www/habitat/app.psgi");
Plack::Handler::FCGI->new->run($app);
```

```sh
sudo apt install libapache2-mod-fcgid libplack-handler-fcgi-perl
```

---

## Config knobs that matter behind a reverse proxy

```perl
# habitatdb/config

# Trusted-proxy list (comma-separated prefixes). Without this the wiki
# IGNORES X-Forwarded-For and X-Forwarded-Proto — defenders should
# default to listing only their actual upstream IP.
$TrustedProxies = "127.0.0.1,::1";

# DB connection string. Stage 4 added Postgres support; SQLite remains
# the default and works for any deployment.
$DBName = "dbi:SQLite:dbname=db/habitatdb.db";
# $DBName = "dbi:Pg:dbname=habitat";   # Postgres alt

# Optional: limit upload size at the wiki layer too (default 210K).
# Match this with your web server's client_max_body_size.
$MaxPost = 1024 * 5 * 1024;   # 5 MB
$PermUseUpload = 50;          # 0 = anyone, 50 = editors, 100 = admins
```

## Migrating from CGI to PSGI

No data migration; just deployment changes. Steps:

1. Install the Plack stack (`libplack-perl`, `libcgi-emulate-psgi-perl`,
   `libcgi-compile-perl`).
2. Test locally: `./runpsgi.sh` then visit `http://localhost:51712/`.
3. Switch your web server config from `mod_cgi` to one of sections 2/3/4/5.
4. The wiki's data directory (`habitatdb/`) and SQLite/Postgres DB
   stay untouched. No URL changes are needed.

## Migrating from SQLite to Postgres

```sh
# 1. Set up Postgres
sudo apt install postgresql libdbd-pg-perl
sudo -u postgres createuser -d $USER
createdb habitat

# 2. Migrate the data (does not touch the source SQLite file)
cd habitat/
perl utils/migrate.pl \
    --source 'dbi:SQLite:dbname=db/habitatdb.db' \
    --dest   'dbi:Pg:dbname=habitat'

# 3. Switch the wiki config to Postgres
sed -i 's|dbi:SQLite:.*|dbi:Pg:dbname=habitat";|' habitatdb/config

# 4. Restart the wiki (Apache reload, or `systemctl restart habitat`)
```

The migration is one-way; keep the SQLite file as backup until you
trust the new instance.

## Diagnostics

- **Live request log**: Starman writes to stdout/stderr — use
  systemd `journalctl -u habitat`.
- **Wiki-internal warnings**: Stage 5 silenced ~150 "Use of
  uninitialized value" warnings. Anything that still shows up in
  the log is real and worth fixing.
- **Slow page**: hit `/?action=index` and check whether the
  page-list rendering is what's slow. Stage 4's `ORDER BY revision
  DESC LIMIT 1` queries are fast; if they aren't, run `EXPLAIN` on
  the affected table.
- **CSRF errors on legitimate edits**: usually a clock skew between
  the worker and the database. Check that `$Now` in the wiki and
  `now()` in SQL agree to within a few seconds.

## Where stuff lives

```
habitat/
├── index.cgi              # CGI entry point
├── app.psgi               # PSGI entry point (wraps index.cgi)
├── runlocal.sh            # dev CGI runner (python3 http.server)
├── runpsgi.sh             # dev PSGI runner (plackup, Starman)
├── stoplocal.sh
├── stoppsgi.sh
├── lib/Habitat/
│   └── Store.pm           # SQL helpers + dialect-aware schema
├── utils/
│   └── migrate.pl         # DB migration tool
├── test/                  # 397-assertion test suite
├── habitatdb/
│   ├── config             # site config (DBName, $SiteName, etc.)
│   ├── secret             # auto-generated HMAC secret (mode 0600)
│   └── i18n/lang.*        # translation files
├── db/
│   └── habitatdb.db       # SQLite (if SQLite mode)
├── css/, images/, fonts/  # static assets
└── DEPLOYMENT.md          # this file
```
