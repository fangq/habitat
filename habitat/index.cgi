#!/usr/bin/env perl
#
# Habitat - A Portable Content Management System
#
# by Qianqian Fang <q.fang at neu.edu>
#
# key features:
#   1. object-oriented wiki text data structures
#   2. hierachical wiki page naming scheme
#   3. page embedding and flexible reference
#   4. regular expression rules for text manipulation
#   5. plugin strctures allow easy extension
#   6. local database (sqlite) backend
#
# This wiki engine was modified from UseModWiki (1.0)
#
# UseModWiki version 1.0 (September 12, 2003)
# Copyright (C) 2000-2003 Clifford A. Adams  <caadams@usemod.com>
# Copyright (C) 2002-2003 Sunir Shah  <sunir@sunir.org>
# Based on the GPLed AtisWiki 0.3  (C) 1998 Markus Denker
#    <marcus@ira.uka.de>
# ...which was based on
#    the LGPLed CVWiki CVS-patches (C) 1997 Peter Merel
#    and The Original WikiWikiWeb  (C) Ward Cunningham
#        <ward@c2.com> (code reused with permission)
# Email and ThinLine options by Jim Mahoney <mahoney@marlboro.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
#    Free Software Foundation, Inc.
#    59 Temple Place, Suite 330
#    Boston, MA 02111-1307 USA

package HabitatEngine;

# if you do not have root permission, you can install
# DBD::SQLite and Crypt::DES modules into ./lib folder.
# To install, you first need to download the source
# package from CPAN, and unpack the package, type
#    perl Makefile.PL PREFIX=/path/where/you/can/write
# then, "make" and "make install", after installation, you
# need to move all the sub-folders under
# PREFIX/lib<64>/perl5/site_perl/x.x.x/xxx-linux-thread-multi/
# into ./lib folder

use lib "./lib";
use strict;
use warnings;

use DBI;
# Text::Diff, Text::Patch, HTML::Scrubber and JSON::PP are loaded on
# demand (require at the call site): an ordinary page view needs none of
# them, and under plain CGI every module is re-loaded on every request
# (~14 ms for these four plus Crypt::Bcrypt on the NeuroJSON host).
use Habitat::Store qw(SafeIdent ReadDBItems WriteDBItems DeleteDBItems CopyDBItems);
use Habitat::Auth qw(
  RandomBytes RandomHex GetSiteSecret Hmac ConstantEq
  SignSessionToken VerifySessionToken BuildSessionCookie IsRequestSecure
  GenCSRFToken VerifyCSRFToken CSRFCheckOrDie
  PrintCaptcha VerifyCaptcha
  EnsureLoginThrottleTable LoginThrottleBlocked LoginThrottleHit LoginThrottleClear
  HashPassword VerifyPassword IsLegacyPasswordHash UpgradePasswordHashDB
);

# Render utilities (Phase 1 of the render extraction). Habitat/Render.pm
# defines these subs in the HabitatEngine package, so bareword callers
# below — and all the engine globals the subs read/write — keep working
# unchanged.
use Habitat::Render;

#use diagnostics;

no strict 'refs';

local $| = 1;    # Do not buffer output (localized for mod_perl)

# Configuration/constant variables:
use vars qw(@RcDays @HtmlPairs @HtmlSingle
  $TempDir $LockDir $DataDir $HtmlDir $UserDir $KeepDir $PageDir
  $InterFile $RcFile $RcOldFile $IndexFile $FullUrl $SiteName $HomePage
  $LogoUrl $RcDefault $IndentLimit $RecentTop $PermEditAllowed $UseDiff
  $UseSubpage $UseCache $RawHtml $SimpleLinks $NonEnglish $LogoLeft
  $KeepDays $HtmlTags $HtmlLinks $UseDiffLog $KeepMajor $KeepAuthor
  $FreeUpper $EmailNotify $SendMail $EmailFrom $FastGlob $EmbedWiki
  $ScriptTZ $BracketText $UseAmPm $UseConfig $UseLookup
  $RedirType $AdminPass $EditPass $UseHeadings $NetworkFile $BracketWiki
  $FreeLinks $WikiLinks $AdminDelete $FreeLinkPattern $RCName $RunCGI
  $ShowEdits $ThinLine $LinkPattern $InterLinkPattern $InterSitePattern
  $UrlProtocols $UrlPattern $ImageExtensions $RFCPattern $ISBNPattern
  $FS $FS1 $FS2 $FS3 $FS4 $FS5 $CookieName $SiteBase $StyleSheet $NotFoundPg
  $FooterNote $EditNote $MaxPost $NewText $HttpCharset
  $UserGotoBar $DeletedPage $ReplaceFile @ReplaceableFiles $TableSyntax
  $MetaKeywords $NamedAnchors $InterWikiMoniker $SiteDescription $RssLogoUrl
  $NumberDates $EarlyRules $LateRules $NewFS $KeepSize $SlashLinks $BGColor
  $UpperFirst $AdminBar $RepInterMap $ConfirmDel
  $MaskHosts $LockCrash $ConfigFile $LangFile $LangID $HistoryEdit $OldThinLine
  @IsbnNames @IsbnPre @IsbnPost $EmailFile $FavIcon $RssDays $UserHeader
  $UserBody $StartUID $ParseParas $AuthorFooter $PermUseUpload $AllUpload
  $UploadDir $UploadUrl $LimitFileUrl $MaintTrimRc $SearchButton
  $EditNameLink $UseMetaWiki @ImageSites $BracketImg $cvUTF8ToUCS2
  $cvUCS2ToUTF8 $MaxTreeDepth $PageEmbed $MaxEmbedDepth $IsPrintTree
  $AMathML $AMathMLPath $MathColor $UseCaptcha
  $UserBuildinCSS %BuildinPages %TextCache %Pages $UseDetailedLog
  $PageLog $UserLog $PrintedHeader $PageItemCount $ListItemCount
  $HistoryLimit $RCHistoryLimit $InlineDiffLimit $TrustedProxies);

# Other global variables:
use vars qw(%InterSite $SaveUrl $SaveNumUrl
  %KeptRevisions %UserCookie %SetCookie %UserData %IndexHash %Translate
  %LinkIndex $InterSiteInit $SaveUrlIndex $SaveNumUrlIndex $MainPage
  $OpenPageName @IndexList $IndexInit $TableMode
  $q $Now $UserID $TimeZoneOffset $ScriptName $BrowseCode $OtherCode
  $AnchoredLinkPattern @HeadingNumbers $TableOfContents $QuotedFullUrl
  $ConfigError $LangError $UploadPattern $LocalTree %Permissions %EditPermissions
  %NameSpaceV0 %NameSpaceV1 %NameSpaceE0 %NameSpaceE1 $DiscussSuffix
  $dbh $DBName $DBUser $DBPass %DBErr %DBPrefix
  %ExtViewer %ExtEditor $UseActivation %ExportPage $HtmlScrubber $DocType
  $StaticCacheDir $StaticCacheOK $StaticCacheGen
  $SecretFile $SiteSecret $LoginMaxAttempts $LoginThrottleWindow %RuleDirCache
  $UsePasswordReset $PasswordResetTTL $PasswordResetMailGap $UseHttps $DBTablePrefix
  $RegistrationPermission);

# == Configuration =====================================================
$DataDir    = "./habitatdb";                   # Main wiki directory
$UseConfig  = 1;                               # 1 = use config file,    0 = do not look for config
$ConfigFile = "$DataDir/config";               # Configuration file
$LangID     = "en";                            # Default language
$LangFile   = "$DataDir/i18n/lang.$LangID";    # i18n  file

# Default configuration (used if UseConfig is 0)
$CookieName = "HabitatWiki";                   # Name for this wiki (for multi-wiki sites)
$SiteName   = "HabitatWiki";                   # Name of site (used for titles)
$HomePage   = "Home";                          # Home page (change space to _)
$RCName     = "RecentChanges";                 # Name of changes page (change space to _)
$LogoUrl    = "";                              # URL for site logo ("" for no logo)
$ENV{PATH}  = "/usr/bin/";                     # Path used to find "diff"
$ScriptTZ   = "";                              # Local time zone ("" means do not print)
$RcDefault  = 30;                              # Default number of RecentChanges days
@RcDays     = qw(1 3 7 30 90);                 # Days for links on RecentChanges
$KeepDays   = 14;                              # Days to keep old revisions
$SiteBase   = "";                              # Full URL for <base> header
$FullUrl    = "";

# Set if the auto-detected URL is wrong
$RedirType        = 1;                         # 1 = CGI.pm, 2 = script, 3 = no redirect
$AdminPass        = "";                        # Set to non-blank to enable password(s)
$EditPass         = "";                        # Like AdminPass, but for editing only
$StyleSheet       = "wiki.css";                # URL for CSS stylesheet (like "/wiki.css")
$NotFoundPg       = "";                        # Page for not-found links ("" for blank pg)
$EmailFrom        = "Wiki";                    # Text for "From: " field of email notes.
$SendMail         = "/usr/sbin/sendmail";      # Full path to sendmail executable
$FooterNote       = "";                        # HTML for bottom of every page
$EditNote         = "";                        # HTML notice above buttons on edit page
$MaxPost          = 1024 * 210;                # Maximum 210K posts (about 200K for pages)
$NewText          = "";                        # New page text ("" for default message)
$HttpCharset      = "UTF-8";                   # Charset for pages, like "iso-8859-2"
$UserGotoBar      = "";                        # HTML added to end of goto bar
$InterWikiMoniker = '';                        # InterWiki moniker for this wiki. (for RSS)
$SiteDescription  = $SiteName;                 # Description of this wiki. (for RSS)
$RssLogoUrl       = '';                        # Optional image for RSS feed
$EarlyRules       = '';                        # Local syntax rules for wiki->html (evaled)
$LateRules        = '';                        # Local syntax rules for wiki->html (evaled)
$KeepSize         = 0;                         # If non-zero, maximum size of keep file
$BGColor          = 'white';                   # Background color ('' to disable)
$FavIcon          = '';                        # URL of bookmark/favorites icon, or ''
$RssDays          = 7;                         # Default number of days in RSS feed
$UserHeader       = '';                        # Optional HTML header additional content
$UserBody         = '';                        # Optional <body> tag additional content
$UserBuildinCSS   = '';                        # Optional build-in css
$StartUID         = 1001;                      # Starting number for user IDs
$UploadDir        = '';                        # Full path (like /foo/www/uploads) for files
$UploadUrl        = '';                        # Full URL (like http://foo.com/uploads)
@ImageSites       = qw();                      # Url prefixes of good image sites: ()=all

# Major options:
$UseSubpage       = 1;                         # 1 = use subpages,       0 = do not use subpages
$UseCache         = 0;                         # 1 = cache HTML pages,   0 = generate every page
$PermEditAllowed  = 1;                         # 1 = editing allowed,    0 = read-only
$RawHtml          = 1;                         # 1 = allow <html> tag,   0 = no raw HTML in pages
$HtmlTags         = 0;                         # 1 = "unsafe" HTML tags, 0 = only minimal tags
$UseDiff          = 1;                         # 1 = use diff features,  0 = do not use diff
$FreeLinks        = 1;                         # 1 = use [[word]] links, 0 = LinkPattern only
$WikiLinks        = 1;                         # 1 = use LinkPattern,    0 = use [[word]] only
$AdminDelete      = 1;                         # 1 = Admin only deletes, 0 = Editor can delete
$RunCGI           = 1;                         # 1 = Run script as CGI,  0 = Load but do not run
$EmailNotify      = 0;                         # 1 = use email notices,  0 = no email on changes
$EmbedWiki        = 0;                         # 1 = no headers/footers, 0 = normal wiki pages
$DeletedPage      = 'DeletedPage';             # 0 = disable, 'PageName' = tag to delete page
$ReplaceFile      = 'ReplaceFile';             # 0 = disable, 'PageName' = indicator tag
@ReplaceableFiles = ();                        # List of allowed server files to replace
$TableSyntax      = 1;                         # 1 = wiki syntax tables, 0 = no table syntax
$NewFS            = 0;                         # 1 = new multibyte $FS,  0 = old $FS
$PermUseUpload    = 0;                         # 1 = allow uploads,      0 = no uploads

# Minor options:
$LogoLeft     = 1;                             # 1 = logo on left,       0 = logo on right
$RecentTop    = 1;                             # 1 = recent on top,      0 = recent on bottom
$UseDiffLog   = 0;                             # 1 = save diffs to log,  0 = do not save diffs
$KeepMajor    = 1;                             # 1 = keep major rev,     0 = expire all revisions
$KeepAuthor   = 1;                             # 1 = keep author rev,    0 = expire all revisions
$ShowEdits    = 1;                             # 1 = show minor edits,   0 = hide edits by default
$HtmlLinks    = 0;                             # 1 = allow A HREF links, 0 = no raw HTML links
$SimpleLinks  = 0;                             # 1 = only letters,       0 = allow _ and numbers
$NonEnglish   = 0;                             # 1 = extra link chars,   0 = only A-Za-z chars
$ThinLine     = 0;                             # 1 = fancy <hr> tags,    0 = classic wiki <hr>
$BracketText  = 1;                             # 1 = allow [URL text],   0 = no link descriptions
$UseAmPm      = 1;                             # 1 = use am/pm in times, 0 = use 24-hour times
$UseHeadings  = 1;                             # 1 = allow = h1 text =,  0 = no header formatting
$NetworkFile  = 1;                             # 1 = allow remote file:, 0 = no file:// links
$BracketWiki  = 0;                             # 1 = [WikiLnk txt] link, 0 = no local descriptions
$UseLookup    = 1;                             # 1 = lookup host names,  0 = skip lookup (IP only)
$FreeUpper    = 1;                             # 1 = force upper case,   0 = do not force case
$FastGlob     = 1;                             # 1 = new faster code,    0 = old compatible code
$MetaKeywords = 1;                             # 1 = Google-friendly,    0 = search-engine averse
$NamedAnchors = 1;                             # 0 = no anchors, 1 = enable anchors,
                                               # 2 = enable but suppress display
$SlashLinks   = 0;                             # 1 = use script/action links, 0 = script?action
$UpperFirst   = 1;                             # 1 = free links start uppercase, 0 = no ucfirst
$AdminBar     = 1;                             # 1 = admins see admin links, 0 = no admin bar
$RepInterMap  = 0;                             # 1 = intermap is replacable, 0 = not replacable
$ConfirmDel   = 1;                             # 1 = delete link confirm page, 0 = immediate delete
$MaskHosts    = 0;                             # 1 = mask hosts/IPs,      0 = no masking
$LockCrash    = 0;                             # 1 = crash if lock stuck, 0 = auto clear locks
$HistoryEdit  = 0;                             # 1 = edit links on history page, 0 = no edit links
$OldThinLine  = 0;                             # 1 = old ==== thick line, 0 = ------ for thick line
$NumberDates  = 0;                             # 1 = 2003-6-17 dates,     0 = June 17, 2003 dates
$ParseParas   = 0;                             # 1 = new paragraph markup, 0 = old markup
$AuthorFooter = 1;                             # 1 = show last author in footer, 0 = do not show
$AllUpload    = 0;                             # 1 = anyone can upload,   0 = only editor/admins
$LimitFileUrl = 1;                             # 1 = limited use of file: URLs, 0 = no limits
$MaintTrimRc  = 0;                             # 1 = maintain action trims RC, 0 = only maintainrc
$SearchButton = 0;                             # 1 = search button on page, 0 = old behavior
$EditNameLink = 0;                             # 1 = edit links use name (CSS), 0 = '?' links
$UseMetaWiki  = 0;                             # 1 = add MetaWiki search links, 0 = no MW links
$BracketImg   = 1;                             # 1 = [url url.gif] becomes image link, 0 = no img

$PageEmbed           = 1;            # 1 = {{page|name}} format
$MaxEmbedDepth       = 5;            # maximum depth for page embedding
$IsPrintTree         = 1;            # print tree for subpages
$MaxTreeDepth        = 8;
$AMathML             = 0;            # 1 = allow <amath> tags, 0 = no amath markup
$AMathMLPath         = "";
$MathColor           = "yellow";
$UseCaptcha          = 1;            # flag to enable captcha
$DiscussSuffix       = '..discuss';
$DBName              = "";
$UseActivation       = 0;
$DocType             = q(<!DOCTYPE HTML PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN">);    # first line of every page; e.g. "<!DOCTYPE HTML>" for HTML5 standards mode
$StaticCacheDir      = '';    # absolute dir for the mod_rewrite static page cache (DEPLOYMENT.md); '' = off
$UseDetailedLog      = 0;
$PageItemCount       = 20;
$ListItemCount       = 100;
$HistoryLimit        = 50;
$RCHistoryLimit      = 100;
$InlineDiffLimit     = 50;
$LoginMaxAttempts    = 5;            # Block after this many failed logins
$LoginThrottleWindow = 300;          # Counted within this many seconds
$UsePasswordReset    = 1;            # "Forgot password?" link on the login page (needs a working $SendMail)
$PasswordResetTTL    = 86400;        # A reset link expires after this many seconds
$PasswordResetMailGap = 900;         # At most one reset email per account in this many seconds
$UseHttps            = 1;            # Links the wiki builds to itself (redirects, emails, RSS) use https,
                                     # even when a TLS proxy (Cloudflare) talks plain http to the server.
                                     # Never applied to localhost. 0 = keep the request's own scheme.
$DBTablePrefix       = '';           # Prefix for every table name (e.g. "dev_" -> dev_page, dev_users),
                                     # so several wikis can share one database. Letters, digits, _ only.
$RegistrationPermission = 'editor';  # Who may create an account (against spam sign-ups):
                                     #   'user'   = anyone;
                                     #   'editor' = only with a token from $EditPass or $AdminPass;
                                     #   'admin'  = only with a token from $AdminPass.
                                     # The token only unlocks registration; the new account is an
                                     # ordinary user. No matching token configured = registration closed.
$TrustedProxies      = '';           # Comma-separated list of trusted proxy IPs/CIDR-like prefixes.
                                     # Only when REMOTE_ADDR matches one of these will
                                     # HTTP_X_REMOTE_ADDR / HTTP_X_FORWARDED_FOR be honored.
                                     # Example: "127.0.0.1,10.0.0.1,192.168.1."

# Names of sites.  (The first entry is used for the number link.)
@IsbnNames = ( 'bn.com', 'amazon.com', 'search' );

# Full URL of each site before the ISBN
@IsbnPre = (
    'http://shop.barnesandnoble.com/bookSearch/isbnInquiry.asp?isbn=',
    'http://www.amazon.com/exec/obidos/ISBN=',
    'http://www.pricescan.com/books/BookDetail.asp?isbn='
);

# Rest of URL of each site after the ISBN (usually '')
@IsbnPost = ( '', '', '' );

# HTML tag lists, enabled if $HtmlTags is set.
# Scripting is currently possible with these tags,
# so they are *not* particularly "safe".
# Tags that must be in <tag> ... </tag> pairs:
@HtmlPairs = qw(b i u font big small sub sup h1 h2 h3 h4 h5 h6 cite code
  em s strike strong tt var div center blockquote ol ul dl table caption
  kbd nav header section article aside footer);

# Single tags (that do not require a closing /tag)
@HtmlSingle = qw(br p hr li dt dd tr td th);
@HtmlPairs  = ( @HtmlPairs, @HtmlSingle );     # All singles can also be pairs

# == You should not have to change anything below this line. =============
$IndentLimit = 20;                             # Maximum depth of nested lists
$PageDir     = "$DataDir/page";                # Stores page data
$HtmlDir     = "$DataDir/html";                # Stores HTML versions
$UserDir = "$DataDir/users";    # Stores user data (table named "users" -- "user" is reserved in PG)
$KeepDir = "$DataDir/keep";     # Stores kept (old) page data
$TempDir = "$DataDir/temp";     # Temporary files and locks
$LockDir = "$TempDir/pagelock"
  ;    # DB is locked if this exists (table renamed from "lock" — MariaDB reserved word)
$InterFile  = "$DataDir/intermap";    # Interwiki site->url map
$RcFile     = "$DataDir/rclog";       # New RecentChanges logfile
$RcOldFile  = "$DataDir/oldrclog";    # Old RecentChanges logfile
$IndexFile  = "$DataDir/pageidx";     # List of all pages
$EmailFile  = "$DataDir/watch";       # Email notification lists
$UserLog    = "$DataDir/userlog";     # Email notification lists
$PageLog    = "$DataDir/pagelog";     # Email notification lists
$SecretFile = "$DataDir/secret";      # Server-side HMAC key (auto-created on first run)

if ($RepInterMap) {
    push @ReplaceableFiles, $InterFile;
}

# Wipe every per-request global that could otherwise leak across
# requests when the wiki runs under a persistent runtime (PSGI/Plack,
# Starman, mod_perl). No-op-correct under plain CGI since each fork
# starts with fresh globals anyway.
#
# Globals already reset by InitRequest / InitCookie / InitWikiEnv are
# NOT duplicated here. This sub catches the rest: render scratch
# space, caches, header-emitted flags, and language state.
sub ResetRequestState {
    $StaticCacheOK   = 1;     # cleared when this response must not be cached statically
    $StaticCacheGen  = '';
    %TextCache       = ();
    %RuleDirCache    = ();
    $LocalTree       = undef;
    $TableOfContents = '';
    @HeadingNumbers  = ();
    $PrintedHeader   = 0;
    $IndexInit       = 0;
    $InterSiteInit   = 0;
    %InterSite       = ();
    $TableMode       = 0;
    @IndexList       = ();
    $OpenPageName    = '';
    $ConfigError     = '';
    $LangError       = '';
    $MainPage        = '.';
    %Permissions     = ();
    %EditPermissions = ();
    %NameSpaceV0     = ();
    %NameSpaceV1     = ();
    %NameSpaceE0     = ();
    %NameSpaceE1     = ();
    undef $q;

    # Per-page Save*Url* symbol-table aliases created by RestorePageHash
    # are not enumerated here; each WikiToHTML call re-initializes the
    # ones it touches before use.
}

# The "main" program, called at the end of this script file.
sub DoWikiRequest {
    ResetRequestState();

    # Server-Software-based dispatch. Empty when invoked from a CLI
    # smoke test (`perl index.cgi`) — guard so we don't warn.
    my $server = $ENV{'SERVER_SOFTWARE'} // '';
    if ( $server =~ /^SimpleHTTP/ ) {    # running a local wiki
        $DataDir = $ENV{'PWD'} . "/$DataDir" if ( $DataDir =~ /^[^\/]/ );
    }
    if ( $UseConfig && ( -f $ConfigFile ) ) {
        if ( !do $ConfigFile ) {         # Some error occurred
            $ConfigError = $@;
            if ( $ConfigError eq '' ) {

                # Unfortunately, if the last expr returns 0, one will get a false
                # error above.  To remain compatible with existing installs the
                # wiki must not report an error unless there is error text in $@.
                # (Errors in "use strict" may not have error text.)
                # Uncomment the line below if you want to catch use strict errors.
                $ConfigError = T('Unknown Error (no error text)');
            }
        }
        if ( ( $ENV{'SERVER_SOFTWARE'} // '' ) =~ /^SimpleHTTP/ ) {    # running a local wiki
            $LogoUrl    = "/$LogoUrl"    if ( $LogoUrl    =~ /^[^\/]/ );
            $StyleSheet = "/$StyleSheet" if ( $StyleSheet =~ /^[^\/]/ );
            $FavIcon    = "/$FavIcon"    if ( $FavIcon    =~ /^[^\/]/ );
        }
    }

    &InitLinkPatterns();
    &InitWikiEnv();
    &StaticCacheCheckStamp();
    if ( !&DoCacheBrowse() ) {
        eval $BrowseCode;
        &InitRequest() or return;
        if ( !&DoBrowseRequest() ) {
            eval $OtherCode;
            &DoOtherRequest();
        }
    }
    &CleanWikiEnv();
}

# Keep $dbh alive across requests under a persistent runtime. Under
# plain CGI the process exits immediately after, so the OS reaps the
# handle either way. Explicit disconnect is intentionally omitted.
sub CleanWikiEnv {
    return;
}

# == Common and cache-browsing code ====================================
# InitLinkPatterns moved to Habitat::Render (phase 1 of render extraction).

sub InitWikiEnv {
    $Habitat::Store::TablePrefix = $DBTablePrefix;    # table names (see DBTable)

    # Connect (or reconnect) lazily. Under PSGI/Starman this runs once per
    # worker; subsequent requests reuse the same $dbh after a cheap ping.
    # SQLite ping is a no-op; matters more for Postgres / network DBs.
    if ( $DBName ne '' ) {
        my $alive = 0;
        if ( defined $dbh ) {
            $alive = eval { $dbh->ping } ? 1 : 0;
        }
        if ( !$alive ) {
            undef $dbh;
            $dbh = DBI->connect( $DBName, $DBUser, $DBPass, \%DBErr )
              or die($DBI::errstr);

            # Register the REGEXP UDF that getnextnum / GetLocalTree
            # rely on — but only on SQLite, where there is no built-in.
            # Postgres has the `~` operator (selected by
            # Habitat::Store::regex_op) so no UDF is needed.
            my $driver = eval { $dbh->{Driver}{Name} } || '';
            if ( $driver eq 'SQLite' ) {
                $dbh->func(
                    'regexp', 2,
                    sub {
                        my ( $regex, $string ) = @_;
                        return $string =~ /$regex/;
                    },
                    'create_function'
                );
            }

            # Schema bootstrap. ensure_schema reads the fingerprint that
            # init_schema recorded and only re-runs it when the schema
            # code changed (or on a fresh database): one SELECT per
            # connection instead of ~25 idempotent DDL statements, which
            # cost ~25 ms per CGI request on MariaDB.
            eval { Habitat::Store::ensure_schema($dbh) };
            $ConfigError .= "schema bootstrap warning: $@" if $@;
        }
    } else {
        $ConfigError .= "database $DBName does not exist";
    }
    %Pages = ( 'page' => (), 'text' => (), 'section' => (), 'embed' => () );

    # $WikiCipher / $CaptchaKey retired: captcha is now an HMAC challenge
    # signed by the site secret. $UseCaptcha still gates whether captcha
    # is rendered.
}

# get parameters before reading cookies
sub InitParam {
    my ( $buffer, @pairs, %param, $value, $name, $pair );
    if ( length( $ENV{'QUERY_STRING'} ) > 0 ) {
        $buffer = $ENV{'QUERY_STRING'};
        @pairs  = split( /&/, $buffer );
        foreach $pair (@pairs) {
            ( $name, $value ) = split( /=/, $pair );

            # Bare keys like "?foo&bar" leave $value undef.
            $value //= '';
            $value =~ s/%([a-fA-F0-9][a-fA-F0-9])/pack("C", hex($1))/eg;
            $param{$name} = $value;
        }
    }
    return %param;
}

# Simple HTML cache
sub DoCacheBrowse {
    my ( $query, $idFile, $text, $language, %param );

    return 0 if ( !$UseCache );

    # Stage 6: cache is anonymous-only (see BrowsePage write guard).
    # DoCacheBrowse runs BEFORE InitCookie (which sets $UserID), so
    # we use the raw cookie header as the anonymous-marker: any
    # incoming Cookie at all means "might be authenticated, skip the
    # cache". Conservative — anonymous requests carrying stale cookies
    # also skip — but never leaks per-user content to other users.
    return 0 if ( defined( $ENV{HTTP_COOKIE} ) && $ENV{HTTP_COOKIE} ne '' );
    $query = $ENV{'QUERY_STRING'} // '';
    %param = &InitParam();

    # Default the params we test below so missing-key reads don't
    # trigger uninit warnings. The function is called on every
    # request so most lookups have no matching query-string key.
    for my $k (qw(action keywords format raw revision embed diff lang id)) {
        $param{$k} //= '';
    }

    if ( ( $query eq "" ) && ( ( $ENV{'REQUEST_METHOD'} // '' ) eq "GET" ) ) {
        $query = $HomePage;    # Allow caching of home page.
    }
    if ( !( $query =~ /^$LinkPattern$/ ) && $param{ 'action' ne 'browse' } ) {
        if ( !( $FreeLinks && ( $query =~ /^$FreeLinkPattern$/ ) ) ) {
            return 0;          # Only use cache for simple links
        }
    }
    if (
        ( $param{'action'} eq 'browse' || $param{'keywords'} ne '' )
        && (   $param{'format'} eq 'json'
            || $param{'raw'}
            || $param{'revision'}
            || $param{'embed'} == 1
            || $param{'diff'} ne '' )
      )
    {
        return 0;
    }
    if ( $param{'keywords'} ne '' ) {
        $query = $param{'keywords'};
    }
    if ( $param{'action'} eq 'browse' ) {
        $query = $param{'id'};
    }
    $language = $param{'lang'};
    if ( $language eq '' ) {
        $language = $LangID;
    }
    my $htmldb    = DBTable($HtmlDir);
    my $pagelogdb = DBTable($PageLog);

    if ( $dbh eq "" || $htmldb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $text = ReadDBItems( $htmldb, 'text', '', '', "id=?", "$query\[$language\]" );
    if ( $text ne '' ) {
        print $text;
        if ( $pagelogdb ne "" ) {
            UpdatePageLogDB( $pagelogdb, $query );
        }
        AddUserLogDB( -1, "Cr", $query );
        return 1;
    }
    return 0;
}

sub GetHtmlCacheFile {
    my ($id) = @_;

    return $HtmlDir . "/" . &GetPageDirectory($id) . "/$id.htm";
}

sub GetPageDirectory {
    my ($id) = @_;
    my $subdir;
    my @letters;
    my $firstletter;

    if ( $id =~ /^([a-zA-Z])/ ) {
        $firstletter = uc($1);

        #    if($id =~ /(.+)\/.+$/){
        #    	return $firstletter."/$1";
        #    }else
        { return $firstletter; }
    }
    if ( $id =~ /^([\x80-\xff][\x80-\xff][\x80-\xff])/ ) {
        @letters = unpack( "C*", $1 );
        $subdir  = sprintf( "%02X", $letters[0] );
        return "other/$subdir";
    }
    return "other";
}

sub T {
    my ($text) = @_;

    if ( defined( $Translate{$text} ) && ( $Translate{$text} ne '' ) ) {
        return $Translate{$text};
    }
    return $text;
}

sub Ts {
    my ( $text, $string ) = @_;

    $text = T($text);
    $text =~ s/\%s/$string/;
    return $text;
}

sub Tss {
    my $text = $_[0];

    $text = T($text);
    $text =~ s/\%([1-9])/$_[$1]/ge;
    return $text;
}

# == Normal page-browsing and RecentChanges code =======================
$BrowseCode = "";    # Comment next line to always compile (slower)

#$BrowseCode = <<'#END_OF_BROWSE_CODE';
use CGI;
use CGI::Carp qw(fatalsToBrowser);

sub InitRequest {

    # SCRIPT_NAME is empty on CLI runs; default to '' to keep the
    # split call quiet under -w.
    my @ScriptPath = split( '/', ( $ENV{SCRIPT_NAME} // '' ) );

    $CGI::POST_MAX = $MaxPost;
    if ($PermUseUpload) {
        $CGI::DISABLE_UPLOADS = 0;    # allow uploads
    } else {
        $CGI::DISABLE_UPLOADS = 1;    # no uploads
    }
    $q = new CGI;

    # Fix some issues with editing UTF8 pages (if charset specified)
    if ( $HttpCharset ne '' ) {
        $q->charset($HttpCharset);
    }
    $ScriptName = pop(@ScriptPath);                 # Name used in links
    $ScriptName = '' unless defined $ScriptName;    # Empty SCRIPT_NAME under PSGI
    $IndexInit  = 0;                                # Must be reset for each request
    if ( !defined($InterSiteInit) ) {
        $InterSiteInit = 0;
        %InterSite     = ();
    }
    $MainPage     = ".";                     # For subpages only, the name of the top-level page
    $OpenPageName = "";                      # Currently open page
    $FullUrl      = &SelfUrl();

    if ( !-d $DataDir ) {
        &ReportError( Ts( 'Could not create %s', $DataDir ) . ": $!" );
        return 0;
    }
    &InitCookie();                           # Reads in user data
    &BuildNameSpaceRules();
    return 1;
}

sub InitCookie {
    my ($tmplang);
    %SetCookie      = ();
    $TimeZoneOffset = 0;
    undef $q->{'.cookies'};                  # Clear cache if it exists (for SpeedyCGI)
    %UserData   = ();                        # Fix for persistent environments.
    %UserCookie = ();
    my $rawcookie = $q->cookie($CookieName);
    $UserID = VerifySessionToken($rawcookie);

    if ( $UserID > 199 ) {
        &LoadUserDataDB($UserID);
        if ( $UserData{'id'} ne $UserID ) {
            $UserID   = 113;    # User row vanished
            %UserData = ();
        }
    } else {
        $UserID = 111;          # anonymous (signature failed, expired, or missing)
    }

    if ( defined $UserData{'tzoffset'} && $UserData{'tzoffset'} != 0 ) {
        $TimeZoneOffset = $UserData{'tzoffset'} * ( 60 * 60 );
    }
    if ( defined $UserData{'lang'} && $UserData{'lang'} ne "" ) {
        $LangID   = $UserData{'lang'};
        $LangFile = "$DataDir/i18n/lang.$LangID";
    }
    $tmplang = GetParam( 'lang', '' );
    if ( $tmplang ne '' ) {
        $LangFile = "$DataDir/i18n/lang.$tmplang";
    }
    if ( -f $LangFile ) {
        if ( !do $LangFile ) {    # Some error occurred
            $LangError = $@;
        }
    }
}

# Database table behind a data-path setting ($PageDir, $UserDir, $RcFile, ...):
# its last path component, after $DBTablePrefix.
sub DBTable {
    my ($path) = @_;
    return $DBTablePrefix . ( split( /\//, $path ) )[-1];
}

sub GetPageDB {
    my ($id) = @_;
    my $pref = ReadPagePermissions( $id, \%DBPrefix );
    if ( $pref ne "" ) {
        return $DBTablePrefix . $pref;
    } else {
        return DBTable($PageDir);
    }
}

sub PageExists {
    my ($id) = @_;
    return 1 if ( defined $BuildinPages{$id} );
    my $pagedb = &GetPageDB($id);
    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    my $data = ReadDBItems( $pagedb, 'id', '', '', "id=?", $id );
    if ( $data ne "" ) {
        return 1;
    }
    return 0;
}

sub DoBrowseRequest {
    my ( $id, $action, $text );

    if ( !$q->param ) {    # No parameter
        &BrowsePage($HomePage);
        return 1;
    }

    $action = lc( &GetParam( 'action', '' ) );    # used by both keywords + id paths
    $id     = &GetParam( 'keywords', '' );
    if ($id) {                                    # Just script?PageName
        if ( $FreeLinks && ( !PageExists($id) ) ) {
            $id = &FreeToNormal($id);
        }
        if ( ( $NotFoundPg ne '' ) && ( !PageExists($id) ) ) {
            $id = $NotFoundPg;
        }
        if ( $action eq 'discuss' ) {
            $id = $id . $DiscussSuffix;
        }
        &BrowsePage($id) if &ValidIdOrDie($id);
        return 1;
    }

    $id = &GetParam( 'id', '' );

    if ( $action eq 'browse' or $action eq 'discuss' ) {
        if ( $action eq 'discuss' ) {
            $id = $id . $DiscussSuffix;
        }
        if ( $FreeLinks && ( !PageExists($id) ) ) {
            $id = &FreeToNormal($id);
        }
        if ( ( $NotFoundPg ne '' ) && ( !PageExists($id) ) ) {
            $id = $NotFoundPg;
        }
        &BrowsePage($id) if &ValidIdOrDie($id);
        return 1;
    } elsif ( $action eq 'rc' ) {
        &BrowsePage($RCName);
        return 1;
    } elsif ( $action eq 'random' ) {
        &DoRandom();
        return 1;
    } elsif ( $action eq 'history' ) {
        &DoHistory($id) if &ValidIdOrDie($id);
        return 1;
    }
    return 0;    # Request not handled
}

sub BuildRuleStack {
    my ($id) = @_;
    my ( @dirs, $toptree, $fname, $ff, $dirname, $rules, $i, $j, $levelcount );
    my %rulefiles =
      ( 'v0' => 'preview', 'v1' => 'postview', 'e0' => 'preedit', 'e1' => 'postedit' );

    if ( $id =~ /\/\.[^\/]+$/ ) { return; }

    if ( defined( $Pages{$id}->{'rules'} ) ) {
        return;
    }
    $toptree = &GetPageDirectory($id);
    @dirs    = ( split( /\//, $toptree . "/" . $id ) );
    if ( @dirs < 1 ) { return; }

    $levelcount = ( $toptree =~ tr/\/// ) + 1;

    # Reset only the rule slots. Assigning the whole %{$Pages{$id}}
    # hash here would also wipe {'page'} / {'text'} / {'section'}
    # loaded by OpenPageDB -- notably {'page'}{'admin_saved'}, which
    # made WikiToHTML scrub raw HTML on every page.
    $Pages{$id}->{$_} = [] for qw(preview postview preedit postedit);
    $Pages{$id}->{'rules'} = 1;

    for ( $i = $levelcount ; $i < @dirs ; $i++ ) {
        $dirname = "";
        for ( $j = $levelcount ; $j <= $i ; $j++ ) {
            if   ( $j == $levelcount ) { $dirname .= $dirs[$j]; }
            else                       { $dirname .= "/" . $dirs[$j]; }
        }

        # Stage 6: cache rule-file content by ancestor directory. When
        # rendering multiple sibling pages in one request (nested
        # embeds, history view, etc.) the ancestors' rule files are
        # shared; doing 4 lookups per page × N pages × D depth is
        # wasteful. %RuleDirCache memoizes per-directory, reset in
        # ResetRequestState. Cache hit = zero DB / zero $TextCache work.
        my $cached = $RuleDirCache{$dirname};
        if ( !defined $cached ) {
            $cached = {};
            foreach my $f ( keys %rulefiles ) {
                $cached->{$f} = &ReadRawWikiPage( $dirname . "/.$f" );
            }
            $RuleDirCache{$dirname} = $cached;
        }

        foreach $ff ( keys %rulefiles ) {
            $rules = $cached->{$ff};
            if ( defined($rules) && $rules ne "" ) {
                if ( $rules =~ /=/ ) {
                    $Pages{$id}->{'clearance'} = max( $Pages{$id}->{'clearance'}, 100 )
                      if ( $rules =~ /\bADMIN=1\b/ );
                    $Pages{$id}->{'clearance'} = max( $Pages{$id}->{'clearance'}, 50 )
                      if ( $rules =~ /\bEDITOR=1\b/ );
                    $Pages{$id}->{'clearance'} = max( $Pages{$id}->{'clearance'}, 200 )
                      if ( $rules =~ /\bPRIVATE=1\b/ );
                    $Pages{$id}->{'writeonly'} = 1 if ( $rules =~ /\bWRITEONLY=1\b/ );
                    if ( $rules =~ /\bALLOW=([0-9.]+)\b/ ) {
                        $Pages{$id}->{'clearance'} = max( $Pages{$id}->{'clearance'}, $1 );
                    }
                    if ( $rules =~ /\bEXPIRE=\s*(.*)\b/ ) {
                        $Pages{$id}->{'expire'} = $1;
                    }
                }
                push( @{ $Pages{$id}->{ $rulefiles{$ff} } }, $rules );
            }
        }
    }
}

sub OpenDefaultPage {
    my ($id) = @_;
    my ($inlinerev);
    if ( defined( $Pages{$id}->{'text'}->{'text'} ) ) {
        return;
    }
    &OpenPageDB($id);

    ( $Pages{$id}->{'text'}->{'text'}, $inlinerev ) =
      &PatchPage( $Pages{$id}->{'text'}->{'text'} );
}

sub PatchPage {
    my ( $text, $inlinerev ) = @_;
    if ( $text =~ /$FS4/ ) {
        my @patches  = split( /$FS4/, $text );
        my $basetext = $patches[0];

        #my $basesec=$Pages{$OpenPageName}->{'section'}->{'revision'};
        if ( $inlinerev ne '' && $inlinerev < $#patches ) {
            splice( @patches, $inlinerev + 1, $#patches - $inlinerev );
        }
        for ( my $i = 1 ; $i < @patches ; $i++ ) {
            if ( $patches[$i] =~ /$FS5$/ ) { next; }
            if ( $patches[$i] =~ /$FS5/ ) {
                $patches[$i] = ( split( /$FS5/, $patches[$i] ) )[-1];
            }
            if ( $patches[$i] ne "" ) {
                $basetext = PatchText( $basetext, $patches[$i], 0 );

                #$Pages{$OpenPageName}->{'section'}->{'revision'}=$basesec+$i;
            }
        }
        $text = $basetext;
        return ( $text, $#patches );
    }
    return $text;
}

sub BrowsePage {
    my ($id) = @_;
    my ( $fullHtml, $oldId,        $allDiff,      $showDiff, $openKept, $extviewer );
    my ( $revision, $goodRevision, $diffRevision, $newText,  $kfid,     $kid, $kstr, $inlinerev );
    my ( $tmpstr,   $Page,         $Text,         $fullrev );
    my $contentlen;
    my $pagehtml;
    my @vv;
    my $pagelogdb = DBTable($PageLog);

    # Static cache: remember the cache generation before rendering, so a
    # purge that happens while we render prevents writing a stale copy.
    $StaticCacheGen = &StaticCacheGeneration();

    $extviewer = ReadPagePermissions( $id, \%ExtViewer );
    $StaticCacheOK = 0 if ( $extviewer ne '' );    # computed or redirected content
    if ( $extviewer ne '' ) {
        if ( ref($extviewer) ne "CODE" ) {
            &ReBrowsePage( "$extviewer#$id", "", 0 );
            return;
        }
    }
    if ( $UserID >= 1000 ) {
        AddUserLogDB( $UserID, 'Br', $id );
    }
    &OpenDefaultPage($id);

    $openKept  = 0;
    $inlinerev = '';
    $revision  = &GetParam( 'revision', '' );
    if ( $revision =~ /(\d+)\.(\d+)/ ) {
        $revision  = $1;
        $inlinerev = $2;
    }
    $fullrev = ( $inlinerev eq '' ? $revision : "$revision.$inlinerev" );
    $revision =~ s/\D//g;         # Remove non-numeric chars
    $goodRevision = $revision;    # Non-blank only if exists
    if ( $revision ne '' ) {
        &OpenKeptRevisions( $id, 'text_default', $inlinerev ne '' && $inlinerev >= 0 );
        $openKept = 1;
        if ( !defined( $KeptRevisions{$revision} ) ) {
            $goodRevision = '';
        } else {
            &OpenKeptRevision( $id, $revision, $inlinerev );
        }
    }
    $Page = \%{ $Pages{$id}->{'page'} };
    $Text = \%{ $Pages{$id}->{'text'} };

    # build-in pages are only used for browsing
    if (   defined $$Text{'isnew'}
        && defined $BuildinPages{$id}
        && $BuildinPages{$id} ne '' )
    {
        $$Text{'text'} = $BuildinPages{$id};
    }

    # Raw mode: just untranslated wiki text
    if ( &GetParam( 'raw', 0 ) || &GetParam( 'format', '' ) eq 'json' ) {
        &BuildRuleStack($id);
        my $pp = ReadPagePermissions( $id, \%Permissions );
        if (
            (
                defined( $Pages{$id}->{'clearance'} )
                && &UserPermission() < $Pages{$id}->{'clearance'}
            )
            || ( ( $pp ne '' ) && &UserPermission() < $pp )
          )
        {
            return "";
        }
        print &GetHttpHeader( 'text/plain', $Pages{$id}->{'expire'} );
        if ( &GetParam( 'raw', 0 ) ) {
            print $$Text{'text'};
        } else {
            print JSONFormat( $id, $$Text{'text'}, &GetParam( 'jsoncallback', '' ) );
        }
        return;
    }
    if ( $extviewer ne '' ) {
        if ( ref($extviewer) eq "CODE" ) {
            $$Text{'text'} = $extviewer->( $id, $$Text{'text'} );
        }
    }
    $newText = $$Text{'text'};    # For differences

    # pages with embeded subpages can not usecache
    if ( $newText =~ /\{\{($FreeLinkPattern)(::($FreeLinkPattern)){0,1}(\|(.*)){0,1}\}\}/ ) {
        $UseCache = 0;
    }

    if ( $newText =~ /\{\(($FreeLinkPattern)(::($FreeLinkPattern)){0,1}(\|(.*)){0,1}\)\}/ ) {
        $UseCache = 0;
    }

    if ( $newText =~ /\{\(($FreeLinkPattern)(::($FreeLinkPattern)){0,1}((.*))\)\}/ ) {
        $UseCache = 0;
    }

    # Handle a single-level redirect
    $oldId = &GetParam( 'oldid', '' );
    if ( ( $oldId eq '' ) && ( substr( $$Text{'text'}, 0, 10 ) eq '#REDIRECT ' ) ) {
        $oldId = $id;
        if ( ($FreeLinks) && ( $$Text{'text'} =~ /\#REDIRECT\s+\[\[.+\]\]/ ) ) {
            ($id) = ( $$Text{'text'} =~ /\#REDIRECT\s+\[\[(.+)\]\]/ );
            $id = &FreeToNormal($id);
        } else {
            ($id) = ( $$Text{'text'} =~ /\#REDIRECT\s+(\S+)/ );
        }
        if ( &ValidId($id) eq '' ) {

            # Consider revision in rebrowse?
            &ReBrowsePage( $id, $oldId, 0 );
            return;
        } else {    # Not a valid target, so continue as normal page
            $id    = $oldId;
            $oldId = '';
        }
    }
    $MainPage = $id;
    $MainPage =~ s|/.*||;    # Only the main page name (remove subpage)
    $fullHtml = &GetHeader( $id, &QuoteHtml($id), $oldId );
    if ( $revision ne '' ) {
        if ( ( $revision eq $$Page{'revision'} ) || ( $goodRevision ne '' ) ) {
            $fullHtml .=
              '<div class="wikiinfo">' . Ts( 'Showing revision %s', $fullrev ) . "</div>";
        } else {
            $fullHtml .=
                '<div class="wikiinfo">'
              . Ts( 'Revision %s not available', $revision ) . ' ('
              . T('showing current revision instead')
              . ')</div>';
        }
    }
    $allDiff = &GetParam( 'alldiff', 0 );
    if ( $allDiff != 0 ) {
        $allDiff = &GetParam( 'defaultdiff', 1 );
    }
    if ( ( ( $id eq $RCName ) || ( T($RCName) eq $id ) || ( T($id) eq $RCName ) )
        && &GetParam( 'norcdiff', 1 ) )
    {
        $allDiff = 0;    # Only show if specifically requested
        if ( defined $$Text{'isnew'} ) {
            $$Text{'text'} = '';
        }
    }
    $showDiff = &GetParam( 'diff', $allDiff );
    if ( $UseDiff && $showDiff ) {
        $diffRevision = $goodRevision;
        $diffRevision = &GetParam( 'diffrevision', $diffRevision );

        # Eventually try to avoid the following keep-loading if possible?
        &OpenKeptRevisions( $id, 'text_default', 1 ) if ( !$openKept );
        $fullHtml .= &GetDiffHTML( $showDiff, $id, $diffRevision, $fullrev, $newText );
    }
    $Page = \%{ $Pages{$id}->{'page'} };
    $Text = \%{ $Pages{$id}->{'text'} };

    if ( &GetParam( 'diff', '' ) eq '' ) {
        $fullHtml .= '<div class="wikitext">';
    }
    $kfid = &GetParam( "keyfield", "" );
    $kid  = &GetParam( "keyblock", "" );
    $kstr = &GetParam( "keyval",   "" );

    if ( $kfid ne "" && $kid ne "" && $kstr ne "" ) {
        @vv = split( /(<\/$kid>)/, $$Text{'text'} );
        for ( my $i = 0 ; $i < @vv ; $i++ ) {
            if ( $vv[$i] =~ /$kstr\s*<\/$kfid>/ ) {
                $$Text{'text'} = $vv[$i] . "\n</$kid>";
                $UseCache = 0;
                $StaticCacheOK = 0;
                last;
            }
        }
    }
    if ( not( $id =~ /\/\.[^\/]+$/ ) ) {
        $pagehtml = &WikiToHTML( $id, $$Text{'text'} );
    } else {
        $pagehtml = "<textarea cols=100 rows=25 readonly=1>" . $$Text{'text'} . "</textarea>";
    }
    if ( &GetParam( 'diff', '' ) eq '' ) {
        $fullHtml .= $pagehtml;
    }
    $fullHtml .= '</div>';
    if ( ( $id eq $RCName ) || ( T($RCName) eq $id ) || ( T($id) eq $RCName ) ) {
        print $fullHtml;
        print '<div class="wikirc">';
        &DoRc(1);
        print '</div>';
        print &GetFooterText( $id, $goodRevision );
        return;
    }
    $fullHtml .= &GetFooterText( $id, $goodRevision );

    print $fullHtml;
    if ( $pagelogdb ne "" ) {
        UpdatePageLogDB( $pagelogdb, $id );
    }
    return
      if ( $showDiff || ( $revision ne '' ) || &GetParam( "embed", "" ) ne "" )
      ;    # Don't cache special version

    my $exportfile = ReadPagePermissions( $id, \%ExportPage );
    if ( $exportfile ne '' ) {
        $exportfile .= "${id}.html" if ( $exportfile =~ /\/$/ );
        my $exportpath = $exportfile;
        $exportpath = $1 if ( $exportpath =~ m#^(.*?)([^/]*)$# );
        &CreateDir($exportpath);
        my $saveHtml = $fullHtml;
        $saveHtml =~ s/.*<\!DOCTYPE/<!DOCTYPE/gs;
        &WriteStringToFile( $exportfile, $saveHtml );
    }

    # Stage 6: only cache when the rendered HTML is the anonymous view.
    # The page includes per-user elements (admin bar / user toolbar /
    # login link) that would otherwise leak admin content to non-admins
    # on cache hit. UserID 111 is the wiki's bare-anonymous sentinel
    # (set in InitCookie when no session token is present).
    if ( $UseCache && $oldId eq '' && $UserID == 111 ) {
        &UpdateHtmlCacheDB( $id, $fullHtml );
    }

    # Static page cache (no-op unless $StaticCacheDir is set; it checks
    # that this is exactly the anonymous request the rewrite serves).
    &WriteStaticCache( $id, $fullHtml ) if ( $oldId eq '' );
}

sub ReBrowsePage {
    my ( $id, $oldId, $isEdit ) = @_;

    if ( $oldId ne "" ) {    # Target of #REDIRECT (loop breaking)
        print &GetRedirectPage( "action=browse&id=$id&oldid=$oldId", $id, $isEdit );
    } else {
        print &GetRedirectPage( $id, $id, $isEdit );
    }
}

sub ReadRCLogDB {
    my ($stime) = @_;
    my ( $sth, $rclogdb );
    my (
        $ts,   $pagename, $summary,    $isEdit,    $host,
        $kind, $uid,      $name,       $rev,       $admin,
        $lim,  $offset,   $moretocome, $searchcmd, $mintime
    );
    my @fullrc = ();
    my %extra;

    $lim = GetParam( 'listc', $RCHistoryLimit ) + 1;

    # 0x7fffffff (~2038-01-19 in unix-time) is the max value the
    # `time integer` column accepts on Postgres; 1e10 (~2286) used to
    # be the "unbounded future" sentinel under SQLite where INTEGER is
    # 64-bit. Clamp to Pg's INT4 limit so the query binds cleanly on
    # both dialects.
    $offset = GetParam( 'offset', 0x7fffffff );

    $rclogdb = DBTable($RcFile);
    if ( $dbh eq "" || $rclogdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("ReadRCLogDB: unsafe table name") if ( !SafeIdent($rclogdb) );
    $stime  = int($stime);
    $offset = int($offset);
    $offset = 0x7fffffff if ( $offset > 0x7fffffff );
    $lim    = int($lim);

    # `LIMIT off, count` is SQLite/MySQL syntax; Postgres requires
    # `LIMIT count OFFSET off`. Both dialects accept the LIMIT-then-
    # OFFSET form below.
    if ( $offset > 0 ) {
        $searchcmd = "select * from $rclogdb where time>? and time<? order by time desc limit $lim";
        $sth       = $dbh->selectall_arrayref( $searchcmd, undef, $stime, $offset );
    } else {
        $searchcmd = "select * from $rclogdb where time>? order by time desc limit $lim";
        $sth       = $dbh->selectall_arrayref( $searchcmd, undef, $stime );
    }
    $mintime = 1e10;
    if ( defined $sth->[0] ) {
        if ( @{$sth} > $RCHistoryLimit ) {
            pop( @{$sth} );
            $moretocome = "+";
        }
        foreach my $rec (@$sth) {
            ( $ts, $pagename, $summary, $isEdit, $host, $kind, $uid, $name, $rev, $admin ) =
              @{$rec};
            if ( $ts ne "" ) {

                # Stage 5: push a hashref per RC entry instead of
                # FS3/FS2-joined strings. All downstream consumers
                # (DoRc / GetRcHtml / GetHtmlRcLine / GetRcRss /
                # GetRssRcLine) handle both shapes; once the in-memory
                # round-trip is hashref-only, the FS-byte path drops out.
                push @fullrc,
                  {
                    ts       => $ts,
                    pagename => $pagename,
                    summary  => $summary,
                    isEdit   => $isEdit,
                    host     => $host,
                    kind     => $kind,
                    id       => $uid,
                    revision => $rev,
                    name     => $name,
                    admin    => $admin,
                  };
                $mintime = $ts if ( $ts < $mintime );
            }
        }
    }
    if ( $mintime > 0 ) {
        $moretocome = '' if ( !defined($moretocome) );
        return ( "Internal:Offset:$mintime$moretocome", reverse(@fullrc) );
    } else {
        return reverse(@fullrc);
    }
}

sub DoRc {
    my ($rcType) = @_;    # 0 = RSS, 1 = HTML
    my ( $fileData, $rcline, $i, $daysago, $lastTs, $ts, $idOnly, $offs, $moretocome );
    my ( @fullrc, $status, $oldFileData, $firstTs, $errorText, $showHTML );
    my $starttime = 0;
    my $showbar   = 0;

    if ( 0 == $rcType ) {
        $showHTML = 0;
    } else {
        $showHTML = 1;
    }
    if ( &GetParam( "from", 0 ) ) {
        $starttime = &GetParam( "from", 0 );
        if ($showHTML) {
            print "<h2>" . Ts( 'Updates since %s', &TimeToText($starttime) ) . "</h2>\n";
        }
    } else {
        $daysago = &GetParam( "days",   0 );
        $daysago = &GetParam( "rcdays", 0 ) if ( $daysago == 0 );
        if ($daysago) {
            $starttime = $Now - ( ( 24 * 60 * 60 ) * $daysago );
            if ($showHTML) {
                print "<h2>"
                  . Ts( 'Updates in the last %s day' . ( ( $daysago != 1 ) ? "s" : "" ), $daysago )
                  . "</h2>\n";
            }

# Note: must have two translations (for "day" and "days") Following comment line is for translation helper
# script Ts('Updates in the last %s days', '');
        }
    }
    if ( $starttime == 0 ) {
        if ( 0 == $rcType ) {
            $starttime = $Now - ( ( 24 * 60 * 60 ) * $RssDays );
        } else {
            $starttime = $Now - ( ( 24 * 60 * 60 ) * $RcDefault );
        }
        if ($showHTML) {
            print "<h2>"
              . Ts( 'Updates in the last %s day' . ( ( $RcDefault != 1 ) ? "s" : "" ), $RcDefault )
              . "</h2>\n";
        }

        # Translation of above line is identical to previous version
    }

    # Read rclog data (and oldrclog data if needed)
    @fullrc = &ReadRCLogDB($starttime);
    if (   @fullrc > 0
        && !ref( $fullrc[0] )
        && $fullrc[0] =~ /^Internal:Offset:([0-9]+)([+]*)/ )
    {
        $offs       = $1;
        $moretocome = $2;
        shift(@fullrc);
    }
    $lastTs = 0;
    if ( @fullrc > 0 ) {    # Only false if no lines in file
                            # Stage 5: rows are hashrefs from ReadRCLogDB.
        my $last = $fullrc[$#fullrc];
        $lastTs = ref($last) eq 'HASH' ? $last->{ts} : ( split( /$FS3/, $last ) )[0];
    }
    $lastTs++ if ( ( $Now - $lastTs ) > 5 );    # Skip last unless very recent

    if ( 0 == $rcType ) {
        print &GetRcRss(@fullrc);
    } else {
        if ($showHTML) {
            foreach $i (@RcDays) {
                print " | " if $showbar;
                $showbar = 1;
                print &ScriptLink( "action=rc&days=$i",
                    Ts( '%s day' . ( ( $i != 1 ) ? 's' : '' ), $i ) );

                # Note: must have two translations (for "day" and "days")
                # Following comment line is for translation helper script
                # Ts('%s days', '');
            }
            print "<br>"
              . &ScriptLink( "action=rc&from=$lastTs", T('List new changes starting from') );
            print " " . &TimeToText($lastTs) . "<br>\n";
        }
        print &GetRcHtml(@fullrc);
        if ( $offs ne '' ) {
            my $url;
            print "<div class='wikipager'>";
            if ( $moretocome ne '' ) {
                if ( $offs >= $RCHistoryLimit ) {
                    print "&nbsp;&nbsp;";
                }
                $url = "action=rc&days=$daysago&offset=" . $offs;
                print &ScriptLink( $url, Ts( 'Next %s', $RCHistoryLimit ) . "&raquo;" );
            }
            print "</div>";
        }
    }
    if ($showHTML) {
        print '<p>' . Ts( 'Page generated %s', &TimeToText($Now) ), "<br>\n";
    }
    return;
}

sub GetRc {
    my $rcType = shift;
    my @outrc  = @_;
    my ( $rcline,       $date,          $newtop,   $author, $inlist,   $result );
    my ( $showedit,     $link,          $all,      $idOnly, $headItem, $item );
    my ( $ts,           $pagename,      $summary,  $isEdit, $host,     $kind, $extraTemp );
    my ( $rcchangehist, $tEdit,         $tChanges, $tDiff );
    my ( $headList,     $historyPrefix, $diffPrefix );
    my %extra      = ();
    my %changetime = ();
    my %pagecount  = ();

    # Slice minor edits. Each rcline is a hashref (Stage 5).
    $showedit = &GetParam( "rcshowedit", $ShowEdits );
    $showedit = &GetParam( "showedit",   $showedit );
    if ( $showedit != 1 ) {
        my @temprc = ();
        foreach $rcline (@outrc) {
            my $is =
              ref($rcline) eq 'HASH'
              ? $rcline->{isEdit}
              : ( split( /$FS3/, $rcline ) )[3];
            if ( $showedit == 0 ) {    # 0 = No edits
                push( @temprc, $rcline ) if ( $is != 1 );
            } else {                   # 2 = Only edits
                push( @temprc, $rcline ) if ($is);
            }
        }
        @outrc = @temprc;
    }

    # Optimize param fetches out of main loop
    $rcchangehist = &GetParam( "rcchangehist", 1 );

    # Optimize translations out of main loop
    $tEdit    = T('(edit)');
    $tDiff    = T('(diff)');
    $tChanges = T('changes');

    # $QuotedFullUrl is initialized lazily by GetRcRss (RSS code path).
    # The HTML path doesn't go through there, so fall back to FullUrl.
    my $base =
      defined($QuotedFullUrl) && $QuotedFullUrl ne ''
      ? $QuotedFullUrl
      : &QuoteHtml( $FullUrl // '' );
    $diffPrefix    = $base . &QuoteHtml("?action=browse\&diff=4\&id=");
    $historyPrefix = $base . &QuoteHtml("?action=history\&id=");
    foreach $rcline (@outrc) {
        if ( ref($rcline) eq 'HASH' ) {
            ( $ts, $pagename ) = @{$rcline}{qw(ts pagename)};
        } else {
            ( $ts, $pagename ) = split( /$FS3/, $rcline );
        }
        $pagecount{$pagename}++;
        $changetime{$pagename} = $ts;
    }
    $date     = "";
    $all      = &GetParam( "rcall",    0 );
    $all      = &GetParam( "all",      $all );
    $newtop   = &GetParam( "rcnewtop", $RecentTop );
    $newtop   = &GetParam( "newtop",   $newtop );
    $idOnly   = &GetParam( "rcidonly", "" );
    $inlist   = 0;
    $headList = '';
    $result   = '';
    @outrc    = reverse @outrc if ($newtop);

    foreach $rcline (@outrc) {
        if ( ref($rcline) eq 'HASH' ) {
            ( $ts, $pagename, $summary, $isEdit, $host, $kind ) =
              @{$rcline}{qw(ts pagename summary isEdit host kind)};
            %extra = ();
            $extra{$_} = $rcline->{$_} for (qw(id revision name admin));
        } else {
            my $extraTemp;
            ( $ts, $pagename, $summary, $isEdit, $host, $kind, $extraTemp ) =
              split( /$FS3/, $rcline );
            %extra = split( /$FS2/, $extraTemp, -1 );
        }
        next if ( ( !$all )         && ( $ts < $changetime{$pagename} ) );
        next if ( ( $idOnly ne "" ) && ( $idOnly ne $pagename ) );
        next if ( $extra{'admin'}   && ( &UserPermission() < $extra{'admin'} ) );
        if ( $date ne &CalcDay($ts) ) {
            $date = &CalcDay($ts);
            if ( 1 == $rcType ) {    # HTML
                                     # add date, properly closing lists first
                if ($inlist) {
                    $result .= "</UL>\n";
                    $inlist = 0;
                }
                $result .= "<p><strong>" . $date . "</strong></p>\n";
                if ( !$inlist ) {
                    $result .= "<ul>\n";
                    $inlist = 1;
                }
            }
        }
        if ( 0 == $rcType ) {    # RSS
            ( $headItem, $item ) = &GetRssRcLine(
                $pagename,      $ts,                   $host,
                $extra{'name'}, $extra{'id'},          $summary,
                $isEdit,        $pagecount{$pagename}, $extra{'revision'},
                $diffPrefix,    $historyPrefix
            );
            $headList .= $headItem;
            $result   .= $item . $extra{'admin'};
        } else {                 # HTML
            $result .=
              &GetHtmlRcLine( $pagename, $ts, $host, $extra{'name'},
                $extra{'id'}, $summary, $isEdit,   $pagecount{$pagename}, $extra{'revision'},
                $tEdit,       $tDiff,   $tChanges, $all,                  $rcchangehist );
            if ( $extra{'admin'} > 0 ) {
                $result .= $extra{'admin'};
            }
        }
    }
    if ( 1 == $rcType ) {
        $result .= "</ul>\n" if ($inlist);    # Close final tag
    }
    return ( $headList, $result );            # Just ignore headList for HTML
}

sub GetRcHtml {
    my ( $html, $extra );

    ( $extra, $html ) = &GetRc( 1, @_ );
    return $html;
}

sub GetHtmlRcLine {
    my (
        $pagename, $timestamp, $host,      $userName, $userID,
        $summary,  $isEdit,    $pagecount, $revision, $tEdit,
        $tDiff,    $tChanges,  $all,       $rcchangehist
    ) = @_;
    my ( $author, $sum, $edit, $count, $link, $html );

    $html = '';
    $host = &QuoteHtml($host);
    if ( defined($userName) && defined($userID) ) {
        $author = &GetAuthorLink( $host, $userName, $userID );
    } else {
        $author = &GetAuthorLink( $host, "", 0 );
    }
    $sum = "";
    if ( ( $summary ne "" ) && ( $summary ne "*" ) ) {
        $summary = &QuoteHtml($summary);
        $sum     = "<strong>[$summary]</strong> ";
    }
    $edit  = "";
    $edit  = "<em>$tEdit</em> "               if ( $isEdit == 1 );
    $edit  = "<em>" . T('deleted') . "</em> " if ( $isEdit == 2 );
    $count = "";
    if ( ( !$all ) && ( $pagecount > 1 ) ) {
        $count = "($pagecount ";
        if ($rcchangehist) {
            $count .= &GetHistoryLink( $pagename, $tChanges );
        } else {
            $count .= $tChanges;
        }
        $count .= ") ";
    }
    $link = "";
    if ( $UseDiff && &GetParam( "diffrclink", 1 ) ) {
        $link .= &ScriptLinkDiff( 4, $pagename, $tDiff, "" ) . " ";
    }
    $link .= &GetPageLink($pagename);
    $html .= "<li>$link ";
    $html .= &CalcTime($timestamp) . " $count$edit" . " $sum";
    $html .= ". . . . . $author\n";
    return $html;
}

sub GetRcRss {
    my ( $rssHeader, $headList, $items );

    # Normally get URL from script, but allow override
    $FullUrl         = &SelfUrl() if ( $FullUrl eq "" );
    $QuotedFullUrl   = &QuoteHtml($FullUrl);
    $SiteDescription = &QuoteHtml($SiteDescription);

    my $ChannelAbout = &QuoteHtml( $FullUrl . &ScriptLinkChar() . $ENV{QUERY_STRING} );
    $rssHeader = <<RSS ;
<?xml version="1.0" encoding="$HttpCharset"?>
<rdf:RDF
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns="http://purl.org/rss/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:wiki="http://purl.org/rss/1.0/modules/wiki/"
>
    <channel rdf:about="$ChannelAbout">
        <title>${\(&QuoteHtml($SiteName))}</title>
        <link>${\($QuotedFullUrl . &QuoteHtml("?$RCName"))}</link>
        <description>${\(&QuoteHtml($SiteDescription))}</description>
        <wiki:interwiki>
            <rdf:Description link="$QuotedFullUrl">
                <rdf:value>$InterWikiMoniker</rdf:value>
            </rdf:Description>
        </wiki:interwiki>
        <items>
            <rdf:Seq>
RSS
    ( $headList, $items ) = &GetRc( 0, @_ );
    $rssHeader .= $headList;
    return <<RSS ;
$rssHeader
            </rdf:Seq>
        </items>
    </channel>
    <image rdf:about="${\(&QuoteHtml($RssLogoUrl))}">
        <title>${\(&QuoteHtml($SiteName))}</title>
        <url>$RssLogoUrl</url>
        <link>$QuotedFullUrl</link>
    </image>
$items
</rdf:RDF>
RSS
}

sub GetRssRcLine {
    my (
        $pagename, $timestamp, $host,     $userName,   $userID, $summary,
        $isEdit,   $pagecount, $revision, $diffPrefix, $historyPrefix
    ) = @_;
    my (
        $itemID,     $description, $authorLink, $author,   $status,
        $importance, $date,        $item,       $headItem, $encodedpage
    );

    $encodedpage = UrlEncode($pagename);

    # Add to list of items in the <channel/>
    $itemID =
      $FullUrl . &ScriptLinkChar() . &GetOldPageParameters( 'browse', $encodedpage, $revision );
    $itemID   = &QuoteHtml($itemID);
    $headItem = " <rdf:li rdf:resource=\"$itemID\"/>\n";

    # Add to list of items proper.
    if ( ( $summary ne "" ) && ( $summary ne "*" ) ) {
        $description = &QuoteHtml($summary);
    }
    $host = &QuoteHtml($host);
    if ($userName) {
        $author     = &QuoteHtml($userName);
        $authorLink = "link=\"$QuotedFullUrl?$author\"";
    } else {
        $author = $host;
    }
    $status     = ( 1 == $revision ) ? 'new'   : 'updated';
    $importance = $isEdit            ? 'minor' : 'major';
    $timestamp += $TimeZoneOffset;
    my ( $sec, $min, $hour, $mday, $mon, $year ) = localtime($timestamp);
    $year += 1900;
    $date = sprintf( "%4d-%02d-%02dT%02d:%02d:%02d+%02d:00",
        $year, $mon + 1, $mday, $hour, $min, $sec, $TimeZoneOffset / ( 60 * 60 ) );
    $pagename = &QuoteHtml($pagename);

    # Write it out longhand

    $item = <<RSS ;
    <item rdf:about="$itemID">
        <title>$pagename</title>
        <link>$QuotedFullUrl?$encodedpage</link>
        <description>$description</description>
        <dc:date>$date</dc:date>
        <dc:contributor>
            <rdf:Description wiki:host="$host" $authorLink>
                <rdf:value>$author</rdf:value>
            </rdf:Description>
        </dc:contributor>
        <wiki:status>$status</wiki:status>
        <wiki:importance>$importance</wiki:importance>
        <wiki:diff>$diffPrefix$encodedpage</wiki:diff>
        <wiki:version>$revision</wiki:version>
        <wiki:history>$historyPrefix$encodedpage</wiki:history>
    </item>
RSS
    return ( $headItem, $item );
}

sub DoRss {
    print "Content-type: text/xml\n\n";
    &DoRc(0);
}

sub DoRandom {
    my ( $id, @pageList );

    @pageList = &AllPagesList();                              # Optimize?
    $id       = $pageList[ int( rand( $#pageList + 1 ) ) ];
    &ReBrowsePage( $id, "", 0 );
}

sub DoHistory {
    my ($id) = @_;
    my ( $html, $canEdit, $row, $newText, $offs, $moretocome );

    &BuildRuleStack($id);
    print &GetHeader( '', Ts( 'History of %s', $id ), '' );
    my $pp = ReadPagePermissions( $id, \%Permissions );
    if ( ( defined( $Pages{$id}->{'clearance'} ) && &UserPermission() < $Pages{$id}->{'clearance'} )
        || ( ( $pp ne '' ) && &UserPermission() < $pp )
        || ( &UserPermission() != 100 && $Pages{$id}->{'writeonly'} == 1 ) )
    {
        print "<div class=\"wikiinfo\">no permission</div>\n";
        print &GetCommonFooter();
        return;
    }
    &OpenDefaultPage($id);

    $newText = $Pages{$id}->{'text'}->{'text'};
    $canEdit = 0;
    $canEdit = &UserCanEdit($id) if ($HistoryEdit);
    if ($UseDiff) {
        print <<EOF ;
      <div class="wikieditform">
      <form action='$ScriptName' METHOD='GET'>
          <input type='hidden' name='action' value='browse'/>
          <input type='hidden' name='diff' value='1'/>
          <input type='hidden' name='id' value='$id'/>
      <table border='0' width='100%'><tr>
EOF
    }
    $html = "";
    $html = &GetHistoryLine( $id, $Pages{$id}->{'page'}->{'text_default'}, $canEdit, $row++ );
    &OpenKeptRevisions( $id, 'text_default', 1 );

    foreach ( reverse sort { $a <=> $b } keys %KeptRevisions ) {
        next if ( $_ eq "" );             # (needed?)
        next if ( $_ =~ /^Internal:/ );
        $html .= &GetHistoryLine( $id, $KeptRevisions{$_}, $canEdit, $row++ );
    }
    print $html;
    if ( $KeptRevisions{"Internal:Offset"} =~ /^([0-9]+)([+]*)$/ ) {
        $offs       = $1;
        $moretocome = $2;
    }
    if ( $offs ne '' ) {
        my $url;
        print "<div class='wikipager'>";
        print "<input type='hidden' name='offset' value='$offs'/>" if ( $offs > 0 );
        if ( $offs >= $HistoryLimit ) {
            $url = "action=history&id=$id&offset=" . ( $offs - $HistoryLimit );
            print &ScriptLink( $url, "&laquo;" . Ts( 'Previous %s pages', $HistoryLimit ) );
        }
        if ( $moretocome ne '' ) {
            if ( $offs >= $HistoryLimit ) {
                print "&nbsp;&nbsp;";
            }
            $url = "action=history&id=$id&offset=" . ( $offs + $HistoryLimit );
            print &ScriptLink( $url, Ts( 'Next %s pages', $HistoryLimit ) . "&raquo;" );
        }
        print "</div>";
    }
    if ($UseDiff) {
        my $label = T('Compare');
        print "<tr><td><input type='submit' " . "value='$label'/>&nbsp;&nbsp;</td></tr>"
          if $html ne "";
        print "</table></form>\n";
        print &GetDiffHTML( &GetParam( 'defaultdiff', 1 ), $id, '', '', $newText );
    }
    print "</div>";
    print &GetCommonFooter();
}

sub GetMaskedHost {
    my ($text) = @_;
    my ($logText);

    if ( !$MaskHosts ) {
        return $text;
    }
    $logText = T('(logged)');
    if ( !( $text =~ s/\d+$/$logText/ ) ) {    # IP address (ending numbers masked)
        $text =~ s/^[^\.\(]+/$logText/;        # Host name: mask until first .
    }
    return $text;
}

sub GetHistoryLine {
    my ( $id, $section, $canEdit, $row ) = @_;
    my (
        $html,   $expirets, $rev,   $summary, $host,  $user,  $uid,      $ts, $minor,
        $subver, $allver,   $revid, $pts,     $puser, $phost, $psummary, $puid
    );
    my ( %sect, %revtext, @textpatch );

    # Stage 5: callers now pass a hashref (was: FS2-joined string).
    # Fall back to the legacy split for any caller still passing a
    # raw string (e.g. an external integration loading kept data).
    if ( ref($section) eq 'HASH' ) {
        %sect = %$section;
        if ( ref( $sect{'data'} ) eq 'HASH' ) {
            %revtext = %{ $sect{'data'} };
        } elsif ( defined $sect{'data'} ) {
            %revtext = split( /$FS3/, $sect{'data'}, -1 );
        }
    } else {
        %sect    = split( /$FS2/, $section,      -1 );
        %revtext = split( /$FS3/, $sect{'data'}, -1 );
    }
    @textpatch = split( /$FS4/, $revtext{'text'} ) if defined $revtext{'text'};

    $rev = $sect{'revision'};
    if ( $rev == 0 ) { return ""; }

    $summary = $revtext{'summary'};
    if ( ( defined( $sect{'host'} ) ) && ( $sect{'host'} ne '' ) ) {
        $host = $sect{'host'};
    } else {
        $host = $sect{'ip'};
    }
    $user     = $sect{'username'};
    $uid      = $sect{'id'};
    $ts       = $sect{'ts'};
    $minor    = '';
    $minor    = '<i>' . T('(edit)') . '</i> ' if ( $revtext{'minor'} );
    $host     = &GetMaskedHost($host);
    $expirets = $Now - ( $KeepDays * 24 * 60 * 60 );

    #$subver=$sect{'inlinerev'};
    $subver = $#textpatch;
    $allver = 1;
    $allver = $subver + 1 if ( $subver > 0 );
    for ( my $i = $allver - 1 ; $i >= 0 ; $i-- ) {
        if ( defined( $textpatch[$i] ) ) {
            if ( $textpatch[$i] =~ /^(.*)$FS5/ ) {
                ( $pts, $puser, $phost, $psummary ) = split( /\|/, $1 );
            }
        }
        $revid = ( $i == $allver - 1 ? $rev : "$rev." . $i );
        if ($UseDiff) {
            my ( $c1, $c2 );
            $c1 = 'checked="checked"' if 1 == $row && $i == $allver - 1;
            $c2 = 'checked="checked"' if 0 == $row && $i == $allver - 1;
            $html .= "<tr><td><input type='radio' " . "name='diffrevision' value='$revid' $c1/> ";
            $html .= "<input type='radio' name='revision' value='$revid' $c2/></td><td>";
        }
        if ( 0 == $row && $i == $allver - 1 ) {    # current revision
            $html .= &GetPageLinkText( $id, Ts( 'Revision %s', $revid ) ) . ' ';

            if ($canEdit) {
                $html .= &GetEditLink( $id, T('(edit)') ) . ' ';
            }
        } else {
            $html .= &GetOldPageLink( 'browse', $id, $revid, Ts( 'Revision %s', $revid ) ) . ' ';
            if ($canEdit) {
                $html .= &GetOldPageLink( 'edit', $id, $revid, T('(edit)') ) . ' ';
            }
        }
        if ( $i == 0 ) {
            ( $pts, $puser, $phost, $psummary ) = ( $ts, $user, $host, $summary );
        }
        $html .= ". . " . $minor . &TimeToText($pts) . " ";
        $html .= T('by') . ' ' . &GetAuthorLink( $phost, $puser, $uid ) . " ";
        if ( defined($psummary) && ( $psummary ne "" ) && ( $psummary ne "*" ) ) {
            $psummary = &QuoteHtml($psummary);    # Thanks Sunir! :-)
            $html .= "<b>[$psummary]</b> ";
        }
        $html .= $UseDiff ? "</tr>\n" : "<br>\n";
    }
    return $html;
}

# ==== HTML and page-oriented functions ====
sub ScriptLinkChar {
    if ($SlashLinks) {
        return '/';
    }
    return '?';
}

sub ScriptLink {
    my ( $action, $text ) = @_;

    return "<a href=\"$ScriptName" . &ScriptLinkChar() . &UrlEncode($action) . "\">$text</a>";
}

sub ScriptLinkClass {
    my ( $action, $text, $class, $hint ) = @_;
    $hint = defined($hint) && $hint ne '' ? "title='$hint'" : '';
    return
        "<a href=\"$ScriptName"
      . &ScriptLinkChar()
      . &UrlEncode($action) . "\""
      . " class='$class' $hint>$text</a>";
}

sub GetPageLinkText {
    my ( $id, $name, $style, $hint ) = @_;

    $id =~ s|^/|$MainPage/|;
    if ($FreeLinks) {
        $id = &FreeToNormal($id);
        $name =~ s/_/ /g;
    }
    $style = 'wikipagelink' if ( !length($style) );
    return &ScriptLinkClass( $id, $name, $style, $hint );
}

sub GetPageLink {
    my ($id) = @_;

    return &GetPageLinkText( $id, $id );
}

sub GetEditLink {
    my ( $id, $name, $style, $hint ) = @_;

    if ($FreeLinks) {
        $id = &FreeToNormal($id);
        $name =~ s/_/ /g;
    }
    $style = 'wikipageedit' if ( !defined($style) || $style eq '' );
    return &ScriptLinkClass( "action=edit&id=$id", $name, $style, $hint );
}

sub GetDeleteLink {
    my ( $id, $name, $confirm ) = @_;

    if ($FreeLinks) {
        $id = &FreeToNormal($id);
        $name =~ s/_/ /g;
    }
    return &ScriptLink( "action=delete&id=$id&confirm=$confirm", $name );
}

sub GetOldPageParameters {
    my ( $kind, $id, $revision ) = @_;

    $id = &FreeToNormal($id) if $FreeLinks;

    #  return "action=" . "$kind&id=".UrlEncode($id)."&revision=$revision";
    return "action=" . "$kind&id=" . $id . "&revision=$revision";
}

sub GetOldPageLink {
    my ( $kind, $id, $revision, $name ) = @_;

    $name =~ s/_/ /g if $FreeLinks;
    return &ScriptLink( &GetOldPageParameters( $kind, $id, $revision ), $name );
}

sub GetPageOrEditAnchoredLink {
    my ( $id, $anchor, $name ) = @_;
    my ( @temp, $exists );

    if ( $name eq "" ) {
        $name = $id;
        if ($FreeLinks) {
            $name =~ s/_/ /g;
        }
    }
    $id =~ s|^/|$MainPage/|;
    if ($FreeLinks) {
        $id = &FreeToNormal($id);
    }
    $exists = 0;
    if ( PageExists($id) ) {    # Page file exists
        $exists = 1;
    }
    if ($exists) {
        $id   = "$id#$anchor"   if $anchor;
        $name = "$name#$anchor" if $anchor && $NamedAnchors != 2;
        return &GetPageLinkText( $id, $name );
    }
    if ( $FreeLinks && !$EditNameLink ) {
        if ( $name =~ m| | ) {    # Not a single word
            $name = "[$name]";    # Add brackets so boundaries are obvious
        }
    }
    if ($EditNameLink) {
        return &GetEditLink( $id, $name );
    } else {
        return $name . &GetEditLink( $id, '?' );
    }
}

sub GetPageOrEditLink {
    my ( $id, $name ) = @_;
    return &GetPageOrEditAnchoredLink( $id, "", $name );
}

sub GetBackLinksSearchLink {
    my ( $id, $style, $hint ) = @_;
    my $name = $id;

    $id =~ s|.+/|/|;    # Subpage match: search for just /SubName
    if ($FreeLinks) {
        $name =~ s/_/ /g;    # Display with spaces
        $id   =~ s/_/+/g;    # Search for url-escaped spaces
    }
    return &ScriptLink( "back=$id", $name ) if ( $style eq '' );
    return &ScriptLinkClass( "back=$id", $name, $style, $hint );
}

sub GetPrefsLink {
    return &ScriptLinkClass( "action=editprefs", T('Preferences'), 'wikipreflink' );
}

sub GetRandomLink {
    return &ScriptLink( "action=random", T('Random Page') );
}

sub ScriptLinkDiff {
    my ( $diff, $id, $text, $rev ) = @_;

    $rev  = "&revision=$rev"              if ( $rev ne "" );
    $diff = &GetParam( "defaultdiff", 1 ) if ( $diff == 4 );
    return &ScriptLink( "action=browse&diff=$diff&id=$id$rev", $text );
}

sub ScriptLinkDiffRevision {
    my ( $diff, $id, $rev, $text ) = @_;

    $rev  = "&diffrevision=$rev"          if ( $rev ne "" );
    $diff = &GetParam( "defaultdiff", 1 ) if ( $diff == 4 );
    return &ScriptLink( "action=browse&diff=$diff&id=$id$rev", $text );
}

sub GetUploadLink {
    return &ScriptLink( 'action=upload', T('Upload') );
}

sub ScriptLinkTitle {
    my ( $action, $text, $title, $class ) = @_;

    if ($FreeLinks) {
        $action =~ s/ /_/g;
    }
    return
        "<a href=\"$ScriptName"
      . &ScriptLinkChar()
      . &UrlEncode($action)
      . "\" title=\"$title\" class=\"$class\">$text</a>";
}

sub GetAuthorLink {
    my ( $host, $userName, $uid ) = @_;
    my ( $html, $title, $userNameShow );

    if ( length($host) > 15 ) {
        $host = ShortString( $host, 15 );
    }

    $userNameShow = $userName;
    if ($FreeLinks) {
        $userName     =~ s/ /_/g;
        $userNameShow =~ s/_/ /g;
    }
    if ( &ValidId($userName) ne "" ) {    # Invalid under current rules
        $userName = "";                   # Just pretend it isn't there.
    }
    if ( defined $uid && ( $uid > 0 ) && ( $userName ne "" ) ) {
        $html =
          &ScriptLinkTitle( $userName, $userNameShow,
            Ts( 'ID %s', $uid ) . ' ' . Ts( 'from %s', $host ),
            'wikiauthorlink' );
    } else {
        $html = $host;
    }
    return $html;
}

sub GetBrowseLink {
    my ( $id, $text, $style, $hint ) = @_;

    if ($FreeLinks) {
        $id =~ s/ /_/g;
    }
    $style = 'wikidiscusslink' if ( $style eq '' );
    return &ScriptLinkClass( "$id", $text . $id, $style, $hint );
}

sub GetCommentLink {
    my ( $id, $text, $style, $hint ) = @_;

    if ($FreeLinks) {
        $id =~ s/ /_/g;
    }

    #  return &ScriptLinkClass("action=discuss&id=$id", $text.$id, 'wikidiscusslink');
    $style = 'wikidiscusslink' if ( $style eq '' );
    return &ScriptLinkClass( "action=discuss&id=$id", $text, $style, $hint );
}

sub GetHistoryLink {
    my ( $id, $text, $style, $hint ) = @_;

    if ($FreeLinks) {
        $id =~ s/ /_/g;
    }
    $style = 'wikihistorylink' if ( $style eq '' );
    return &ScriptLinkClass( "action=history&id=$id", $text, $style, $hint );
}

sub ShortString {
    my ( $id, $len ) = @_;
    my $shortname;

    $shortname = substr( $id, 0, $len );
    if ( UrlEncode($shortname) =~ /\%[eE][0-9A-Fa-f]$/ ) { chop($shortname); }
    if ( UrlEncode($shortname) =~ /\%[eE][0-9A-Fa-f]\%8[0-9A-Fa-f]$/ ) {
        chop($shortname);
        chop($shortname);
    }
    $shortname .= "...";
    return $shortname;
}

sub GetHeader {
    my ( $id, $title, $oldId, $nocache ) = @_;
    my $logoImage = "";
    my $result    = "";
    my $embed     = &GetParam( 'embed', $EmbedWiki );
    my $altText   = T('[Home]');
    my ( $action, $tab );

    if ( $PrintedHeader == 1 ) {
        return;
    }
    $PrintedHeader = 1;

    $result = &GetHttpHeader( '', &GetParam( 'expires', '' ) );
    if ($FreeLinks) {
        $title =~ s/_/ /g;    # Display as spaces
    }
    $result .= &GetHtmlHeader( "$SiteName: $title", $nocache );
    return $result if ($embed);

    if ( ( !$embed ) && ( $LogoUrl ne "" ) ) {
        $logoImage = "img src=\"$LogoUrl\" id='logoimg' alt=\"$altText\" border=0";
        $result .= '<div class="wikilogo">' . &ScriptLink( $HomePage, "<$logoImage>" ) . '</div>';
    }
    $result .= '<div class="wikiheader">';

    if ( &GetParam( "toplinkbar", 1 ) ) {
        $result .= &GetGotoBar($id);
    }
    if ( $oldId ne '' ) {
        $result .= $q->h5( '(' . Ts( '» %s', &GetEditLink( $oldId, $oldId ) ) . ')' );
    }
    $result .= '</div>';
    $result .= '<div class="wikititle"><ul class=titletab>';
    $action = &GetParam( "action", "" );
    $tab    = "inactivetab";
    $tab    = "activetab" if ( $action eq "browse" || $action eq "" );

    #  if ($id ne '') {
    #    $result .=  "<li class='activetab'>".&GetBackLinksSearchLink($id,"icon-link")."</li>";
    #  } else {
    #    $result .=  "<li class='activetab'><span class='icon-link'>$title</span></li>";
    #  }
    if ( $id ne '' && $action ne 'edit' && $action ne 'history' ) {
        $result .= "<li class='inactivetab'>"
          . &GetEditLink( $id, T('Edit this page'), 'icon-edit', T('Edit this page') ) . '</li>';
        $result .= "<li class='inactivetab'>";
        $result .=
          &GetHistoryLink( $id, T('View other revisions'), "icon-time", T('View other revisions') );
        $result .= "</li><li class='inactivetab'>";
        if ( not( $id =~ m|$DiscussSuffix$| ) ) {
            $result .= &GetCommentLink( $id, T('Discuss'), "icon-comments", T('Discuss') );
        } else {
            $result .= &GetBrowseLink( substr( $id, 0, length($id) - length($DiscussSuffix) ),
                T('Return'), "icon-undo", T('Return') );
        }
        $result .= '</li>';
    }
    $result .= '</ul></div>' . &GetWrapperStart();
    return $result;
}

sub GetWrapperStart {
    return '<div class="wikiwrapper">';
}

sub GetWrapperEnd {
    return '</div>';
}

sub GetHttpHeader {
    my ( $type, $expire ) = @_;
    my ( $cookie, $exptime );

    if   ( $expire eq "" ) { $exptime = "'now'"; }
    else                   { $exptime = "'$expire'"; }

    $type = 'text/html' if ( $type eq '' );
    if ( defined( $SetCookie{'id'} ) ) {
        my $val =
          $SetCookie{'id'}
          ? SignSessionToken( $SetCookie{'id'}, 30 * 86400 )
          : '';
        my $ttl = $SetCookie{'id'} ? 30 * 86400 : -1;
        $cookie = $q->cookie( BuildSessionCookie( $val, $ttl ) );
        if ( $HttpCharset ne '' ) {
            return $q->header(
                -cookie  => $cookie,
                -expires => $exptime,
                -type    => "$type; charset=$HttpCharset"
            );
        }
        return $q->header( -cookie => $cookie, -expires => $exptime );
    }
    if ( $HttpCharset ne '' ) {
        return $q->header( -type => "$type; charset=$HttpCharset", -expires => $exptime )
          if $expire ne "";
        return $q->header( -type => "$type; charset=$HttpCharset" );
    }
    return $q->header( -type => $type, -expires => $exptime ) if $expire ne "";
    return $q->header( -type => $type );
}

sub GetHtmlHeader {
    my ( $title, $nocache ) = @_;
    my ( $dtd, $html, $bodyExtra, $stylesheet, $printcss, $fontcss );

    $html  = '';
    $html  = ( defined($DocType) && $DocType ne '' ? $DocType : qq(<!DOCTYPE HTML PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN">) ) . "\n";
    $title = $q->escapeHTML($title);
    $html .= "<html><head><title>$title</title>\n";
    $html .= "<meta http-equiv=\"content-type\" content=\"text/html; charset=$HttpCharset\"/>";
    if ( defined($nocache) && $nocache ne '' ) {
        $html .= "<meta http-equiv=\"cache-control\" content=\"$nocache\"/>";
    }
    if ( defined($FavIcon) && $FavIcon ne '' ) {
        $html .= '<link rel="SHORTCUT ICON" href="' . $FavIcon . '">';
    }
    if ($MetaKeywords) {
        my $keywords = $OpenPageName;
        $keywords =~ s/([a-z])([A-Z])/$1, $2/g;
        $html .= "<meta name='keywords' content='$keywords'/>\n" if $keywords;
    }
    $html .=
        '<link rel="alternate" type="application/rss+xml" title="'
      . $SiteName
      . '" HREF="http://'
      . ( $ENV{SERVER_NAME} // '' )
      . ( $ENV{SCRIPT_NAME} // '' )
      . &ScriptLinkChar()
      . 'action=rss"/>';

    if ( $SiteBase ne "" ) {
        $html .= qq(<base href="$SiteBase">\n);
    }
    $stylesheet = &GetParam( 'stylesheet', $StyleSheet );
    $stylesheet = $StyleSheet if ( $stylesheet eq '' );
    $stylesheet = ''          if ( $stylesheet eq '*' );    # Allow removing override
    $printcss   = $stylesheet;
    # A ?query suffix (e.g. "?v=20261104" to bust browser and proxy caches)
    # carries over to the derived stylesheets.
    $printcss =~ s{\.[Cc][Ss][Ss](\?[^?]*)?$}{'_print.css' . ($1 // '')}e;
    $fontcss = $stylesheet;
    $fontcss =~ s{\.[Cc][Ss][Ss](\?[^?]*)?$}{'_webfont.css' . ($1 // '')}e;

    if ( $stylesheet ne '' ) {
        $html .= qq(<style type="text/css">
.wikiheader ul li{display:inline;padding-left:10px;}
.wikiadminbar ul li{display:inline;padding-left:10px;}
.wikiuserbar ul li{display:inline;padding-left:10px;}
.wikititle ul li{display:inline;padding-left:10px;}
.wikifooter {margin-top: 10pt;border-top:solid 1px black;}
.wikiwrapper {border:1px solid black;padding:10pt;}
.wikisearchbox {float:right;}
.wikieditor {width:100%;}
$UserBuildinCSS</style>\n);
        $html .= qq(<link rel="stylesheet" href="$fontcss">\n);
        $html .= qq(<link rel="stylesheet" href="$stylesheet">\n);
        $html .= qq(<link rel="stylesheet" href="$printcss" media="print">\n);
    }
    $html .= $UserHeader;
    $bodyExtra = '';
    if ( $UserBody ne '' ) {
        $bodyExtra = ' ' . $UserBody;
    }
    $html .= "</head><body$bodyExtra><div class='wikimain'>\n";
    return $html;
}

sub GetFooterText {
    my ( $id, $rev ) = @_;
    my ( $result, $Section );

    $Section = \%{ $Pages{$id}->{'section'} };

    if ( &GetParam( 'embed', $EmbedWiki ) ) {
        return $q->end_html;
    }
    $result = '<div class="wikifooter">';
    if ( defined( $$Section{'revision'} ) && $$Section{'revision'} > 0 ) {
        $result .= '<div class="wikipginfo">';
        if ( !defined($rev) || $rev eq '' ) {    # Only for most current rev
            $result .= T('Last edited');
        } else {
            $result .= T('Edited');
        }
        $result .= ' ' . &TimeToText( $$Section{ts} );
        if ($AuthorFooter) {
            $result .= ' '
              . Ts( 'by %s',
                &GetAuthorLink( $$Section{'host'}, $$Section{'username'}, $$Section{'id'} ) );
        }
        $result .= '</div>';
    }

    if ( $UserID > 1000 && $UserData{'username'} ) {
        $result .= &GetUserBar($id);
    }
    if ( $AdminBar && &UserIsAdmin() ) {
        $result .= &GetAdminBar($id);
    }
    if ( $DataDir =~ m|/tmp/| ) {
        $result .= '<b>'
          . T('Warning')
          . ':</b> '
          . Ts( 'Database is stored in temporary directory %s', $DataDir ) . '|';
    }
    if ( $ConfigError ne '' ) {
        $result .= '<b>' . T('Config file error:') . '</b> ' . $ConfigError . '|';
    }

    if ( $FooterNote ne '' ) {
        $result .= '<div class="wikifooternote">' . T($FooterNote) . "</div>";
    }
    $result .= '</div>';
    $result .= &GetMinimumFooter();
    return $result;
}

sub GetCommonFooter {
    my ($html);
    $html = &GetWrapperEnd();
    $html .= '<hr class="wikilinefooter"><div class="wikifooter">';
    if ( $FooterNote ne '' ) {
        $html .= T($FooterNote);
    }
    $html .= '</div>' . $q->end_html;
    $html .= "</div>";                  # for wikimain
    return $html;
}

sub GetMinimumFooter {
    return &GetWrapperEnd() . $q->end_html . "</div>";
}

sub GetFormStart {
    my $form = $q->start_form( "POST", "$ScriptName", "application/x-www-form-urlencoded" );
    my $tok  = GenCSRFToken();
    $form .= qq(<input type="hidden" name="csrf_token" value="$tok" />);
    return $form;
}

sub GetGotoBar {
    my ($id) = @_;
    my ( $main, $bartext );

    $bartext = '<ul class="wikiheaderlist"><li class="icon-home">';
    $bartext .= &GetPageLinkText( $HomePage, T('Home') );
    $bartext .= '</li>';

    if ( $id =~ m|/| ) {
        $main = $id;
        $main =~ s|/.*||;    # Only the main page name (remove subpage)
        $bartext .= '<li>' . &GetPageLink($main) . '</li>';
    }
    $bartext .= "<li>" . &GetPageLinkText( $RCName, T('Activities') ) . '</li>';
    if ( $PermUseUpload && &UserCanUpload() ) {
        $bartext .= "<li>" . &GetUploadLink() . '</li>';
    }
    if ( &GetParam( "linkrandom", 0 ) ) {
        $bartext .= "<li>" . &GetRandomLink() . '</li>';
    }
    if ( $UserGotoBar ne '' ) {
        $bartext .= $UserGotoBar;
    }
    if ( !defined( $UserData{'username'} ) || $UserData{'username'} eq '' ) {
        $bartext .=
            "<li><a href=\"$ScriptName"
          . &ScriptLinkChar()
          . "action=login\">"
          . T('Login') . '</a>' . '</li>';
    } else {
        $bartext .= "<li>" . &GetPrefsLink() . '</li>';
        $bartext .=
            "<li><a href=\"$ScriptName"
          . &ScriptLinkChar()
          . "action=logout\">"
          . T('Logout') . '</a>' . '</li>';
    }
    $bartext .= "</ul>\n";
    $bartext .= &GetSearchForm();

    return $bartext;
}

sub GetSearchForm {
    my ($result);
    $result = &GetFormStart();
    $result .= $q->textfield(
        -name    => 'search',
        -size    => 10,
        -value   => T('Search ...'),
        -class   => 'wikisearchbox',
        -onfocus => "if(!this._haschanged){this.value=''};this._haschanged=true;",
        -onblur  => "if(this.value===''){this.value='"
          . T('Search ...')
          . "'};this._haschanged=false;",
    );
    if ($SearchButton) {
        $result .= $q->submit( 'dosearch', T('Go!') );
    } else {
        $result .= &GetHiddenValue( "dosearch", 1 );
    }
    $result .= $q->end_form;

    return $result;
}

# Absolute URL of this script, for links the wiki builds to itself.
# Behind a TLS-terminating proxy the CGI sees plain http, so with
# $UseHttps (default) an http:// URL is upgraded to https://, except
# for local development hosts.
sub SelfUrl {
    my $u = $q->url( -full => 1 );
    $u =~ s{\Ahttp://}{https://}i
      if ( $UseHttps && $u !~ m{\Ahttp://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?(?:/|\z)}i );
    return $u;
}

sub GetRedirectPage {
    my ( $newid, $name, $isEdit ) = @_;
    my ( $url, $html );
    my ($nameLink);

    if ( $newid =~ /^http[s:]+\/\// ) {
        $url = $newid;
    } else {

        # Normally get URL from script, but allow override.
        $FullUrl = &SelfUrl() if ( $FullUrl eq "" );
        $url     = $FullUrl . &ScriptLinkChar() . &UrlEncode($newid);
    }
    $nameLink = "<a href=\"$url\">$name</a>";
    if ( $RedirType < 3 ) {
        if ( $RedirType == 1 ) {    # Use CGI.pm
             # NOTE: do NOT use -method (does not work with old CGI.pm versions) Thanks to Daniel Neri for fixing this
             # problem.
            $html = $q->redirect( -uri => $url );
        } elsif ( $RedirType == 4 ) {
            $html .= "Content-Type: text/html\n\n<html><head>"
              . "<meta HTTP-EQUIV='Refresh' CONTENT='0; URL=$url'></head></html>\n";
        } else {    # Minimal header
            $html = "Status: 302 Moved\n";
            $html .= "Location: $url\n";
            if ( defined( $SetCookie{'id'} ) ) {
                my $val =
                  $SetCookie{'id'}
                  ? SignSessionToken( $SetCookie{'id'}, 30 * 86400 )
                  : '';
                my $ttl = $SetCookie{'id'} ? 30 * 86400 : -1;
                my $ck  = $q->cookie( BuildSessionCookie( $val, $ttl ) );
                $html .= "Set-Cookie: $ck\n";
            }
            $html .= "Content-Type: text/html\n\n";           # Needed for browser failure
            $html .= "<html><script type='text/javascript'>
<!--
window.location = '$url'
//-->
</script></html>";
        }
        $html .= "\n" . Ts( 'Your browser should go to the %s page.', $newid );
        $html .= ' ' . Ts( 'If it does not, click %s to continue.', $nameLink );
    } else {
        if ($isEdit) {
            $html = &GetHeader( '', T('Thanks for editing...'), '' );
            $html .= Ts( 'Thank you for editing %s.', $nameLink );
        } else {
            $html = &GetHeader( '', T('Link to another page...'), '' );
        }
        $html .= "\n<p>";
        $html .= Ts( 'Follow the %s link to continue.', $nameLink );
        $html .= &GetMinimumFooter();
    }
    return $html;
}

# ==== Common wiki markup ====
# RestoreSavedText, RemoveFS, ApplyRegExp moved to Habitat::Render.

sub getnextnum {
    my ($id) = @_;
    $id =~ s/\/$//g;
    my $op        = Habitat::Store::regex_op();
    my @matchitem = split(
        /\n/,
        ReadDBItems(
            GetPageDB($id), 'id', "\n", '',
            "id $op ? group by id",
            "^" . quotemeta($id) . "/[0-9]+"
        )
    );
    for ( my $i = 0 ; $i < @matchitem ; $i++ ) {
        $matchitem[$i] =~ s/^$id\///;
    }
    return sprintf( "%04d", ( sort(@matchitem) )[-1] + 1 ) if ( @matchitem >= 0 );
}

# WikiToHTML moved to Habitat::Render (phase 2 of render extraction).

sub GetLocalTree {
    my ( $id, $namepat, $format ) = @_;
    my ( $toptree, $topnode );
    if ( !( defined $LocalTree ) && $IsPrintTree ) {
        my $op        = Habitat::Store::regex_op();
        my @matchitem = split(
            /\n/,
            ReadDBItems(
                GetPageDB($id), 'id', "\n", '',
                "id $op ? group by id",
                quotemeta($id) . "/" . $namepat
            )
        );
        foreach my $subitem (@matchitem) {
            my $oo      = $format;
            my $xmltext = ReadRawWikiPage($subitem);
            $oo =~ s/%([0-9a-zA-Z_]+)%/&GetXMLFields($1,$xmltext,$subitem,$subitem)/goe;
            $LocalTree .= $oo;    #"<li class=\"wikitreefile\">$oo</li>\n";
        }

        if ( $toptree ne '' ) {
            $LocalTree =
                "<ul class=\"wikitreedir\"><li class=\"wikitreefile\"><a href=\"$ScriptName"
              . &ScriptLinkChar()
              . "$topnode\">$topnode</a></li>\n  $LocalTree </ul>";
        }
        $LocalTree =
            "<div class=\"wikitree\"><h5>"
          . T("Subpage List") . "</h5>"
          . "<table class=\"wikitreeblock\">$LocalTree</table></div>";
    }
    return $LocalTree;
}

sub RestorePageHash {
    my ($id) = @_;
    my $pagehash = $id;

    $SaveUrl         = "SaveUrl$pagehash";
    $SaveNumUrl      = "SaveNumUrl$pagehash";
    $SaveUrlIndex    = "SaveUrlIndex$pagehash";
    $SaveNumUrlIndex = "SaveNumUrlIndex$pagehash";
}

# added by FangQ, 2006/4/16

# Load {'page'}{'admin_saved'} for a page that was not opened via
# OpenPageDB (e.g. one pulled in by {{Page}} embedding). Leaves an
# already-loaded flag alone. Pages not in the DB (e.g. %BuildinPages)
# stay untrusted.
sub LoadPageTrust {
    my ($id) = @_;
    return if ( defined $Pages{$id}->{'page'}{'admin_saved'} );
    my $pagedb = &GetPageDB($id);
    my $trust  = 0;
    if ( $dbh ne "" && $pagedb ne "" && SafeIdent($pagedb) ) {
        ($trust) = $dbh->selectrow_array(
            "SELECT admin_saved FROM $pagedb WHERE id=? ORDER BY revision DESC LIMIT 1",
            undef, $id );
    }
    $Pages{$id}->{'page'}{'admin_saved'} = $trust ? 1 : 0;
}

sub EmbedWikiPage {
    my ( $id, $uri, $name, $text ) = @_;
    $uri  = '' if ( !defined($uri) );
    $name = '' if ( !defined($name) );
    $text = '' if ( !defined($text) );
    my ( $res, $PageStack );
    if ( $name eq "" ) {
        $name = $id;
        if ($FreeLinks) {
            $name =~ s/_/ /g;
        }
    }
    if ($FreeLinks) {
        $id = &FreeToNormal($id);
    }
    $PageStack = \@{ $Pages{$id}->{'embed'} };
    if ( PageExists($id) && @$PageStack <= $MaxEmbedDepth ) {
        if ( $uri eq "" ) {
            if ( $text eq '' ) {

                # The embedded page renders its own content, so it gets
                # its own raw-HTML trust. ReadRawWikiPage does not load
                # admin_saved, so without this every embed was scrubbed.
                &LoadPageTrust($id);
                $res = &WikiToHTML( $id, ReadRawWikiPage($id) );
            } else {

                # Caller-supplied text formatted with $id's rules: the
                # text belongs to the embedding page, so never let it
                # inherit $id's trust.
                local $Pages{$id}->{'page'}{'admin_saved'} = 0;
                $res = &WikiToHTML( $id, $text );    # use the rules for $id to format $text
            }
        } else {
            $res = &WikiToHTML( GetVariable( ReadRawWikiPage($id), $uri ) );
        }
        $res = "<div class='embedpage'>\n" . $res . "\n</div>";
        push( @$PageStack, $id );
    } else {
        $res = &GetPageOrEditLink( $id, $name );
    }
    return $res;
}

sub EmbedWikiPageRaw {
    my ( $id, $uri, $name ) = @_;
    $uri  = '' if ( !defined($uri) );
    $name = '' if ( !defined($name) );
    my ( $res, $PageStack );
    if ( $name eq "" ) {
        $name = $id;
        if ($FreeLinks) {
            $name =~ s/_/ /g;
        }
    }
    if ($FreeLinks) {
        $id = &FreeToNormal($id);
    }
    $PageStack = \@{ $Pages{$id}->{'embed'} };
    if ( PageExists($id) && @$PageStack <= $MaxEmbedDepth ) {
        if ( $uri eq "" ) {
            $res = &ReadRawWikiPage($id);
        } else {
            $res = &GetVariable( &ReadRawWikiPage($id), $uri );
        }
        push( @$PageStack, $id );
    } else {
        $res = &GetPageOrEditLink( $id, $name );
    }
    return $res;
}

sub GetVariable {
    my ( $text, $var ) = @_;
    my $res;
    if ( $text =~ m/\{\{\{$var\}(.*)\}\}/s ) {
        $res = $1;
    }
    return $res;
}

sub GetXMLFields {
    my ( $pat, $data, $thispage, $thispagefull ) = @_;
    my ($val);
    if ( $pat eq "THIS" )     { return $thispage; }
    if ( $pat eq "THISFULL" ) { return $thispagefull; }
    if ( $data =~ /<$pat>(.*)<\/$pat>/s ) {
        $val = $1;
        $val =~ s/\[\[$FreeLinkPattern\]\]/&StorePageOrEditLink($1, "")/geo;
        return $val;
    }
    return "";
}

sub BuildWikiTree {
    my ( $topDir, $baseDir, $namepat, $outpat ) = @_;
    my $fcount;
    my ( @dirs, @seg, $dir, $file, $fname, $sname, $lname, $currdir );
    my ( $xmltext, $oo );
    my $treetext = "<ul class=\"pagetree\">\n";

    $fcount  = 0;
    $currdir = ( reverse split( /\//, $topDir ) )[0];

    opendir( DIRLIST, $topDir );
    @dirs = readdir(DIRLIST);
    closedir(DIRLIST);
    @dirs = sort(@dirs);
    foreach $dir (@dirs) {
        next if ( substr( $dir, 0, 1 ) eq '.' );    # No ., .., or .dirs
        if ( $namepat ne "" && not $dir =~ /$namepat/ ) { next; }
        $fname = "$topDir/$dir";
        $sname = $dir;
        $sname =~ s/\.db$//;
        $lname = $fname;
        if ( $lname =~ /$baseDir\/(.+)$/ ) { $lname = $1; $lname =~ s/\.db$//; }  # lname is page id
        if ( -f $fname ) {
            if ( $fcount == 50 ) {
                $treetext .= "<li class=\"wikitreefile\">...</li>\n";
                next;
            } elsif ( $fcount > 50 ) {
                next;
            }
            if ( -d "$topDir/$sname" ) { next; }
            if ( $outpat eq "" ) {
                $treetext .=
                    "<li class=\"wikitreefile\"><a href=\"$ScriptName"
                  . &ScriptLinkChar()
                  . "$lname\">$sname</a></li>\n";
            } else {
                $oo      = $outpat;
                $xmltext = ReadRawWikiPage($lname);
                $oo =~ s/%([0-9a-zA-Z_]+)%/&GetXMLFields($1,$xmltext,$sname,$lname)/goe;
                $treetext .= "<li class=\"wikitreefile\">$oo</li>\n";
            }
            $fcount++;
        } elsif ( -d $fname ) {
            if ( -f "$fname\.db" ) {
                $treetext .=
                    "<li class=\"wikitreedir\"><a href=\"$ScriptName"
                  . &ScriptLinkChar()
                  . "$lname\" class=\"wikipagelink\">$sname</a></li>\n"
                  . &BuildWikiTree( $fname, $baseDir );
            } else {
                $treetext .=
                    "<li class=\"wikitreedir\"><a href=\"$ScriptName"
                  . &ScriptLinkChar()
                  . "action=edit&id=$lname\" class=\"wikipageedit\">$sname</a></li>\n"
                  . &BuildWikiTree( $fname, $baseDir );
            }
        }
    }
    $treetext .= "</ul>";
    return $treetext;
}

# WikiToHTML, CommonMarkup, WikiLinesToHtml, ParseParagraph, StoreInterPage,
# InterPageLink, StoreBracketInterPage, GetSiteUrl moved to Habitat::Render
# (phase 2). Inter-mixed "# foo moved" comments from phase 1 are absorbed.

# StoreRaw, StorePre, StoreHref, StoreUrl moved to Habitat::Render.

sub UrlLink {
    my ( $rawname, $useImage ) = @_;
    my ( $name, $punct );

    ( $name, $punct ) = &SplitUrlPunct($rawname);
    if ( $LimitFileUrl && ( $NetworkFile && $name =~ m|^file:| ) ) {

        # Only do remote file:// links. No file:///c|/windows.
        if ( $name =~ m|^file://[^/]| ) {
            return ( "<a href=\"" . UrlEncode($name) . "\">$name</a>", $punct );
        }
        return ( $rawname, '' );
    }
    return ( &UrlLinkOrImage( $name, $name, $useImage ), $punct );
}

sub UrlLinkOrImage {
    my ( $url, $name, $useImage ) = @_;

    # Restricted image URLs so that mailto:foo@bar.gif is not an image
    if ( $useImage && &ImageAllowed($url) ) {
        return "<img src=\"$url\" class=\"wikiimg\">";
    }

    #  $url=UrlEncode($url);
    return "<a href=\"$url\">$name</a>";
}

sub ImageAllowed {
    my ($url) = @_;
    my ( $site, $imagePrefixes );

    $imagePrefixes = 'http:|https:|ftp:';
    $imagePrefixes .= '|file:' if ( !$LimitFileUrl );
    return 1 if ( $url =~ /Count\.cgi/ );
    return 0 unless ( $url =~ /^($imagePrefixes).+\.$ImageExtensions$/ );
    return 0 if ( $url =~ /"/ );                 # No HTML-breaking quotes allowed
    return 1 if ( @ImageSites < 1 );             # Most common case: () means all allowed
    return 0 if ( $ImageSites[0] eq 'none' );    # Special case: none allowed
    foreach $site (@ImageSites) {
        return 1 if ( $site eq substr( $url, 0, length($site) ) );    # Match prefix
    }
    return 0;
}

sub StoreBracketUrl {
    my ( $url, $text, $useImage ) = @_;

    if ( $text eq "" ) {
        $text = &GetBracketUrlIndex($url);
    }
    if ( $BracketImg && $useImage && &ImageAllowed($text) ) {
        $text = "<img src=\"$text\" class=\"wikilinkimg\">";
    } else {
        $text = "$text";
    }
    if ( $url =~ /^http:(#.*)/ ) {
        $url = $1;
    }

    #  $url=UrlEncode($url);
    return &StoreRaw("<a href=\"$url\" class=\"wikiurllink\">$text</a>");
}

sub StoreBracketLink {
    my ( $name, $text ) = @_;

    return &StoreRaw( &GetPageLinkClass( $name, "$text", "wikiurllink" ) );
}

sub StoreBracketAnchoredLink {
    my ( $name, $anchor, $text ) = @_;

    return &StoreRaw( &GetPageLinkClass( "$name#$anchor", "$text", "wikiurllink" ) );
}

sub StorePageOrEditLink {
    my ( $page, $name ) = @_;

    if ($FreeLinks) {
        $page =~ s/^\s+//;        # Trim extra spaces
        $page =~ s/\s+$//;
        $page =~ s|\s*/\s*|/|;    # ...also before/after subpages
    }
    $name =~ s/^\s+//;
    $name =~ s/\s+$//;
    return &StoreRaw( &GetPageOrEditLink( $page, $name ) );
}

sub StoreRFC {
    my ($num) = @_;

    return &StoreRaw( &RFCLink($num) );
}

sub RFCLink {
    my ($num) = @_;

    return "<a href=\"http://www.faqs.org/rfcs/rfc${num}.html\">RFC $num</a>";
}

sub StoreUpload {
    my ($url) = @_;
    return &StoreRaw( &UploadLink($url) );
}

sub UploadLink {
    my ($filename) = @_;
    my ( $html, $url );
    return $filename  if ( $UploadUrl eq '' );                      # No bad links if misconfigured
    $UploadUrl .= '/' if ( substr( $UploadUrl, -1, 1 ) ne '/' );    # End with /
    $url  = $UploadUrl . $filename;
    $html = '<a href="' . $url . '">';

    if ( &ImageAllowed($url) ) {
        $html .= '<img src="' . $url . '" alt="upload:' . $filename . '" class="wikiuploadimg">';
    } else {
        $html .= 'upload:' . $filename;
    }
    $html .= '</a>';
    return $html;
}

sub StoreISBN {
    my ($num) = @_;

    return &StoreRaw( &ISBNLink($num) );
}

sub ISBNALink {
    my ( $num, $pre, $post, $text ) = @_;

    return '<a href="' . $pre . $num . $post . '">' . $text . '</a>';
}

sub ISBNLink {
    my ($rawnum) = @_;
    my ( $rawprint, $html, $num, $numSites, $i );

    $num      = $rawnum;
    $rawprint = $rawnum;
    $rawprint =~ s/ +$//;
    $num      =~ s/[- ]//g;
    $numSites = scalar @IsbnNames;    # Number of entries
    if ( ( length($num) != 10 ) || ( $numSites < 1 ) ) {
        return "ISBN $rawnum";
    }
    $html = &ISBNALink( $num, $IsbnPre[0], $IsbnPost[0], 'ISBN ' . $rawprint );
    if ( $numSites > 1 ) {
        $html .= ' (';
        $i = 1;
        while ( $i < $numSites ) {
            $html .= &ISBNALink( $num, $IsbnPre[$i], $IsbnPost[$i], $IsbnNames[$i] );
            if ( $i < ( $numSites - 1 ) ) {    # Not the last site
                $html .= ', ';
            }
            $i++;
        }
        $html .= ')';
    }
    $html .= " " if ( $rawnum =~ / $/ );    # Add space if old ISBN had space.
    return $html;
}

sub SplitUrlPunct {
    my ($url) = @_;
    my ($punct);

    if ( $url =~ s/\"\"$// ) {
        return ( $url, "" );    # Delete double-quote delimiters here
    }
    $punct = "";
    if ($NewFS) {
        ($punct) = ( $url =~ /([^a-zA-Z0-9\/\x80-\xff]+)$/ );
        $url =~ s/([^a-zA-Z0-9\/\xc0-\xff]+)$//;
    } else {
        ($punct) = ( $url =~ /([^a-zA-Z0-9\/\xc0-\xff]+)$/ );
        $url =~ s/([^a-zA-Z0-9\/\xc0-\xff]+)$//;
    }
    return ( $url, $punct );
}

sub StripUrlPunct {
    my ($url) = @_;
    my ($junk);

    ( $url, $junk ) = &SplitUrlPunct($url);
    return $url;
}

sub WikiHeadingNumber {
    my ( $depth, $text ) = @_;
    my ( $anchor, $number );
    my $oldtext = $text;

    return '' unless --$depth > 0;    # Don't number H1s because it looks stupid
    while ( scalar @HeadingNumbers < ( $depth - 1 ) ) {
        push @HeadingNumbers, 1;
        $TableOfContents .= '<dl class="wikitoc"><dt> </dt><dd>';
    }
    if ( scalar @HeadingNumbers < $depth ) {
        push @HeadingNumbers, 0;
        $TableOfContents .= '<dl class="wikitoc"><dt> </dt><dd>';
    }
    while ( scalar @HeadingNumbers > $depth ) {
        pop @HeadingNumbers;
        $TableOfContents .= "</dd></dl>\n\n";
    }
    $HeadingNumbers[$#HeadingNumbers]++;
    $number = ( join '.', @HeadingNumbers ) . '. ';

    # Remove embedded links. THIS IS FRAGILE!
    $text = &RestoreSavedText($text);
    $text =~ s/\<a\s[^\>]*?\>\?\<\/a\>//si;        # No such page syntax
    $text =~ s/\<a\s[^\>]*?\>(.*?)\<\/a\>/$1/si;

    # Cook anchor by canonicalizing $text.
    $anchor = $text;
    $anchor =~ s/\<.*?\>//g;
    $anchor =~ s/\W/_/g;
    $anchor =~ s/__+/_/g;
    $anchor =~ s/^_//;
    $anchor =~ s/_$//;

    # Last ditch effort
    $anchor = '_' . ( join '_', @HeadingNumbers ) unless $anchor;
    $TableOfContents .=
      $number . &ScriptLink( "$OpenPageName#$anchor", $text ) . "</dd>\n<dt> </dt><dd>";
    return &StoreHref(" name=\"$anchor\"") . $number;
}

sub WikiHeading {
    my ( $pre, $depth, $text ) = @_;

    $depth = length($depth);
    $depth = 6 if ( $depth > 6 );
    $text =~ s/^\s*#\s+(.*)/&WikiHeadingNumber($depth,$1).$1/eo;    # $' == $POSTMATCH
    return $pre . "<h$depth>$text</h$depth>\n";
}

# ==== Difference markup and HTML ====
sub GetDiffHTML {
    my ( $diffType, $id,       $revOld,      $revNew,    $newText ) = @_;
    my ( $html,     $diffText, $diffTextTwo, $priorName, $links,    $usecomma );
    my ( $major,    $minor,    $author,      $useMajor,  $useMinor, $useAuthor, $cacheName );

    $links     = "(";
    $usecomma  = 0;
    $major     = &ScriptLinkDiff( 1, $id, T('major diff'),  "" );
    $minor     = &ScriptLinkDiff( 2, $id, T('minor diff'),  "" );
    $author    = &ScriptLinkDiff( 3, $id, T('author diff'), "" );
    $useMajor  = 1;
    $useMinor  = 1;
    $useAuthor = 1;
    $diffType  = &GetParam( "defaultdiff", 1 ) if ( $diffType == 4 );

    if ( $diffType == 1 ) {
        $priorName = T('major');
        $cacheName = 'major';
        $useMajor  = 0;
    } elsif ( $diffType == 2 ) {
        $priorName = T('minor');
        $cacheName = 'minor';
        $useMinor  = 0;
    } elsif ( $diffType == 3 ) {
        $priorName = T('author');
        $cacheName = 'author';
        $useAuthor = 0;
    }
    if ( $revOld ne "" ) {

# Note: OpenKeptRevisions must have been done by caller. Eventually optimize if same as cached revision
        $diffText = &GetKeptDiff( $newText, $revOld, 1 );    # 1 = get lock
        if ( $diffText eq "" ) {
            $diffText = T('(The revisions are identical or unavailable.)');
        }
    } else {
        $diffText = &GetCacheDiff($cacheName);
    }
    $useMajor  = 0 if ( $useMajor  && ( $diffText eq &GetCacheDiff("major") ) );
    $useMinor  = 0 if ( $useMinor  && ( $diffText eq &GetCacheDiff("minor") ) );
    $useAuthor = 0 if ( $useAuthor && ( $diffText eq &GetCacheDiff("author") ) );
    $useMajor  = 0
      if ( ( !defined( &GetPageCache('oldmajor') ) )
        || ( &GetPageCache("oldmajor") < 1 ) );
    $useAuthor = 0
      if ( ( !defined( &GetPageCache('oldauthor') ) )
        || ( &GetPageCache("oldauthor") < 1 ) );
    if ($useMajor) {
        $links .= $major;
        $usecomma = 1;
    }
    if ($useMinor) {
        $links .= ", " if ($usecomma);
        $links .= $minor;
        $usecomma = 1;
    }
    if ($useAuthor) {
        $links .= ", " if ($usecomma);
        $links .= $author;
    }
    if ( !( $useMajor || $useMinor || $useAuthor ) ) {
        $links .= T('no other diffs');
    }
    $links .= ")";
    if ( ( !defined($diffText) ) || ( $diffText eq "" ) ) {
        $diffText = T('No diff available.');
    }
    if ( $revOld ne "" ) {
        my $currentRevision = T('current revision');
        $currentRevision = Ts( 'revision %s', $revNew ) if $revNew;
        $html            = '<b>'
          . Tss( "Difference (from revision %1 to %2)", $revOld, $currentRevision )
          . "</b>\n"
          . "$links<br>"
          . &DiffToHTML($diffText);
    } else {
        if (
            ( $diffType != 2 )
            && (   ( !defined( &GetPageCache("old$cacheName") ) )
                || ( &GetPageCache("old$cacheName") < 1 ) )
          )
        {
            $html = '<b>'
              . Ts( 'No diff available--this is the first %s revision.', $priorName )
              . "</b>\n$links";
        } else {
            $html = '<b>'
              . Ts( 'Difference (from prior %s revision)', $priorName )
              . "</b>\n$links<br>"
              . &DiffToHTML($diffText);
        }
    }
    @HeadingNumbers  = ();
    $TableOfContents = '';
    if ( lc( &GetParam( 'action', '' ) ) ne 'history' ) {
        $html = '<div class="wikitext">' . $html . "</div>";
    }
    return $html;
}

sub GetCacheDiff {
    my ($type) = @_;
    my ($diffText);

    $diffText = &GetPageCache("diff_default_$type");
    $diffText = &GetCacheDiff('minor') if ( $diffText eq "1" );
    $diffText = &GetCacheDiff('major') if ( $diffText eq "2" );
    return $diffText;
}

# Must be done after minor diff is set and OpenKeptRevisions called
sub GetKeptDiff {
    my ( $newText, $oldRevision, $lock ) = @_;
    my ( $oldText, $inlinerev, $vmajor, $vminor );

    $oldText = "";
    ( $vmajor, $vminor ) = split( /\./, $oldRevision );
    if ( defined( $KeptRevisions{$vmajor} ) ) {

        # Stage 5: %KeptRevisions stores hashrefs. The "data" slot
        # is itself a hashref containing text/minor/newauthor/summary.
        my $kept = $KeptRevisions{$vmajor};
        if ( ref($kept) eq 'HASH' ) {
            my $data = $kept->{data};
            my $body =
              ref($data) eq 'HASH'
              ? $data->{text}
              : ( split( /$FS3/, $data, -1 ) )[1];    # legacy fallback
            ( $oldText, $inlinerev ) = &PatchPage( $body, $vminor );
        }
    }
    return "" if ( $oldText eq "" );                  # Old revision not found
    return &GetDiff( $oldText, $newText, $lock );
}

sub GetDiff {
    my ( $old, $new, $lock ) = @_;
    my ( $diff_out, $oldName, $newName, $key );

    require Text::Diff;
    return Text::Diff::diff( \$old, \$new, { STYLE => 'OldStyle' } );
}

sub PatchText {
    my ( $base, $patch, $lock ) = @_;
    my ( $patch_out, $oldName, $newName, $key );

    require Text::Patch;
    if ( $patch =~ /^\@\@/ ) {
        return Text::Patch::patch( $base, $patch, { STYLE => 'Unified' } );
    }
    return Text::Patch::patch( $base, $patch, { STYLE => 'OldStyle' } );
}

sub DiffToHTML {
    my ($html) = @_;
    my ( $tChanged, $tRemoved, $tAdded );

    $tChanged = T('Changed:');
    $tRemoved = T('Removed:');
    $tAdded   = T('Added:');
    if ( $html =~ /(^|\n)@@/ ) {
        $html =~ s/(\-\d+)(,(\d+))*/$tRemoved $1 $2/g;
        $html =~ s/(\+\d+)(,(\d+))*/$tAdded $1 $2/g;
        $html =~ s/(^|\n)@@ (.*) @@/$1 <br><strong>$2<\/strong><br>/g;
        $html =~ s/\n((\-.*\n)+)/&ColorDiff("$1", 0)/ge;
        $html =~ s/\n((\+.*\n)+)/&ColorDiff("$1", 1)/ge;
    } else {
        $html =~ s/\n--+//g;

        # Note: Need spaces before <br> to be different from diff section.
        $html =~ s/(^|\n)(\d+.*c.*)/$1 <br><strong>$tChanged $2<\/strong><br>/g;
        $html =~ s/(^|\n)(\d+.*d.*)/$1 <br><strong>$tRemoved $2<\/strong><br>/g;
        $html =~ s/(^|\n)(\d+.*a.*)/$1 <br><strong>$tAdded $2<\/strong><br>/g;
        $html =~ s/\n((<.*\n)+)/&ColorDiff($1, 0)/ge;
        $html =~ s/\n((>.*\n)+)/&ColorDiff($1, 1)/ge;
    }
    return $html;
}

sub ColorDiff {
    my ( $diff, $type ) = @_;
    my ( $colorHtml, $classHtml );

    $diff =~ s/(^|\n)[<>+-]/$1/g;
    $diff = &QuoteHtml($diff);

    # Do some of the Wiki markup rules:
    %$SaveUrl         = ();
    %$SaveNumUrl      = ();
    $$SaveUrlIndex    = 0;
    $$SaveNumUrlIndex = 0;
    $diff             = &RemoveFS($diff);
    $diff             = &CommonMarkup( $diff, 0, 1 );    # No images, all patterns
    if ( $LateRules ne '' ) {
        $diff = &EvalLocalRules( $LateRules, $diff, 1 );
    }
    1 while $diff =~ s/$FS(\d+)$FS/$$SaveUrl{$1}/ge;     # Restore saved text
    $diff =~ s/\r?\n/<br>/g;

    if ($type) {
        $classHtml = ' class="wikidiffnew"';
    } else {
        $classHtml = ' class="wikidiffold"';
    }
    return "\n<table width=\"95\%\"$classHtml><tr><td>\n" . $diff . "</td></tr></table>\n";
}

# ==== Database (Page, Section, Text, Kept, User) functions ====

sub OpenNewPage {
    my ($id) = @_;
    my ( $pagehash, $Page );

    $Page = \%{ $Pages{$id}->{'page'} };

    %$Page             = ();
    $$Page{'version'}  = 3;       # Data format version
    $$Page{'revision'} = 0;       # Number of edited times
    $$Page{'tscreate'} = $Now;    # Set once at creation
    $$Page{'ts'}       = $Now;    # Updated every edit
}

sub OpenNewSection {
    my ( $id, $name, $data ) = @_;
    my ( $Page, $Section );

    $Page    = \%{ $Pages{$id}->{'page'} };
    $Section = \%{ $Pages{$id}->{'section'} };

    %$Section             = ();
    $$Section{'name'}     = $name;
    $$Section{'version'}  = 1;                           # Data format version
    $$Section{'revision'} = 0;                           # Number of edited times
    $$Section{'tscreate'} = $Now;                        # Set once at creation
    $$Section{'ts'}       = $Now;                        # Updated every edit
    $$Section{'ip'}       = &RemoteAddr;
    $$Section{'host'}     = '';                          # Updated only for real edits (can be slow)
    $$Section{'id'}       = $UserID;
    $$Section{'username'} = &GetParam( "username", "" );
    $$Section{'data'}     = $data;

    # Snapshot the section into the page hash. Stage 5 cleanup: was
    # join($FS2, %$Section) — replaced with an anonymous-hash COPY so
    # subsequent edits to %$Section don't propagate to $Page{$name}
    # until SaveSection runs (same snapshot semantics as the prior
    # split-on-Open / join-on-Save round-trip, just without the byte
    # separator).
    $$Page{$name} = {%$Section};
}

sub OpenNewText {
    my ( $id, $name ) = @_;    # Name of text (usually "default")
    my ($Text);

    $Text = \%{ $Pages{$id}->{'text'} };

    %$Text = ();
    $$Text{'isnew'} = 1;
    if ( $NewText ne '' ) {
        $$Text{'text'} = T($NewText);
    } else {
        $$Text{'text'} = T('Describe the new page here.') . "\n";
    }
    $$Text{'text'} .= "\n" if ( substr( $$Text{'text'}, -1, 1 ) ne "\n" );
    $$Text{'minor'}     = 0;    # Default as major edit
    $$Text{'newauthor'} = 1;    # Default as new author
    $$Text{'summary'}   = '';

    # Pass the text hash directly; SaveSection stores it as a
    # hashref under $Section{data} (was: FS3-joined string).
    &OpenNewSection( $id, "text_$name", {%$Text} );
}

sub GetPageFile {
    my ($id) = @_;

    return $PageDir . "/" . &GetPageDirectory($id) . "/$id.db";
}

sub ReadLatestPageDB {
    my ( $id, $rev ) = @_;
    my @res;
    my (
        $pagedb,   $sth,     $maxversion, $pgid, $version, $author,
        $revision, $tupdate, $tcreate,    $ip,   $host,    $summary,
        $text,     $minor,   $newauthor,  $data
    );
    $pagedb = &GetPageDB($id);

    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("ReadLatestPageDB: unsafe table name") if ( !SafeIdent($pagedb) );
    if ( $rev eq "" ) {

        # ORDER BY ... LIMIT 1 is portable across SQLite and Postgres.
        # The historical "SELECT max(revision), *" was SQLite-only and
        # only happened to pull the matching row's columns by accident.
        $sth = $dbh->selectall_arrayref(
            "SELECT revision, * FROM $pagedb WHERE id=? ORDER BY revision DESC LIMIT 1",
            undef, $id );
    } else {
        $sth = $dbh->selectall_arrayref(
            "select revision,* from $pagedb where id=? and revision=? limit 1",
            undef, $id, $rev );
    }
    if ( defined $sth->[0] ) {
        (
            $maxversion, $pgid, $version, $author, $revision, $tupdate,   $tcreate,
            $ip,         $host, $summary, $text,   $minor,    $newauthor, $data
        ) = @{ $sth->[0] };
        if ( $pgid eq "" || $revision eq "" ) {
            return @res;
        } else {
            @res = (
                $maxversion, $pgid, $version, $author, $revision, $tupdate,   $tcreate,
                $ip,         $host, $summary, $text,   $minor,    $newauthor, $data
            );
        }
    }
    return @res;
}

sub OpenPageDB {
    my ($id) = @_;
    my ( $fname, $data, $pagedb, $sth );
    my (
        $pgid,        $version, $author,  $revision, $tupdate, $tcreate,
        $ip,          $host,    $summary, $text,     $minor,   $newauthor,
        $admin_saved, $Page,    $Text,    $Section
    );

    $Page    = \%{ $Pages{$id}->{'page'} };
    $Section = \%{ $Pages{$id}->{'section'} };
    $Text    = \%{ $Pages{$id}->{'text'} };

    if ( $OpenPageName eq $id ) {
        return;
    }
    $pagedb = &GetPageDB($id);

    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("OpenPageDB: unsafe table name") if ( !SafeIdent($pagedb) );

    # Explicit column list (was: `SELECT revision, *` with positional
    # unpacking). Explicit columns survive schema additions without
    # silently mis-binding — when admin_saved was added in this stage,
    # the old `*` would have shifted every variable in the assignment.
    $sth = $dbh->selectall_arrayref(
        "SELECT id, version, author, revision, tupdate, tcreate, ip, host, "
          . "summary, text, minor, newauthor, data, admin_saved "
          . "FROM $pagedb WHERE id=? ORDER BY revision DESC LIMIT 1",
        undef, $id
    );
    if ( defined $sth->[0] ) {
        (
            $pgid, $version, $author, $revision, $tupdate,   $tcreate, $ip,
            $host, $summary, $text,   $minor,    $newauthor, $data,    $admin_saved
        ) = @{ $sth->[0] };
        if ( $pgid eq "" || $revision eq "" ) {
            &OpenNewPage($id);
            &OpenNewText( $id, 'default' );
        } else {
            $$Page{'name'}        = $pgid;
            $$Page{'version'}     = $version;
            $$Page{'revision'}    = $revision;
            $$Page{'tscreate'}    = $tcreate;
            $$Page{'ts'}          = $tupdate;
            $$Page{'admin_saved'} = $admin_saved || 0;

            $$Section{'name'}     = 'text_default';
            $$Section{'version'}  = $version;
            $$Section{'revision'} = $revision;
            $$Section{'tscreate'} = $tcreate;
            $$Section{'ts'}       = $tupdate;
            $$Section{'ip'}       = $ip;
            $$Section{'host'}     = $host;
            $$Section{'username'} = $author;

            $$Text{'text'}      = $text;
            $$Text{'newauthor'} = $newauthor;
            $$Text{'minor'}     = $minor;
            $$Text{'summary'}   = $summary;

            # Stage 5: snapshot via hashref (was: FS3/FS2-joined string).
            $$Section{'data'} = {%$Text};
            $$Page{ $$Section{'name'} } = {%$Section};
        }
    } else {    # open new page
        &OpenNewPage($id);
        &OpenNewText( $id, 'default' );
    }
    if ( $$Page{'version'} != 3 ) {
        &UpdatePageVersion();
    }
    $OpenPageName = $id;
}

sub OpenSection {
    my ( $id, $name ) = @_;
    my ( $Page, $Section );

    $Page    = \%{ $Pages{$id}->{'page'} };
    $Section = \%{ $Pages{$id}->{'section'} };

    if ( !defined( $$Page{$name} ) ) {
        &OpenNewSection( $id, $name, "" );
    } elsif ( ref( $$Page{$name} ) eq 'HASH' ) {

        # Stage 5 in-memory shape: hashref. Copy out into $Section.
        %$Section = %{ $$Page{$name} };
    } else {

        # Legacy form may show up if some external caller stuffed an
        # FS2-joined string into the page hash; tolerate it.
        %$Section = split( /$FS2/, $$Page{$name}, -1 );
    }
}

sub OpenText {
    my ( $id, $name ) = @_;
    my ( $Page, $Section, $Text );

    $Page    = \%{ $Pages{$id}->{'page'} };
    $Section = \%{ $Pages{$id}->{'section'} };
    $Text    = \%{ $Pages{$id}->{'text'} };

    if ( !defined( $$Page{"text_$name"} ) ) {
        &OpenNewText( $id, $name );
    } else {
        &OpenSection( $id, "text_$name" );
        if ( ref( $$Section{'data'} ) eq 'HASH' ) {
            %$Text = %{ $$Section{'data'} };
        } else {
            %$Text = split( /$FS3/, $$Section{'data'}, -1 );
        }
    }
}

sub OpenDefaultText {
    my ($id) = @_;
    &OpenText( $id, 'default' );
}

# Called after OpenKeptRevisions
sub OpenKeptRevision {
    my ( $id, $revision, $inlinerev ) = @_;
    my ( $Text, $Section );

    $Section = \%{ $Pages{$id}->{'section'} };
    $Text    = \%{ $Pages{$id}->{'text'} };

    # Stage 5: %KeptRevisions stores hashrefs (not FS-joined strings).
    my $kept = $KeptRevisions{$revision};
    return if ( !defined($kept) || ref($kept) ne 'HASH' );
    %$Section = %$kept;
    if ( ref( $$Section{'data'} ) eq 'HASH' ) {
        %$Text = %{ $$Section{'data'} };
    } else {
        %$Text = split( /$FS3/, $$Section{'data'}, -1 );    # legacy form, safety
    }
    ( $$Text{'text'}, $inlinerev ) = &PatchPage( $$Text{'text'}, $inlinerev );
}

sub GetPageCache {
    my ($name) = @_;

    return $Pages{$OpenPageName}->{'page'}->{"cache_$name"};
}

sub SavePageDB {
    my ($name) = @_;
    my ( $Page, $Text, $Section );

    $Page    = \%{ $Pages{$name}->{'page'} };
    $Section = \%{ $Pages{$name}->{'section'} };
    $Text    = \%{ $Pages{$name}->{'text'} };

    my $pagedb = &GetPageDB($name);
    my $revdb  = "${pagedb}_revisions";

    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("SavePageDB: unsafe table name") if ( !SafeIdent($pagedb) );
    die("SavePageDB: unsafe table name") if ( !SafeIdent($revdb) );
    $$Page{'name'} = $name;

    # Read the previous current row (if any) so we can archive it
    # before we overwrite. The new revision is current_rev + 1.
    my $cur_row = $dbh->selectrow_arrayref(
        "SELECT revision, version, author, tupdate, tcreate, ip, host, summary, "
          . "text, minor, newauthor, data FROM $pagedb WHERE id=?",
        undef, $name
    );

    my $cur_rev = 0;
    my $cur_tcreate;
    if ( defined $cur_row ) {
        $cur_rev     = $cur_row->[0];
        $cur_tcreate = $cur_row->[4];

        # Archive the previous revision into page_revisions. Stage 6:
        # store as a REVERSE DIFF against the new current — applying
        # the diff to the new current's text yields the previous
        # current's text. Fall back to a full-text snapshot if diff
        # storage would be larger than the snapshot (radical rewrite
        # of small content, etc.).
        my $cur_text = $cur_row->[8];
        my $new_text = $$Text{'text'};
        my ( $kind, $body ) = ( 'snapshot', $cur_text );

        if ( $UseDiff && defined($new_text) && defined($cur_text) ) {
            require Text::Diff;    # outside the eval: a missing module must not degrade silently
            my $diff = eval { Text::Diff::diff( \$new_text, \$cur_text, { STYLE => 'Unified' } ); };
            if ( !$@ && defined($diff) && length($diff) < length($cur_text) ) {
                $kind = 'diff';
                $body = $diff;
            }
        }

        WriteDBItems(
            $revdb,
            "page_id,revision,version,author,tupdate,tcreate,ip,host,"
              . "summary,minor,newauthor,data,kind,text",
            0,                 # plain insert; (page_id, revision) PK guards dupes
            $name,
            $cur_row->[0],     # revision
            $cur_row->[1],     # version
            $cur_row->[2],     # author
            $cur_row->[3],     # tupdate
            $cur_row->[4],     # tcreate
            $cur_row->[5],     # ip
            $cur_row->[6],     # host
            $cur_row->[7],     # summary
            $cur_row->[9],     # minor
            $cur_row->[10],    # newauthor
            $cur_row->[11],    # data
            $kind,
            $body,
        );
    }

    my $new_rev = $cur_rev + 1;
    $$Page{'revision'}    = $new_rev;
    $$Section{'revision'} = $new_rev;

    my $tcreate = $cur_tcreate || $$Page{'tscreate'} || $Now;
    my $tupdate = $Now;

    # Per-page trust flag for the raw-HTML bypass: scrub is skipped at
    # render time iff this is 1 and the page is rendered via WikiToHTML.
    # Captured at save time from the saver's admin status, not derived
    # later — so demoting the admin password invalidates trust on the
    # next save, never retroactively.
    my $admin_saved = UserIsAdmin() ? 1 : 0;
    $$Page{'admin_saved'} = $admin_saved;

    # Upsert the current snapshot. UPSERT semantics: REPLACE INTO on
    # SQLite, INSERT ... ON CONFLICT (id) DO UPDATE on Postgres.
    WriteDBItems(
        $pagedb,
        "id,revision,version,author,tupdate,tcreate,ip,host,"
          . "summary,text,minor,newauthor,data,admin_saved",
        1,    # upsert on id
        $name,
        $new_rev,
        $$Page{'version'},
        $UserData{'username'},
        $tupdate,
        $tcreate,
        $$Section{'ip'},
        $$Section{'host'},
        $$Text{'summary'},
        $$Text{'text'},
        $$Text{'minor'},
        $$Text{'newauthor'},
        $UserData{'id'},
        $admin_saved,
    );
    &PurgeStaticCache();    # any page change can alter pages that embed or inherit it
}

sub SaveSection {
    my ( $name, $data ) = @_;
    my ( $Section, $Page );

    $Section = \%{ $Pages{$OpenPageName}->{'section'} };
    $Page    = \%{ $Pages{$OpenPageName}->{'page'} };

    $$Section{'revision'} += 1;                            # Number of edited times
    $$Section{'ts'}       = $Now;                          # Updated every edit
    $$Section{'ip'}       = &RemoteAddr;
    $$Section{'id'}       = $UserID;
    $$Section{'username'} = &GetParam( "username", "" );
    $$Section{'data'}     = $data;

    # Hash copy (was: FS2-joined string).
    $$Page{$name} = {%$Section};
}

sub SaveText {
    my ( $id, $name ) = @_;

    # Pass text hash as a copy (was: FS3-joined string).
    &SaveSection( "text_$name", { %{ $Pages{$id}->{'text'} } } );
}

sub SaveDefaultText {
    my ($id) = @_;

    &SaveText( $id, 'default' );
}

sub SetPageCache {
    my ( $name, $data ) = @_;

    $Pages{$OpenPageName}->{'page'}->{"cache_$name"} = $data;
}

sub UpdatePageVersion {
    &ReportError( T('Bad page version (or corrupt page).') );
}

sub OpenKeptListDB {
    my ($nopatch) = @_;
    my $pagedb    = &GetPageDB($OpenPageName);
    my $revdb     = "${pagedb}_revisions";
    my @KeptList;
    my $moretocome = '';

    die("OpenKeptListDB: unsafe table name") if ( !SafeIdent($pagedb) );
    die("OpenKeptListDB: unsafe table name") if ( !SafeIdent($revdb) );

    my $lim    = int( GetParam( 'listc',  $HistoryLimit ) ) + 1;
    my $offset = int( GetParam( 'offset', 0 ) );

    # Stage 5: revision history is split across two tables. The
    # current revision lives in `page`; older revisions in
    # `page_revisions` (kind='snapshot' or 'diff'). UNION-merge them
    # ordered by revision and apply the same paging the legacy code
    # did via LIMIT/OFFSET.
    my $cur_cols =
        "id AS page_id, revision, version, author, tupdate, "
      . "tcreate, ip, host, summary, minor, newauthor, data, "
      . "'snapshot' AS kind, text";
    my $rev_cols =
        "page_id, revision, version, author, tupdate, "
      . "tcreate, ip, host, summary, minor, newauthor, data, "
      . "kind, text";
    my $sql =
        "SELECT $cur_cols FROM $pagedb WHERE id=? "
      . "UNION ALL "
      . "SELECT $rev_cols FROM $revdb WHERE page_id=? "
      . "ORDER BY revision DESC LIMIT $lim";
    $sql .= " OFFSET $offset" if ( $offset > 0 );

    my $sth = $dbh->selectall_arrayref( $sql, undef, $OpenPageName, $OpenPageName );

    # Stage 6: rows can carry kind='diff' (reverse-diff against the
    # immediately-higher revision's text) or kind='snapshot' (full
    # text). Walking the result DESC and applying diffs incrementally
    # reconstructs each revision's text in a single O(n) pass. A
    # diff that fails to apply (corruption, partial chain) falls back
    # to its raw body so the row is still listable.
    my $running_text;

    if ( defined $sth->[0] ) {
        if ( @{$sth} == $lim ) {
            pop( @{$sth} );
            $moretocome = "+";
        }
        foreach my $rec ( @{$sth} ) {
            my (
                $pgid, $revision, $version, $author,    $tupdate, $tcreate, $ip,
                $host, $summary,  $minor,   $newauthor, $data,    $kind,    $text
            ) = @$rec;
            next if ( !defined($pgid) || $pgid eq "" || !defined($revision) || $revision eq "" );

            # Materialize this revision's text. The first row (highest
            # revision) is always a snapshot (the current `page.text`).
            # Subsequent rows are either snapshots or diffs from the
            # row immediately above.
            my $resolved;
            if ( !defined($running_text) ) {
                $resolved = $text;    # first iteration = current
            } elsif ( $kind eq 'diff' ) {
                require Text::Patch;    # outside the eval: never show a raw diff as page text
                $resolved =
                  eval { Text::Patch::patch( $running_text, $text, STYLE => 'Unified' ); };
                $resolved = $text if ( $@ || !defined($resolved) );
            } else {
                $resolved = $text;    # snapshot
            }
            $running_text = $resolved;

            $KeptList[$revision] = {
                name     => "text_default",
                version  => $version,
                revision => $revision,
                tscreate => $tcreate,
                ts       => $tupdate,
                ip       => $ip,
                host     => $host,
                id       => $data,
                username => $author,
                kind     => $kind,
                data     => {
                    text      => $resolved,
                    minor     => $minor,
                    newauthor => $newauthor,
                    summary   => $summary,
                },
            };
        }
    }
    return ( "Internal:Offset:$offset$moretocome", @KeptList );
}

sub OpenKeptRevisions {
    my ( $id, $name, $nopatch ) = @_;
    my @KeptList = &OpenKeptListDB($nopatch);
    %KeptRevisions = ();
    foreach my $rev (@KeptList) {
        next if ( !defined($rev) || $rev eq '' );

        # Stage 5: list elements are hashrefs; the offset sentinel is
        # the only string that can appear (it's the first element).
        if ( !ref($rev) && $rev =~ /^Internal:Offset:([0-9]+[+]*)/ ) {
            $KeptRevisions{"Internal:Offset"} = $1;
            next;
        }
        next unless ( ref($rev) eq 'HASH' );
        next if ( $rev->{name} ne $name );
        $KeptRevisions{ $rev->{revision} } = $rev;
    }
}

sub LoadUserDataDB {
    my ( $uid, $uname ) = @_;
    $uname    = '' if ( !defined($uname) );
    %UserData = ();
    my $userdb = DBTable($UserDir);
    my $sth;
    my (
        $id,         $name,      $pass,     $group,    $lang,       $email,      $param,
        $createtime, $extradata, $createip, $tzoffset, $pagecreate, $pagemodify, %extra
    );

    if ( $dbh eq "" || $userdb eq "" ) {
        return T('ERROR: database uninitialized!');
    }
    die("LoadUserDataDB: unsafe table name") if ( !SafeIdent($userdb) );

    # Explicit column list — Stage 5 dropped randkey from the schema,
    # so `SELECT *` ordinal-unpacking would shift. Naming columns
    # explicitly also lets us reorder fields freely in the future.
    # Note: the `stylesheet` column was renamed to `prefs` and the
    # contents switched from $FS2-joined to JSON in Stage 5.
    my $cols = "id,name,pass,groupid,lang,email,param,createtime,"
      . "prefs,createip,tzoffset,pagecreate,pagemodify";

    if ( $uname eq "" ) {
        $uid = int($uid);
        $sth =
          $dbh->selectall_arrayref( "SELECT $cols FROM $userdb WHERE id=? LIMIT 1", undef, $uid );
    } else {
        # Case-insensitive exact match. Was `LIKE ?`: case-insensitive on
        # SQLite but case-sensitive under MariaDB's utf8mb4_bin, and it
        # treated % and _ in the typed name as wildcards.
        if ( $uname =~ /\@/ ) {
            $sth = $dbh->selectall_arrayref(
                "SELECT $cols FROM $userdb WHERE UPPER(email)=UPPER(?) LIMIT 1",
                undef, $uname );
        } else {
            $sth = $dbh->selectall_arrayref(
                "SELECT $cols FROM $userdb WHERE UPPER(name)=UPPER(?) LIMIT 1",
                undef, $uname );
        }
    }
    if ( !defined $sth->[0] ) {
        if ( $UserID < 1000 ) {
            return T("ERROR: can not find the specified user");
        } else {
            return -1;    # new user
        }
    } else {
        (
            $id,       $name,       $pass,       $group,     $lang,
            $email,    $param,      $createtime, $extradata, $createip,
            $tzoffset, $pagecreate, $pagemodify
        ) = @{ $sth->[0] };

        # `prefs` is JSON (Stage 5); legacy rows from before the
        # migration may still carry the $FS2-joined form, accept both.
        if ( defined($extradata) && $extradata ne '' ) {
            if ( $extradata =~ /^\s*\{/ ) {
                require JSON::PP;
                my $h = eval { JSON::PP::decode_json($extradata) };
                %extra = %$h if ( !$@ && ref($h) eq 'HASH' );
            } else {
                %extra = split( /$FS2/, $extradata );
            }
        }
    }
    $UserData{'id'}           = $id;
    $UserData{'username'}     = $name;
    $UserData{'password'}     = $pass;
    $UserData{'adminpw'}      = $group;
    $UserData{'lang'}         = $lang;
    $UserData{'email'}        = $email;
    $UserData{'param'}        = $param;
    $UserData{'createtime'}   = $createtime;
    $UserData{'createip'}     = $createip;
    $UserData{'tzoffset'}     = $tzoffset;
    $UserData{'pagecreate'}   = $pagecreate;
    $UserData{'pagemodify'}   = $pagemodify;
    $UserData{'stylesheet'}   = $extra{'stylesheet'};
    $UserData{'rcdays'}       = $extra{'rcdays'};
    $UserData{'rcnewtop'}     = $extra{'rcnewtop'};
    $UserData{'rcchangehist'} = $extra{'rcchangehist'};
    $UserData{'rcshowedit'}   = $extra{'rcshowedit'};
    $UserData{'tzoffset'}     = $extra{'tzoffset'};
    $UserData{'editrows'}     = $extra{'editrows'};
    $UserData{'editcols'}     = $extra{'editcols'};
    $UserData{'norcdiff'}     = $extra{'norcdiff'};
    $UserData{'diffrclink'}   = $extra{'diffrclink'};
    $UserData{'alldiff'}      = $extra{'alldiff'};
    $UserData{'defaultdiff'}  = $extra{'defaultdiff'};

    # Registration profile; prefs keys match the legacy NeuroJSON wiki
    # so migrated accounts keep their data.
    $UserData{'firstname'} = $extra{'fn'};
    $UserData{'lastname'}  = $extra{'sn'};
    $UserData{'inst'}      = $extra{'inst'};
    $UserData{'area'}      = $extra{'area'};
    return "";

    # need to print log
}

# ==== Misc. functions ====
sub ReportError {
    my ($errmsg) = @_;

    print $q->header, "<h2>", $errmsg, "</h2>", $q->end_html;
}

sub ValidId {
    my ($id) = @_;

    if ( length($id) > 120 ) {
        return Ts( 'Page name is too long: %s', $id );
    }
    if ( $id =~ m| | ) {
        return Ts( 'Page name may not contain space characters: %s', $id );
    }
    if ($UseSubpage) {
        if ( $id =~ /^\// ) {
            return Ts( 'Invalid Page %s (subpage without main page)', $id );
        }
        if ( $id =~ /\/$/ ) {
            return Ts( 'Invalid Page %s (missing subpage name)', $id );
        }
    }
    if ($FreeLinks) {
        $id =~ s/ /_/g;
        if ( !$UseSubpage ) {
            if ( $id =~ /\// ) {
                return Ts( 'Invalid Page %s (/ not allowed)', $id );
            }
        }
        if ( !( $id =~ m|^$FreeLinkPattern$| ) ) {

            #      return Ts('Invalid Page %s %s', $id,$FreeLinkPattern);
            return Ts( 'Invalid Page %s', $FreeLinkPattern );
        }
        if ( $id =~ m|\.db$| ) {
            return Ts( 'Invalid Page %s (must not end with .db)', $id );
        }
        if ( $id =~ m|\.lck$| ) {
            return Ts( 'Invalid Page %s (must not end with .lck)', $id );
        }
        return "";
    } else {
        if ( !( $id =~ /^$LinkPattern$/ ) ) {
            return Ts( 'Invalid Page %s', $id );
        }
    }
    return "";
}

sub ValidIdOrDie {
    my ($id) = @_;
    my $error;

    $error = &ValidId($id);
    if ( $error ne "" ) {
        &ReportError($error);
        return 0;
    }
    return 1;
}

sub UserCanEdit {
    my ( $id, $deepCheck ) = @_;
    my ( $permit, $clearance );

    $clearance = &UserPermission();
    if ( $id =~ /\/\./ ) {
        return 0 if ( $clearance < 100 );    # Requires more privledges
    }

    # Optimized for the "everyone can edit" case (don't check passwords)
    if ( ( $id ne "" ) && ( IsPageLocked($id) ) ) {
        return 1 if ( $clearance == 100 );   # Requires more privledges
                                             # Consider option for editor-level to edit these pages?
        return 0;
    }

    # %EditPermissions: page-name pattern => minimum clearance to EDIT.
    # It only restricts (checked before any grant below), so pages can be
    # readable by everyone through %Permissions yet editable by few.
    my $need = ReadPagePermissions( $id, \%EditPermissions );
    return 0 if ( $need ne '' && $clearance < $need );

    $permit = ReadPagePermissions( $id, \%Permissions );
    if ( $permit ne '' && $clearance >= $permit ) {
        return 1;
    }
    if ( defined $PermEditAllowed ) {
        return 1 if ( $clearance >= $PermEditAllowed );
        return 0;
    }
    return 0;
}

sub UserIsBanned {
    my ( $host, $ip, $data, $status );
    $data   = ReadDBItems( Habitat::Store::T("system"), 'data', "\n", '', "id=?", 'banlist' );
    $status = 1;
    return 0 if ( !$status );    # No file exists, so no ban
    $data =~ s/\r//g;
    $ip   = &RemoteAddr;
    $host = &GetRemoteHost(0);
    foreach ( split( /\n/, $data ) ) {
        next     if ( (/^\s*$/) || (/^#/) );    # Skip empty, spaces, or comments
        return 1 if ( $ip   =~ /$_/i );
        return 1 if ( $host =~ /$_/i );
    }
    return 0;
}

sub UserPermission {
    my $up;
    if ( defined( $UserData{'clearance'} ) ) {
        return $UserData{'clearance'};
    }
    if ( UserIsAdmin() ) {
        $up = 100;
    } elsif ( UserIsBanned() ) {
        $up = -100;
    } elsif ( UserIsEditor() ) {
        $up = 50;
    } elsif ( $UserID > 1000 && defined( $UserData{'id'} ) && $UserData{'id'} ne '' ) {
        $up = 1;
    } else {
        $up = -1;
    }
    $UserData{'clearance'} = $up;
    return $up;
}

sub UserIsAdmin {
    my ($stored);
    return 0 if ( $AdminPass eq "" );
    $stored = &GetParam( "adminpw", "" );
    return 0 if ( $stored eq "" );
    foreach my $token ( split( /\s+/, $AdminPass ) ) {
        next     if ( $token eq "" );
        return 1 if ( VerifyPassword( $token, $stored ) );
    }
    return 0;
}

# $RegistrationPermission as 'user', 'editor' or 'admin'; anything else
# counts as 'admin' (the most restrictive).
sub RegistrationLevel {
    my $l = lc( $RegistrationPermission // 'editor' );
    return ( $l eq 'user' || $l eq 'editor' ) ? $l : 'admin';
}

# May an account be created with registration token $tok? The token is
# only compared, never stored: it does not give the new account rights.
sub RegistrationTokenOK {
    my ($tok) = @_;
    my $level = &RegistrationLevel();
    return 1 if ( $level eq 'user' );
    return 0 if ( !defined($tok) || $tok eq '' );
    my $ok = 0;
    my $pool = ( $level eq 'admin' ) ? $AdminPass : "$AdminPass $EditPass";
    foreach my $t ( split( /\s+/, $pool ) ) {
        next if ( $t eq '' );
        $ok = 1 if ( ConstantEq( $t, $tok ) );
    }
    return $ok;
}

sub UserIsEditor {
    my ($stored);
    return 1 if ( &UserIsAdmin() );    # Admin includes editor
    return 0 if ( $EditPass eq "" );
    $stored = &GetParam( "adminpw", "" );
    return 0 if ( $stored eq "" );
    foreach my $token ( split( /\s+/, $EditPass ) ) {
        next     if ( $token eq "" );
        return 1 if ( VerifyPassword( $token, $stored ) );
    }
    return 0;
}

sub UserCanUpload {
    return 1 if ( &UserPermission() >= $PermUseUpload );
    return $AllUpload;
}

sub WriteStringToFile {
    my ( $file, $string ) = @_;

    open( OUT, ">$file" ) or die( Ts( 'cant write %s', $file ) . ": $!" );
    print OUT $string;
    close(OUT);
}

sub GetLockedPageFile {
    my ($id) = @_;
    return $PageDir . "/" . &GetPageDirectory($id) . "/$id.lck";
}

# Named locks were directories under $LockDir for the flat-file store;
# with the database store (now the only one) they always succeeded and
# the database does the locking. Removing these with the flat-file code
# left RequestLock calling an undefined sub, so every save died.
sub RequestLockDir { return 1; }
sub ReleaseLockDir { return 1; }

sub RequestLock {

    # 10 tries, 3 second wait, possibly die on error
    return &RequestLockDir( "main", 10, 3, $LockCrash );
}

sub ReleaseLock {
    &ReleaseLockDir('main');
}

sub ForceReleaseLock {
    my ($name) = @_;
    my $forced;

# First try to obtain lock (in case of normal edit lock) 5 tries, 3 second wait, do not die on error
    $forced = !&RequestLockDir( $name, 5, 3, 0 );
    &ReleaseLockDir($name);    # Release the lock, even if we didn't get it.
    return $forced;
}

sub RequestCacheLock {

    # 4 tries, 2 second wait, do not die on error
    return &RequestLockDir( 'cache', 4, 2, 0 );
}

sub ReleaseCacheLock {
    &ReleaseLockDir('cache');
}

sub RequestDiffLock {

    # 4 tries, 2 second wait, do not die on error
    return &RequestLockDir( 'diff', 4, 2, 0 );
}

sub ReleaseDiffLock {
    &ReleaseLockDir('diff');
}

# Index lock is not very important--just return error if not available
sub RequestIndexLock {

    # 1 try, 2 second wait, do not die on error
    return &RequestLockDir( 'index', 1, 2, 0 );
}

sub ReleaseIndexLock {
    &ReleaseLockDir('index');
}

sub ReadFile {
    my ($fileName) = @_;
    my ($data);
    local $/ = undef;    # Read complete files

    if ( open( IN, "<$fileName" ) ) {
        $data = <IN>;
        close IN;
        return ( 1, $data );
    }
    return ( 0, "" );
}

sub UpdateHtmlCacheDB {
    my ( $id, $html ) = @_;
    my $htmldb = DBTable($HtmlDir);
    my ( $sth, $language );
    $language = &GetParam( 'lang', $LangID );

    if ( $dbh eq "" || $htmldb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("UpdateHtmlCacheDB: unsafe table name") if ( !SafeIdent($htmldb) );
    $sth = $dbh->prepare("replace into $htmldb (id,time,text) values (?,?,?)");
    $sth->execute( "$id\[$language\]", $Now, $html );

    # need to print log
}

# ----------------------------------------------------------------
# Static page cache (served by Apache via mod_rewrite, no Perl).
#
# When $StaticCacheDir is set, the anonymous rendering of a plain page
# view is also written to
#     $StaticCacheDir/p/<PageId>.html   for  GET index.cgi?PageId
#     $StaticCacheDir/front.html        for  GET index.cgi  (home page)
# and .htaccess rewrite rules (see DEPLOYMENT.md) serve those files
# directly when the visitor has no wiki cookie. Under plain CGI that
# skips process start, compiling and the database entirely.
#
# Correctness rules:
#  - only the exact request the rewrite answers is written (GET, query
#    string == page id or empty, no wiki cookie, anonymous), so a file
#    never holds another language, revision or user's view;
#  - any write to the wiki purges the whole cache (SavePageDB,
#    DeletePage, RenamePage, every CSRF-verified POST): pages embed
#    other pages and inherit rule pages, so per-page invalidation
#    would miss dependents;
#  - a change to the config, translation file or engine purges it too
#    (StaticCacheCheckStamp, a few stat() calls per request);
#  - a generation counter stops a render that began before a purge
#    from writing its stale result after it.
# ----------------------------------------------------------------

# Page ids eligible for the static cache. Must accept exactly what the
# QUERY_STRING pattern of the .htaccess rules accepts. Every segment
# starts with a letter or digit, so ".." and rule pages (".v0") can
# never form a path.
our $StaticCachePageRe = qr{\A[A-Za-z0-9][A-Za-z0-9_.,()'-]*(?:/[A-Za-z0-9][A-Za-z0-9_.,()'-]*)*\z};

# Cache file for page $id if *this request* is one the rewrite serves.
sub StaticCacheFile {
    my ($id) = @_;
    return '' if ( !defined($StaticCacheDir) || $StaticCacheDir eq '' || !defined($id) );
    my $qs = $ENV{'QUERY_STRING'} // '';
    if ( $qs eq '' ) {
        return ( $id eq $HomePage ) ? "$StaticCacheDir/front.html" : '';
    }
    return '' if ( $qs ne $id || $id !~ $StaticCachePageRe );
    return "$StaticCacheDir/p/$id.html";
}

sub StaticCacheGeneration {
    return '' if ( !defined($StaticCacheDir) || $StaticCacheDir eq '' );
    my $fh;
    open( $fh, '<', "$StaticCacheDir/.gen" ) or return '';
    my $g = <$fh>;
    close($fh);
    return defined($g) ? $g : '';
}

sub _StaticCacheWriteAtomic {
    my ( $file, $content ) = @_;
    my $tmp = "$file.tmp$$";
    my $fh;
    open( $fh, '>', $tmp ) or return 0;
    binmode($fh);
    print $fh $content;
    close($fh) or do { unlink $tmp; return 0 };
    chmod( 0604, $tmp );
    rename( $tmp, $file ) or do { unlink $tmp; return 0 };
    return 1;
}

sub WriteStaticCache {
    my ( $id, $html ) = @_;
    return if ( !defined($StaticCacheDir) || $StaticCacheDir eq '' || !$StaticCacheOK );
    return if ( ( $ENV{'REQUEST_METHOD'} // '' ) ne 'GET' );
    return if ( $UserID != 111 || ( defined( $UserData{'username'} ) && $UserData{'username'} ne '' ) );
    return if ( ( $ENV{'HTTP_COOKIE'} // '' ) =~ /(?:^|;\s*)\Q$CookieName\E=/ );
    return if ( $ConfigError ne '' );
    return if ( defined( $Pages{$id}->{'expire'} ) && $Pages{$id}->{'expire'} ne '' );
    return if ( !&PageExists($id) && !( defined $BuildinPages{$id} && $BuildinPages{$id} ne '' ) );
    my $file = &StaticCacheFile($id);
    return if ( $file eq '' );

    # $html normally starts with the CGI header block (absent if headers
    # were already printed earlier in the request); the file is the body
    # only. Never store a response that sets a cookie.
    if ( $html =~ s/\A((?:[A-Za-z][\w-]*:[^\r\n]*\r?\n)+)\r?\n//s ) {
        return if ( $1 =~ /^Set-Cookie:/mi );
    }
    return if ( $html !~ /\A\s*<!DOCTYPE/i );

    my $gen = $StaticCacheGen // '';
    return if ( &StaticCacheGeneration() ne $gen );    # purged since rendering began
    require File::Path;
    my ($dir) = $file =~ m{\A(.*)/[^/]+\z};
    eval { File::Path::make_path( $dir, { mode => 0705 } ) };
    return if ( !-d $dir );
    &_StaticCacheWriteAtomic( $file, $html ) or return;

    # A purge between the check above and the rename would leave a stale
    # file behind; re-check and drop it if so.
    unlink($file) if ( &StaticCacheGeneration() ne $gen );
}

sub PurgeStaticCache {
    return if ( !defined($StaticCacheDir) || $StaticCacheDir eq '' || !-d $StaticCacheDir );

    # New generation first, so renders already in flight won't write.
    &_StaticCacheWriteAtomic( "$StaticCacheDir/.gen", RandomHex(8) );
    unlink("$StaticCacheDir/front.html");
    if ( -d "$StaticCacheDir/p" ) {
        my $trash = "$StaticCacheDir/.trash-$$-" . RandomHex(4);
        rename( "$StaticCacheDir/p", $trash );
    }

    # Delete this purge's trash and any left behind by an earlier purge
    # that was interrupted. (File::Path::remove_tree chdir()s while it
    # works and silently left whole trees behind under Apache CGI on the
    # NeuroJSON host; _StaticCacheRmTree uses absolute paths only.)
    if ( opendir( my $dh, $StaticCacheDir ) ) {
        my @trash = grep { /\A\.trash-[\w-]+\z/ } readdir($dh);
        closedir($dh);
        &_StaticCacheRmTree("$StaticCacheDir/$_") for @trash;
    }
    $StaticCacheGen = '';    # this request no longer has a valid generation
}

# Recursive delete without chdir: absolute paths, never follows symlinks.
sub _StaticCacheRmTree {
    my ($path) = @_;
    if ( -l $path || !-d _ ) {
        unlink($path) or warn "static cache: cannot delete $path: $!\n";
        return;
    }
    if ( opendir( my $dh, $path ) ) {
        my @e = grep { $_ ne '.' && $_ ne '..' } readdir($dh);
        closedir($dh);
        &_StaticCacheRmTree("$path/$_") for @e;
    }
    rmdir($path) or warn "static cache: cannot remove $path: $!\n";
}

# Purge when the config, translation file or engine changed since the
# cache was built (they change the HTML of every page).
sub StaticCacheCheckStamp {
    return if ( !defined($StaticCacheDir) || $StaticCacheDir eq '' || !-d $StaticCacheDir );
    my @files = ( $ConfigFile, "$DataDir/i18n/lang.$LangID", __FILE__,
        grep { defined } map { $INC{"Habitat/$_.pm"} } qw(Render Store Auth) );
    my $stamp = join( ',', map { ( stat($_) )[9] // 0 } @files );
    my $old   = '';
    if ( open( my $fh, '<', "$StaticCacheDir/.stamp" ) ) {
        $old = <$fh> // '';
        close($fh);
    }
    return if ( $old eq $stamp );
    &PurgeStaticCache();
    &_StaticCacheWriteAtomic( "$StaticCacheDir/.stamp", $stamp );
}

sub GenerateAllPagesListDB {
    my @pages;
    my $pagedb = GetParam( "dbprefix", "" ) . DBTable($PageDir);
    my ( $sth, $pg, $lim, $offset, $searchcmd );

    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("GenerateAllPagesListDB: unsafe table name") if ( !SafeIdent($pagedb) );
    $lim       = int( GetParam( 'listc',  $ListItemCount ) ) + 1;
    $offset    = int( GetParam( 'offset', 0 ) );
    $searchcmd = "select id from $pagedb group by id limit $lim";
    $searchcmd .= " offset $offset" if ( $offset > 0 );
    $sth = $dbh->selectall_arrayref($searchcmd);
    foreach $pg ( @{$sth} ) {
        push( @pages, $pg->[0] );
    }
    if ( @pages == $lim ) {
        pop(@pages);
        @pages = sort (@pages);
        return ( "Internal:Offset:$offset+", @pages );
    }
    @pages = sort (@pages);
    return ( "Internal:Offset:$offset", @pages );

    # need to print log
}

sub AllPagesList {
    my ( $rawIndex, $refresh, $status );

    return &GenerateAllPagesListDB();
}

sub CalcDay {
    my ($ts) = @_;

    $ts += ( $TimeZoneOffset || 0 );
    my ( $sec, $min, $hour, $mday, $mon, $year ) = localtime($ts);
    if ($NumberDates) {
        return ( $year + 1900 ) . '-' . ( $mon + 1 ) . '-' . $mday;
    }
    return (
        "January", "February", "March",     "April",   "May",      "June",
        "July",    "August",   "September", "October", "November", "December"
    )[$mon]
      . " "
      . $mday . ", "
      . ( $year + 1900 );
}

sub CalcDayNum {
    my ($ts) = @_;

    $ts += ( $TimeZoneOffset || 0 );
    my ( $sec, $min, $hour, $mday, $mon, $year ) = localtime($ts);
    return ( $year + 1900 ) . '-' . ( $mon + 1 ) . '-' . $mday;
}

sub CalcTime {
    my ($ts) = @_;
    my ( $ampm, $mytz );

    my $tzoff = $TimeZoneOffset || 0;
    $ts += $tzoff;
    my ( $sec, $min, $hour, $mday, $mon, $year ) = localtime($ts);
    $mytz = "";
    if ( ( $tzoff == 0 ) && ( ( $ScriptTZ // '' ) ne "" ) ) {
        $mytz = " " . $ScriptTZ;
    }
    $ampm = "";
    if ($UseAmPm) {
        $ampm = " am";
        if ( $hour > 11 ) {
            $ampm = " pm";
            $hour = $hour - 12;
        }
        $hour = 12 if ( $hour == 0 );
    }
    $min = "0" . $min if ( $min < 10 );
    return $hour . ":" . $min . $ampm . $mytz;
}

sub TimeToText {
    my ($t) = @_;

    return &CalcDay($t) . " " . &CalcTime($t);
}

sub GetParam {
    my ( $name, $default ) = @_;
    my $result;

    $result = $q->param($name);
    if ( !defined($result) ) {
        if ( defined( $UserData{$name} ) ) {
            $result = $UserData{$name};
        } else {
            $result = $default;
        }
    }
    return $result;
}

sub GetHiddenValue {
    my ( $name, $value ) = @_;

    $q->param( $name, $value );
    return $q->hidden($name);
}

sub GetRemoteHost {
    my ($doMask) = @_;
    my ( $rhost, $iaddr );

    $rhost = $ENV{REMOTE_HOST} // '';

    # Reverse-DNS lookup only when (a) configured on AND (b) we
    # actually have a non-empty IP. inet_aton('') returns undef, and
    # gethostbyaddr(undef, AF_INET) used to warn under -w with
    # "Use of uninitialized value in subroutine entry".
    if ( $UseLookup && $rhost eq '' ) {
        my $addr = RemoteAddr();
        if ( defined($addr) && $addr ne '' ) {
            eval {
                require Socket;
                $iaddr = Socket::inet_aton($addr);
                $rhost = gethostbyaddr( $iaddr, Socket::AF_INET() )
                  if defined $iaddr;
            };
            $rhost = '' if ( !defined($rhost) );
        }
    }
    if ( $rhost eq "" ) {
        $rhost = &RemoteAddr;
    }
    $rhost = &GetMaskedHost($rhost) if ($doMask);
    return $rhost;
}

sub FreeToNormal {
    my ($id) = @_;

    $id =~ s/ /_/g;
    $id = ucfirst($id) if ( $UpperFirst || $FreeUpper );
    if ( index( $id, '_' ) > -1 ) {    # Quick check for any space/underscores
        $id =~ s/__+/_/g;
        $id =~ s/^_//;
        $id =~ s/_$//;
        if ($UseSubpage) {
            $id =~ s|_/|/|g;
            $id =~ s|/_|/|g;
        }
    }
    if ($FreeUpper) {

        # Note that letters after ' are *not* capitalized
        if ( $id =~ m|[-_.,\(\)/][a-z]| ) {    # Quick check for non-canonical case
            $id =~ s|([-_.,\(\)/])([a-z])|$1 . uc($2)|ge;
        }
    }
    return $id;
}

#END_OF_BROWSE_CODE

# == Page-editing and other special-action code ========================
$OtherCode = "";    # Comment next line to always compile (slower)

#$OtherCode = <<'#END_OF_OTHER_CODE';

sub DoOtherRequest {
    my ( $id, $action, $text, $search );

    $action = &GetParam( "action", "" );
    $id     = &GetParam( "id",     "" );
    if ( $action ne "" ) {
        $action = lc($action);
        if ( $action eq "edit" ) {
            &DoEdit( $id, 0, 0, "", 0 ) if &ValidIdOrDie($id);
        } elsif ( $action eq "unlock" ) {
            &DoUnlock();
        } elsif ( $action eq "index" ) {
            &DoIndex();
        } elsif ( $action eq "links" ) {
            &DoLinks();
        } elsif ( $action eq "maintain" ) {
            &DoMaintain();
        } elsif ( $action eq "pagelock" ) {
            &DoPageLock();
        } elsif ( $action eq "editlock" ) {
            &DoEditLock();
        } elsif ( $action eq "editprefs" ) {
            &DoEditPrefs();
        } elsif ( $action eq "editbanned" ) {
            &DoEditBanned();
        } elsif ( $action eq "editlinks" ) {
            &DoEditLinks();
        } elsif ( $action eq "login" ) {
            &DoEnterLogin();
        } elsif ( $action eq "logout" ) {
            &DoLogout();
        } elsif ( $action eq "newlogin" ) {
            $UserID = 0;
            &DoEditPrefs();    # Also creates new ID
        } elsif ( $action eq "version" ) {
            &DoShowVersion();
        } elsif ( $action eq "rss" ) {
            &DoRss();
        } elsif ( $action eq "delete" ) {
            &DoDeletePage($id);
        } elsif ( $PermUseUpload && ( $action eq "upload" ) ) {
            &DoUpload();
        } elsif ( $action eq "maintainrc" ) {
            &DoMaintainRc();
        } elsif ( $action eq "convert" ) {
            &DoConvert();
        } elsif ( $action eq "watch" ) {
            &DoWatchPage($id);
        } elsif ( $action eq "activate" ) {
            &DoActivateUser();
        } elsif ( $UsePasswordReset && $action eq "forgotpw" ) {
            &DoForgotPasswordForm();
        } elsif ( $UsePasswordReset && $action eq "resetpw" ) {
            &DoResetPasswordForm();
        } elsif ( $action eq "unwatch" ) {
            &DoUnWatchPage($id);
        } else {
            &ReportError( Ts( 'Invalid action parameter %s', $action ) );
        }
        return;
    }
    if ( &GetParam( "edit_prefs", 0 ) ) {
        &DoUpdatePrefs();
        return;
    }
    if ( &GetParam( "edit_ban", 0 ) ) {
        &DoUpdateBanned();
        return;
    }
    if ( &GetParam( "enter_login", 0 ) ) {
        &DoLogin();
        return;
    }
    if ( $UsePasswordReset && &GetParam( "forgot_pw", 0 ) ) {
        &DoForgotPassword();
        return;
    }
    if ( $UsePasswordReset && &GetParam( "reset_pw", 0 ) ) {
        &DoResetPassword();
        return;
    }
    if ( &GetParam( "edit_links", 0 ) ) {
        &DoUpdateLinks();
        return;
    }
    if ( $PermUseUpload && ( &GetParam( "upload", 0 ) ) ) {
        &SaveUpload();
        return;
    }
    $search = &GetParam( "search", "" );
    if ( ( $search ne "" ) || ( &GetParam( "dosearch", "" ) ne "" ) ) {
        &DoSearch($search);
        return;
    } else {
        $search = &GetParam( "back", "" );
        if ( $search ne "" ) {
            &DoBackLinks($search);
            return;
        }
    }

    # Handle posted pages
    if ( &GetParam( "oldtime", "" ) ne "" ) {
        $id = &GetParam( "title", "" );
        &DoPost() if &ValidIdOrDie($id);
        return;
    }
    &ReportError( T('Invalid URL.') );
}

sub DoEdit {
    my ( $id,       $isConflict, $oldTime,  $newText,  $preview ) = @_;
    my ( $header,   $editRows,   $editCols, $userName, $revision, $oldText );
    my ( $summary,  $isEdit,     $pageTime );
    my ( $pagehash, %pagetype,   $kstr, $kid, $noeditrule, $exteditor );
    my @vv;

    if ( $FreeLinks && ( not $id =~ /\/__[A-Z0-9]+__$/ ) ) {
        $id = &FreeToNormal($id);    # Take care of users like Markus Lude :-)
    }
    if ( !&UserCanEdit( $id, 1 ) ) {
        print &GetHeader( "", T('Editing Denied'), "", "no-cache" );
        print '<div class="wikiinfo">';
        if ( &UserIsBanned() ) {
            print T('Editing not allowed: user, ip, or network is blocked.');
            print "<p>";
            print T('Contact the wiki administrator for more information.');
        } else {
            print Ts( 'Editing not allowed: %s is read-only.', $SiteName );
            if ( $UserID < 1000 ) {
                &EnterLoginForm( $FullUrl . &ScriptLinkChar() . $ENV{QUERY_STRING} );
            }
        }
        print "</div>";
        print &GetCommonFooter();
        return;
    }
    $exteditor = ReadPagePermissions( $id, \%ExtEditor );
    if ( $exteditor ne '' ) {
        &ReBrowsePage( "$exteditor#$id", "", 0 );
        return;
    }
    &BuildRuleStack($id);    # added 05/13/06 by fangq
                             # Consider sending a new user-ID cookie if user does not have one
    &OpenDefaultPage($id);
    $pageTime = $Pages{$id}->{'section'}->{'ts'};
    $header   = Ts( 'Editing %s', $id );

    # Old revision handling
    $revision = &GetParam( 'revision', '' );
    $revision =~ s/\D//g;    # Remove non-numeric chars
    if ( $revision ne '' ) {
        &OpenKeptRevisions( $id, 'text_default' );
        if ( !defined( $KeptRevisions{$revision} ) ) {
            $revision = '';

            # Consider better solution like error message?
        } else {
            &OpenKeptRevision( $id, $revision );
            $header = Ts( 'Editing revision %s of ', $revision ) . $id;
        }
    }
    if ( $Pages{$id}->{'writeonly'} == 1 ) {
        $Pages{$id}->{'text'}->{'text'} = '';
    }
    $oldText = $Pages{$id}->{'text'}->{'text'};
    if ( $preview && !$isConflict ) {
        $oldText = $newText;
    }
    $editRows = &GetParam( "editrows", 20 );
    $editCols = &GetParam( "editcols", 65 );
    print &GetHeader( '', &QuoteHtml($header), '', 'no-cache' );
    print '<div class="wikieditform">';
    if ( $revision ne '' ) {
        print "\n<b>"
          . Ts( 'Editing old revision %s.', $revision ) . " "
          . T('Saving this page will replace the latest revision with this text.')
          . '</b><br>';
    }
    if ($isConflict) {
        $editRows -= 10 if ( $editRows > 19 );
        print "\n<h1>" . T('Edit Conflict!') . "</h1>\n";
        if ( $isConflict > 1 ) {

# The main purpose of a new warning is to display more text and move the save button down from its old location.
            print "\n<h2>" . T('This change is a conflit.') . "</h2>\n";
        }
        print "<p><strong>",
          T('Someone saved this page after you started editing.'), " ",
          T('The top textbox contains the saved text.'),           " ",
          T('Only the text in the top textbox will be saved.'),
          "</strong><br>\n",
          T('Scroll down to see your edited text.'), "<br>\n";
        print T('Last save time:'), ' ', &TimeToText($oldTime),
          " (", T('Current time is:'), ' ', &TimeToText($Now), ")<br>\n";
    }
    if ($preview) {
        print "<div class='wikipreview'>\n<h2>", T('Preview'), "</h2>\n";
        if ($isConflict) {
            print "<b>", T('NOTE: This preview shows the revision of the other author.'),
              "</b><hr>\n";
        }
        $MainPage = $id;
        $MainPage =~ s|/.*||;    # Only the main page name (remove subpage)
        print &WikiToHTML( $id, $oldText ) . '<hr class="wikilinefooter">';
        print "<h2>", T('Preview only, not yet saved'), "</h2>\n</div>\n";
    }

    #  if($id =~ m/_9pt$/ || $id =~ m/_10pt$/ || $id =~ m/_11pt$/ || $id =~ m/_12pt$/){
    print
      "<form method=\"post\" action=\"$ScriptName\" enctype=\"application/x-www-form-urlencoded\" 
name=\"myform\">";

    # The edit form is written by hand (it needs name="myform" for the
    # editor scripts), so it must add the CSRF token GetFormStart adds;
    # without it every save was refused by DoPost's CSRFCheckOrDie.
    print qq(<input type="hidden" name="csrf_token" value="), GenCSRFToken(), qq(" />\n);

    #  }
    #  else {print &GetFormStart();}
    print &GetHiddenValue( "title", $id ), "\n",
      &GetHiddenValue( "oldtime",     $pageTime ),   "\n",
      &GetHiddenValue( "oldconflict", $isConflict ), "\n";

    if ( $revision ne "" ) {
        print &GetHiddenValue( "revision", $revision ), "\n";
    }
    $noeditrule = &GetParam( "noeditrule", "" );
    if ( $noeditrule eq "" ) {
        my $u  = &UserPermission();
        my $pp = ReadPagePermissions( $id, \%Permissions );
        if (
            (
                defined( $Pages{$id}->{'clearance'} )
                && &UserPermission() < $Pages{$id}->{'clearance'}
            )
            || ( ( $pp ne '' ) && &UserPermission() < $pp )
          )
        {
            $UseCache = 0;
            $StaticCacheOK = 0;    # permission-restricted view
            return "";
        }
    }
    {
        $kstr = &GetParam( "keyfield", "" );
        $kid  = &GetParam( "keyblock", "" );
        $kstr = &GetParam( "keyval",   "" );

        if ( $kstr ne "" && $kid ne "" && $kstr ne "" ) {
            @vv = split( /(<\/$kid>)/, $oldText );
            for ( my $i = 0 ; $i < @vv ; $i++ ) {
                if ( $vv[$i] =~ /$kstr/ ) {
                    $oldText = $vv[$i] . "\n</$kid>";
                    last;
                }
            }
        }
    }

    if ( $noeditrule eq "" ) {
        print &ApplyRegExp( $id, "", \%NameSpaceE0, $Pages{$id}->{'preedit'} );
    } elsif ( &UserPermission() < 100 ) {
        print "<div class='wikiinfo'>" . T('noeditrule mode only allowed for admin.');
        if ( $UserID < 1000 ) {
            &EnterLoginForm( $FullUrl . &ScriptLinkChar() . $ENV{QUERY_STRING} );
        }
        print "</div>";
        return;
    }
    print &GetTextArea( 'text', $oldText, $editRows, $editCols );
    $summary = &GetParam( "summary", "*" );
    print "<p>", T('Summary:'),
      $q->textfield(
        -name      => 'summary',
        -default   => $summary,
        -override  => 1,
        -size      => 60,
        -maxlength => 200
      );
    if ( &GetParam("recent_edit") eq "on" ) {
        print "<br>",
          $q->checkbox(
            -name    => 'recent_edit',
            -checked => 1,
            -label   => T('This change is a minor edit.')
          );
    } else {
        print "<br>",
          $q->checkbox(
            -name  => 'recent_edit',
            -label => T('This change is a minor edit.')
          );
    }
    if ($EmailNotify) {
        print "&nbsp;&nbsp;&nbsp;"
          . $q->checkbox(
            -name  => 'do_email_notify',
            -id    => 'do_email_notify',
            -label => Ts( 'Send email notification that %s has been changed.', $id )
          );
    }
    print "<br>";
    if ( $EditNote ne '' ) {
        print T($EditNote) . '<br>';    # Allow translation
    }
    print PrintCaptcha() if $UseCaptcha;

    print $q->submit( -name => 'Save', -id => 'btn_save', -value => T('Save') ), "\n";
    $userName = &GetParam( "username", "" );
    if ( $userName ne "" ) {
        print Ts( '(Current user name is %s)', &GetPageLink($userName) );
    } else {
        print Ts( '(Current user name is %s)', T("anonymous") );
    }
    print $q->submit( -name => 'Preview', -id => 'btn_preview', -value => T('Preview') ), "\n";

    if ($isConflict) {
        print "\n<br><hr><p><strong>", T('This is the text you submitted:'),
          "</strong><p>",
          &GetTextArea( 'newtext', $newText, $editRows, $editCols ),
          "<p>\n";
    }
    print $q->end_form;
    print "\n</div>\n";

    print '<div class="wikifooter">';

    #print &GetFormStart();
    #print &GetHistoryLink($id, T('View other revision')) . "<br>\n";
    #print &GetGotoBar($id);
    #print $q->end_form;
    print "</div>";
    print &GetMinimumFooter();
}

sub GetTextArea {
    my ( $name, $text, $rows, $cols ) = @_;

    return $q->textarea(
        -name     => $name,
        -default  => $text,
        -id       => $name,
        -rows     => $rows,
        -columns  => $cols,
        -override => 1,
        -class    => 'wikieditor',
        -wrap     => 'virtual'
    );
}

sub DoActivateUser {
    my ( $regkey, $regid, $uid, $treg, $userdb, $sth );
    $regid = &GetParam( 'regid',   '' );
    $uid   = &GetParam( 'uid',     '' );
    $treg  = &GetParam( 'regtime', '' );

    $userdb = DBTable($UserDir);
    $uid    = ( $uid =~ /\A\d+\z/ ) ? $uid : 0;
    $regkey = &ReadDBItems( $userdb, 'param', '', '', "id=?", $uid );

    if ( $regkey eq $regid ) {
        if ( $dbh eq "" || $userdb eq "" ) {
            die( T('ERROR: database uninitialized!') );
        }
        die("DoActivateUser: unsafe table name") if ( !SafeIdent($userdb) );
        $sth = $dbh->selectall_arrayref( "select id from $userdb where id=? limit 1", undef, $uid );
        if ( defined $sth->[0] ) {
            $sth = $dbh->prepare("update $userdb set param='' where id=? limit 1");
            $sth->execute($uid);
        }
        ResetRandKeyDB( $uid, '' );
        print &GetHeader( '', T('Activate Account'), '' );
        print '<div class="wikiinfo">' . T("Registration complete") . '</div>';
        print &GetCommonFooter();
    } else {
        print &GetHeader( '', T('Activate Account'), '' );
        print '<div class="wikiinfo">' . T("Registration key does not match") . '</div>';
        print &GetCommonFooter();
    }
}

sub DoLogout {
    my $oldid = $UserID;
    $UserID    = 0;
    %SetCookie = ();
    if ( $oldid >= 1000 ) {
        AddUserLogDB( $oldid, 'Lo', $UserData{'id'} );
    }
    &DoNewLoginDB();
    &DoEnterLogin();
}

sub DoEditPrefs {
    my ( $check, $recentName, %labels );

    $recentName = $RCName;
    $recentName =~ s/_/ /g;

    &DoNewLoginDB() if ( $UserID < 400 );
    print &GetHeader( '', T('Editing Preferences'), "" );
    print '<div class="wikipref">';
    print &GetFormStart();
    print GetHiddenValue( "edit_prefs", 1 ), "\n";
    print '<h4>' . T('User info:') . "</h4>";

    # Registration profile (first/last name, institute, interests).
    # Names are fixed once set; institute/interests stay editable.
    # Stored values are user input, so quote them on output.
    print '<span class="span_prefinfo"><label class="formlabel">' . T('First Name') . '</label>';
    if ( defined( $UserData{'firstname'} ) && $UserData{'firstname'} ne '' ) {
        print QuoteHtml( $UserData{'firstname'} ) . '</span><br/>';
    } else {
        print &GetFormText( 'reg_firstname', '', 20, 50 ) . '<strong>*</strong></span><br/>';
    }
    print '<span class="span_prefinfo"><label class="formlabel">' . T('Last Name') . '</label>';
    if ( defined( $UserData{'lastname'} ) && $UserData{'lastname'} ne '' ) {
        print QuoteHtml( $UserData{'lastname'} ) . '</span><br/>';
    } else {
        print &GetFormText( 'reg_lastname', '', 20, 50 ) . '<strong>*</strong></span><br/>';
    }
    print '<span class="span_prefinfo"><label class="formlabel">' . T('Institute/Company') . '</label>',
      &GetFormText( 'reg_inst', $UserData{'inst'} // '', 20, 50 ) . '<strong>*</strong></span><br/>';
    print '<span class="span_prefinfo"><label class="formlabel">' . T('Interests') . '</label>',
      &GetFormText( 'reg_research', $UserData{'area'} // '', 100, 250 )
      . '</span><hr class="wikilinepref"/>';

    print '<span class="span_prefinfo"><label class="formlabel">' . T('User name:') . '</label>';
    if ( $UserData{'username'} ne '' ) {

        # Username is constrained to $FreeLinkPattern's charset, which
        # excludes < > " &, so XSS via this output is already blocked
        # by validation in DoUpdatePrefs. QuoteHtml is defensive
        # depth-in-defense: an apostrophe in 'O'Brien' or similar
        # still renders correctly, and any future relaxation of the
        # username charset won't break out of the surrounding span.
        print "<span class='span_username'>"
          . QuoteHtml( $UserData{'username'} )
          . "</span> ("
          . QuoteHtml($UserID) . ")";
        print &GetHiddenValue( 'p_username', $UserData{'username'} ), "\n";
    } else {
        print &GetFormText( 'username', "", 20, 30 ) . "<strong>*</strong>";
        print T('(must be unique)');
    }
    if ( $UserData{'username'} ne '' ) {
        print '</span><br><span class="span_prefinfo"><label class="formlabel">'
          . T('Old password:')
          . '</label>',
          $q->password_field(
            -name      => 'p_password',
            -value     => '',
            -size      => 20,
            -maxlength => 50
          ),
          '<strong>*</strong></span><br/>';
        print '<span class="span_prefinfo"><label class="formlabel">'
          . T('New password:')
          . '</label>',
          $q->password_field(
            -name      => 'new_password',
            -value     => '',
            -size      => 20,
            -maxlength => 50
          ),
          '</span><br/>';
    } else {
        print '</span><br><span class="span_prefinfo"><label class="formlabel">'
          . T('User password:')
          . '</label>',
          $q->password_field(
            -name      => 'p_password',
            -value     => '',
            -size      => 20,
            -maxlength => 50
          ),
          '<strong>*</strong></span><br/>';
    }
    print '<span class="span_prefinfo"><label class="formlabel">'
      . T('Repeat password:')
      . '</label>',
      $q->password_field(
        -name      => 'p_password2',
        -value     => '',
        -size      => 20,
        -maxlength => 50
      ),
      '<strong>*</strong></span><br/>';
    print '<span class="span_prefinfo"><label class="formlabel">' . T('Email Address:'), '</label>',
      &GetFormText( 'email', "", 20, 60 )
      . '<strong>*'
      . T('(must be unique)')
      . '</strong></span><hr class="wikilinepref"/>';
    if ( $UserData{'username'} eq '' && &RegistrationLevel() ne 'user' ) {    # sign-up form
        print '<h4>' . T('Registration token') . '</h4>';
        print '<span class="span_prefinfo"><label class="formlabel">' . T('Token:'), '</label>',
          $q->password_field( -name => 'p_regtoken', -value => '', -size => 20, -maxlength => 50 ),
          '<strong>*</strong> ',
          (
            &RegistrationLevel() eq 'admin'
            ? T('(registration needs a token from the wiki administrator)')
            : T('(registration needs a token from a wiki editor or administrator)')
          ),
          '</span><hr class="wikilinepref"/>';
    }
    if ( ( $AdminPass ne '' ) || ( $EditPass ne '' ) ) {
        print '<h4>' . T('Administrator token') . '</h4>';
        print '<span class="span_prefinfo"><label class="formlabel">' . T('Token:'), '</label>',
          $q->password_field(
            -name      => 'p_adminpw',
            -value     => '*',
            -size      => 20,
            -maxlength => 50
          ),
          ' ', T('(if you do not know what this is, please leave it untouched)'), '</span><br>';
    }
    print "<hr class='wikilinepref'><h4>" . T('Additional user preferences') . '</h4>';
    print "<hr class='wikilinepref'><h4>$recentName:</h4>";
    print '<span class="span_prefinfo"><label class="formlabel">' . T('Default days to display:'),
      '</label>',
      &GetFormText( 'rcdays', $RcDefault, 4, 9 );
    print "</span><br>", &GetFormCheck( 'rcnewtop', $RecentTop, T('Most recent changes on top') );
    print "<br>",        &GetFormCheck( 'rcall', 0, T('Show all changes (not just most recent)') );
    %labels = (
        0 => T('Hide minor edits'),
        1 => T('Show minor edits'),
        2 => T('Show only minor edits')
    );
    print '<br><span class="span_prefinfo"><label class="formlabel">', T('Minor edit display:'),
      '</label>';
    print $q->popup_menu(
        -name    => 'p_rcshowedit',
        -values  => [ 0, 1, 2 ],
        -labels  => \%labels,
        -default => &GetParam( "rcshowedit", $ShowEdits )
    );
    print "</span><br>", &GetFormCheck( 'rcchangehist', 1, T('Use "changes" as link to history') );

    if ($UseDiff) {
        print '<hr class="wikilinepref"><h4>', T('Differences:'), "</h4>\n";
        print &GetFormCheck( 'diffrclink', 1, Ts( 'Show (diff) links on %s', $recentName ) );
        print "<br>", &GetFormCheck( 'alldiff', 0, T('Show differences on all pages') );
        print " (", &GetFormCheck( 'norcdiff', 1, Ts( 'No differences on %s', $recentName ) ), ")";
        %labels = ( 1 => T('Major'), 2 => T('Minor'), 3 => T('Author') );
        print '<br><span class="span_prefinfo"><label class="formlabel">',
          T('Default difference type:'), '</label>';
        print $q->popup_menu(
            -name    => 'p_defaultdiff',
            -values  => [ 1, 2, 3 ],
            -labels  => \%labels,
            -default => &GetParam( "defaultdiff", 1 )
        );
    }
    print '</span><hr class="wikilinepref"><h4>', T('Misc:'), "</h4>\n";

    # Note: TZ offset is added by TimeToText, so pre-subtract to cancel.
    print T('Server time:'), ' ', &TimeToText( $Now - $TimeZoneOffset );
    print '<br><span class="span_prefinfo"><label class="formlabel">',
      T('Time Zone offset (hours):'), '</label>',
      &GetFormText( 'tzoffset', 0, 4, 9 );
    print '</span><br>', T('Edit area:') . T('rows:'), ' ', &GetFormText( 'editrows', 20, 4, 4 ),
      ' ', T('columns:'), ' ', &GetFormText( 'editcols', 65, 4, 4 );

    print '<br>', &GetFormCheck( 'toplinkbar', 1, T('Show link bar on top') );
    print '<br>', &GetFormCheck( 'linkrandom', 0, T('Add "Random Page" link to link bar') );
    print '<br><span class="span_prefinfo"><label class="formlabel">'
      . T('StyleSheet URL:')
      . '</label>',
      &GetFormText( 'stylesheet', "", 30, 150 );

    %labels = ( "en" => T('English'), "cn" => T('Simplified Chinese') );
    print '</span><br><span class="span_prefinfo"><label class="formlabel">', T('Language:'),
      '</label>';
    print $q->popup_menu(
        -name    => 'p_lang',
        -values  => [ "en", "cn" ],
        -labels  => \%labels,
        -default => &GetParam( "lang", 1 )
    );

    print '</span><hr class="wikilinepref">Fields marked with an asterisk (*) are required.<br/>'
      . $q->submit( -name => 'Save', -value => T('Submit') ), "\n";
    print '</div>';
    print '<hr class="wikilinefooter">';
    print '<div class="wikifooter">';

    #print &GetGotoBar('');
    print $q->end_form;
    print '</div>';
    print &GetMinimumFooter();
    if ( $UserID >= 400 ) {
        AddUserLogDB( $UserID, 'Ep', $UserData{'id'} );
    }
}

sub GetFormText {
    my ( $name, $default, $size, $max ) = @_;
    my $text = &GetParam( $name, $default );

    return $q->textfield(
        -name      => "p_$name",
        -default   => $text,
        -override  => 1,
        -size      => $size,
        -maxlength => $max
    );
}

sub GetFormCheck {
    my ( $name, $default, $label ) = @_;
    my $checked = ( &GetParam( $name, $default ) > 0 );

    return $q->checkbox(
        -name     => "p_$name",
        -override => 1,
        -checked  => $checked,
        -label    => $label
    );
}

sub DoUpdatePrefs {
    CSRFCheckOrDie();
    my ( $username, $password, $password2, $newpass, $stylesheet, $lang, $email );

    # All link bar settings should be updated before printing the header
    &UpdatePrefCheckbox("toplinkbar");
    &UpdatePrefCheckbox("linkrandom");
    $username  = &GetParam( "p_username",   "" );
    $password  = &GetParam( "p_password",   "" );
    $password2 = &GetParam( "p_password2",  "" );
    $newpass   = &GetParam( "new_password", "" );
    $email     = &GetParam( "p_email",      "" );

    # The address is later handed to the mailer (activation notice), so
    # only plain addresses are accepted, for new and existing users.
    if ( $email ne "" && !ValidEmail($email) ) {
        PrintMsg( T("Please enter a valid email address"), T("Error"), 1 );
    }

    # $RegistrationPermission: an editor/admin-only wiki needs a matching
    # registration token. Checked before anything is set up, so a refused
    # registration writes no user row. Failures are throttled per IP.
    if ( $UserID < 1001 && &RegistrationLevel() ne 'user' ) {
        my $ip_key = 'regtoken-ip:' . &RemoteAddr;
        if ( LoginThrottleBlocked($ip_key) ) {
            PrintMsg( T('Too many requests. Try again in a few minutes.'), T('Error'), 1 );
        }
        if ( !&RegistrationTokenOK( &GetParam( "p_regtoken", "" ) ) ) {
            LoginThrottleHit($ip_key);
            PrintMsg(
                &RegistrationLevel() eq 'admin'
                ? T('Registration requires a valid administrator token.')
                : T('Registration requires a valid editor or administrator token.'),
                T('Error'), 1
            );
        }
    }

    if ( $UserID < 1001 ) {
        &DoNewLoginDB() if ( $UserID < 400 );
        if ($UseActivation) {
            undef $SetCookie{'id'};
        }
        if ( $email eq "" ) {
            PrintMsg( T("You have to give an email address"), T("Error"), 1 );
        }
    } else {    # for existing users, you have to match password before changing anything
        if ( !VerifyPassword( $password, $UserData{'password'} ) ) {
            PrintMsg(
                T("You have to type the correct password in order to change your preferences"),
                T("Error"), 1 );
        }
        if ( $newpass ne "" && $password2 ne "" ) {
            if ( $newpass eq $password2 ) {
                $password = $newpass;
            } else {
                PrintMsg( T("Two passwords do not match"), T("Error"), 1 );
            }
        }
    }
    print &GetHeader( '', T('Saving Preferences'), '' );
    print '<div class="wikitext"><br>';

    if ($FreeLinks) {
        $username =~ s/^\[\[(.+)\]\]/$1/;    # Remove [[ and ]] if added
        $username = &FreeToNormal($username);
        $username =~ s/_/ /g;
    }

    # Registration profile. First/last name are required once and then
    # fixed (DoEditPrefs no longer offers an input for them, so keep the
    # stored value rather than reading an absent field); institute is
    # required on every save; interests are optional.
    my %profile;
    for my $f (
        [ 'firstname', 'p_reg_firstname', 50,  1 ],
        [ 'lastname',  'p_reg_lastname',  50,  1 ],
        [ 'inst',      'p_reg_inst',      50,  0 ],
        [ 'area',      'p_reg_research',  250, 0 ],
      )
    {
        my ( $key, $param, $max, $fixed ) = @$f;
        my $val =
          ( $fixed && defined( $UserData{$key} ) && $UserData{$key} ne '' )
          ? $UserData{$key}
          : &GetParam( $param, '' );
        $val =~ s/[\x00-\x1f\x7f]+/ /g;    # no control chars (incl. $FS)
        $val =~ s/^\s+|\s+$//g;
        $val = substr( $val, 0, $max ) if ( length($val) > $max );
        $profile{$key} = $val;
    }
    if ( $profile{'firstname'} eq '' || $profile{'lastname'} eq '' || $profile{'inst'} eq '' ) {
        ErrMsg(
            T('You must provide your first name, last name and institute/company in order to register'),
            T('Error'), 1
        );
    }

    # Validation failures render as a wiki message (was: die, which
    # CGI::Carp turns into a "Software error" page). The username is
    # user input, so it is quoted before being echoed back.
    if ( $username eq "" ) {

        #removing username is not allowed now
        #print T('UserName removed.'), '<br>';
        #undef $UserData{'username'};
        ErrMsg( T('User name can not be empty.'), T('Error'), 1 );
    } elsif ( ( !$FreeLinks ) && ( !( $username =~ /^$LinkPattern$/ ) ) ) {
        ErrMsg( Ts( 'Invalid UserName %s: not saved.', QuoteHtml($username) ), T('Error'), 1 );
    } elsif ( $FreeLinks && ( !( $username =~ /^$FreeLinkPattern$/ ) ) ) {
        ErrMsg( Ts( 'Invalid UserName %s: not saved.', QuoteHtml($username) ), T('Error'), 1 );
    } elsif ( length($username) > 50 ) {    # Too long
        ErrMsg( T('UserName must be 50 characters or less. (not saved)'), T('Error'), 1 );
    } else {
        $UserData{'username'} = $username;
    }
    if ( $password eq "" ) {
        ErrMsg( T("User must set an non-empty password."), T('Error'), 1 );
    } elsif ( length($password) < 8 ) {
        ErrMsg( T("Password is shorter than 8 char."), T('Error'), 1 );
    } elsif ( $password =~ /[^a-zA-Z0-9_@^\]\[!@\$%^&]/ ) {
        ErrMsg( T("Password can only contain basic latin, digits or one of '[]!\@\$%^&'."),
            T('Error'), 1 );
    } elsif ( $password ne "*" ) {
        print T('Successfully set user password.'), '<br>';
        $UserData{'password'} = HashPassword($password);
    }
    if ( ( $AdminPass ne "" ) || ( $EditPass ne "" ) ) {
        $password = &GetParam( "p_adminpw", "" );
        if ( $password eq "" ) {
            print T('Administrator password removed.'), '<br>';
            undef $UserData{'adminpw'};
        } elsif ( $password ne "*" ) {
            print T('Administrator password changed.'), '<br>';
            $UserData{'adminpw'} = HashPassword($password);
            if ( &UserIsAdmin() ) {
                print T('User has administrative abilities.'), '<br>';
            } elsif ( &UserIsEditor() ) {
                print T('User has editor abilities.'), '<br>';
            } else {
                print T('User does not have administrative abilities.'), ' ',
                  T('(Password does not match administrative password(s).)'),
                  '<br>';
            }
        }
    }
    if ( &GetLockState == 1 || ( ( !$PermEditAllowed ) && &UserPermission() < $PermEditAllowed ) ) {
        ErrMsg( T("Wiki read-only"), T("Error"), 1 );
    }
    $UserData{'email'} = &GetParam( "p_email", "" );

    #  if ($EmailNotify) {
    #    &UpdatePrefCheckbox("notify");
    #    &UpdateEmailList();
    #  }
    &UpdatePrefNumber( "rcdays", 0, 0, 999999 );
    &UpdatePrefCheckbox("rcnewtop");
    &UpdatePrefCheckbox("rcall");
    &UpdatePrefCheckbox("rcchangehist");
    if ($UseDiff) {
        &UpdatePrefCheckbox("norcdiff");
        &UpdatePrefCheckbox("diffrclink");
        &UpdatePrefCheckbox("alldiff");
        &UpdatePrefNumber( "defaultdiff", 1, 1, 3 );
    }
    &UpdatePrefNumber( "rcshowedit", 1, 0,    2 );
    &UpdatePrefNumber( "tzoffset",   0, -999, 999 );
    &UpdatePrefNumber( "editrows",   1, 1,    999 );
    &UpdatePrefNumber( "editcols",   1, 1,    999 );
    print T('Server time:'), ' ', &TimeToText( $Now - $TimeZoneOffset ), '<br>';
    $TimeZoneOffset = &GetParam( "tzoffset", 0 ) * ( 60 * 60 );
    print T('Local time:'), ' ', &TimeToText($Now), '<br>';
    $stylesheet = &GetParam( 'p_stylesheet', '' );

    if ( $stylesheet eq '' ) {
        if ( &GetParam( 'stylesheet', '' ) ne '' ) {
            print T('StyleSheet URL removed.'), '<br>';
        }
        $UserData{'stylesheet'} = '';
    } else {
        $stylesheet =~ s/[">]//g;    # Remove characters that would cause problems
        $UserData{'stylesheet'} = $stylesheet;
        print T('StyleSheet setting saved.'), '<br>';
    }
    $lang = &GetParam( 'p_lang', $LangID );
    if ( $LangID ne "" ) {
        $UserData{'lang'} = $lang;
    }
    $UserData{$_} = $profile{$_} for keys %profile;
    &SaveUserDataDB();
    if ( $UserID >= 1000 ) {
        AddUserLogDB( $UserID, 'Sp', '' );
    }
    print '<b>', T('User settings updated.'), '</b>';
    print '</div>';
    print &GetCommonFooter();
}

# add or remove email address from preferences to $EmailFile
sub UpdateEmailList {
    my (@old_emails);

    local $/ = "\n";    # don't slurp whole files in this sub.
    if ( my $new_email = $UserData{'email'} = &GetParam( "p_email", "" ) ) {
        my $notify = $UserData{'notify'};
        if ( -f $EmailFile ) {
            open( NOTIFY, $EmailFile )
              or die( Ts( 'Could not read from %s:', $EmailFile ) . " $!\n" );
            @old_emails = <NOTIFY>;
            close(NOTIFY);
        } else {
            @old_emails = ();
        }
        my $already_in_list = grep /$new_email/, @old_emails;
        if ( $notify and ( not $already_in_list ) ) {
            &RequestLock() or die( T('Could not get mail lock') );
            if ( !open( NOTIFY, ">>$EmailFile" ) ) {
                &ReleaseLock();    # Don't leave hangling locks
                die( Ts( 'Could not append to %s:', $EmailFile ) . " $!\n" );
            }

            #      print NOTIFY $new_email, "\n";
            close(NOTIFY);
            &ReleaseLock();
        } elsif ( ( not $notify ) and $already_in_list ) {
            &RequestLock() or die( T('Could not get mail lock') );
            if ( !open( NOTIFY, ">$EmailFile" ) ) {
                &ReleaseLock();
                die( Ts( 'Could not overwrite %s:', "$EmailFile" ) . " $!\n" );
            }
            foreach (@old_emails) {
                print NOTIFY "$_" unless /$new_email/;
            }
            close(NOTIFY);
            &ReleaseLock();
        }
    }
}

sub UpdatePrefCheckbox {
    my ($param) = @_;
    my $temp = &GetParam( "p_$param", "*" );

    $UserData{$param} = 1 if ( $temp eq "on" );
    $UserData{$param} = 0 if ( $temp eq "*" );

    # It is possible to skip updating by using another value, like "2"
}

sub UpdatePrefNumber {
    my ( $param, $integer, $min, $max ) = @_;
    my $temp = &GetParam( "p_$param", "*" );

    return if ( $temp eq "*" );
    $temp =~ s/[^-\d\.]//g;
    $temp =~ s/\..*// if ($integer);
    return if ( $temp eq "" );
    return if ( ( $temp < $min ) || ( $temp > $max ) );
    $UserData{$param} = $temp;
}

sub DoIndex {
    print &GetHeader( '', T('Index of all pages'), '' );
    print &GetWrapperStart();
    &PrintPageList( &AllPagesList() );
    if ( &GetParam( "offset", "" ) == 0 ) {
        print '<div class="wikitext"><h3>' . T('Search build-in pages ...') . '</h3></div>';
        &PrintPageList( keys %BuildinPages );
    }
    print &GetWrapperEnd();
    print &GetCommonFooter();
}

# Create a new user file/cookie pair. The signed session cookie is
# emitted on the next response by GetHttpHeader / GetRedirectPage.
sub DoNewLoginDB {
    $SetCookie{'id'} = &GetNewUserIdDB();
    %UserCookie      = ( id => $SetCookie{'id'} );
    $UserID          = $SetCookie{'id'};

    %UserData               = ();
    $UserData{'id'}         = $SetCookie{'id'};
    $UserData{'createtime'} = $Now;
    $UserData{'createip'}   = &RemoteAddr;
    $UserData{'pagecreate'} = '';
    $UserData{'pagemodify'} = '';
    $UserData{'param'}      = '';
    $UserData{'stylesheet'} = '';

    # &SaveUserDataDB();
}

sub EnterLoginForm {
    my ($refurl) = @_;
    $refurl = '' if ( !defined($refurl) );
    print &GetFormStart();
    print &GetHiddenValue( 'enter_login', 1 ), "\n";
    print &GetHiddenValue( 'refer_url', $refurl ), "\n" if ( $refurl =~ /^http/i );
    print '<br><label class="formlabel">', T('User Name:'), '</label>',
      $q->textfield(
        -name      => 'p_username',
        -value     => '',
        -size      => 15,
        -maxlength => 50
      );
    print '<br><label class="formlabel">', T('Password:'), '</label>',
      $q->password_field(
        -name      => 'p_password',
        -value     => '',
        -size      => 15,
        -maxlength => 50
      );
    print '<br>', $q->submit( -name => 'Login', -value => T('Login') ), "\n";
    print '<br>'
      . Ts(
        'If you do not have an account, please %s to register.',
        &ScriptLink( "action=newlogin", T('click here') )
      ) . "\n";
    print '<br>' . &ScriptLink( "action=forgotpw", T('Forgot your password?') ) . "\n"
      if ($UsePasswordReset);
    print '<hr class="wikilinefooter">';
    print $q->end_form;
}

sub DoEnterLogin {
    print &GetHeader( '', T('Login'), "" );
    print '<div class="wikiinfo">';
    &EnterLoginForm();
    print "</div>";
    print &GetMinimumFooter();
}

sub DoLogin {
    CSRFCheckOrDie();
    my ( $uid, $uname, $password, $admpass, $success );
    my $generic_err = T('Login failed.');

    $success = 0;
    $uid     = &GetParam( "p_userid", "" );
    $uid =~ s/\D//g;
    $uname    = &GetParam( "p_username",  "" );
    $password = &GetParam( "p_password",  "" );
    $admpass  = &GetParam( "p_adminpass", "" );

    my $ip_key   = 'ip:' . &RemoteAddr;
    my $name_key = $uname ne '' ? ( 'name:' . lc($uname) ) : '';

    if ( LoginThrottleBlocked($ip_key) || ( $name_key && LoginThrottleBlocked($name_key) ) ) {
        AddUserLogDB( $UserID, 'login', '-T' );    # throttled
        print &GetHeader( '', T('Login'), '' );
        print '<div class="wikiinfo">',
          T('Too many failed login attempts. Try again in a few minutes.'),
          "</div>";
        print &GetMinimumFooter();
        return;
    }

    if ( ( $password ne "" ) && ( $password ne "*" ) ) {
        if ( $uname ne "" ) {
            &LoadUserDataDB( -1, $uname );
        } else {
            &LoadUserDataDB($uid);
        }
        $UserID = $UserData{'id'};
        if ( $UserID > 199 ) {
            if ( $UserData{'param'} =~ /^R/ ) {

                # Account exists but is pending activation. Same generic
                # error as wrong password so existence is not leaked.
            } elsif ( VerifyPassword( $password, $UserData{'password'} ) ) {
                $success = 1;
                $SetCookie{'id'} = $UserData{'id'};
                if ( IsLegacyPasswordHash( $UserData{'password'} ) ) {
                    my $newhash = HashPassword($password);
                    UpgradePasswordHashDB( $UserData{'username'}, $newhash );
                    $UserData{'password'} = $newhash;
                }
            }
        }
    }

    if ($success) {
        LoginThrottleClear($ip_key);
        LoginThrottleClear($name_key) if $name_key;
        my $refurl = &GetParam( "refer_url", "" );
        ResetRandKeyDB( $UserID, $UserData{'param'} );
        if ( $refurl =~ /^http/i ) {
            AddUserLogDB( $UserID, 'login', $uname );
            print &GetRedirectPage( $refurl,
                T("if your browser does not support redirect, please click this link"), 1 );
            return;
        }
    } else {
        LoginThrottleHit($ip_key);
        LoginThrottleHit($name_key) if $name_key;
    }

    print &GetHeader( '', T('Login Results'), '' );
    print '<div class="wikiinfo">';
    if ($success) {
        print Ts( 'Login for user %s complete.', "$uname" );
        AddUserLogDB( $UserID, 'login', $uname );
    } else {
        print $generic_err;
        AddUserLogDB( $UserID, 'login', '-F' );
    }
    print '<hr class="wikilinefooter">';
    print $q->end_form;
    print "</div>";
    print &GetMinimumFooter();
}

# Signals that a freshly-authenticated session cookie should be emitted
# on the next response. Used to be: rotate per-IP randkey, store in DB.
# Now: just record uid; the next response signs and sets the cookie.
sub ResetRandKeyDB {
    my ( $uid, $param ) = @_;
    return if ( $UseActivation && $param =~ /^R/ );
    $SetCookie{'id'} = $uid;
}

sub GetNewUserIdDB {
    my ( $id, $rest, $count );
    my $userdb = DBTable($UserDir);
    my $sth;

    if ( $dbh eq "" || $userdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("GetNewUserIdDB: unsafe table name") if ( !SafeIdent($userdb) );
    $sth = $dbh->selectall_arrayref("select max(id) from $userdb");
    if ( defined $sth->[0] ) {
        ($id) = @{ $sth->[0] };
        if ( $id eq "" ) {
            $id = 1000;
        }
    } else {
        $id = 1000;
    }
    $id++;
    return $id;
}

sub SaveUserDataDB {
    my $userdb = DBTable($UserDir);
    my (
        $id,       $sth,     $encpass,   $isnewuser, $tmp,   $name,
        $passhash, $randkey, $adminhash, $linkchr,   %extra, %rkey
    );

    if ( $dbh eq "" || $userdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("SaveUserDataDB: unsafe table name") if ( !SafeIdent($userdb) );
    # User names are unique case-insensitively ("Alice" blocks "alice"),
    # as on the legacy NeuroJSON wiki. UPPER() works on all three
    # dialects; on MariaDB the utf8mb4_bin collation would otherwise
    # make `name=?` case-sensitive.
    # Pre-existing case-variant duplicates can return several ids. User
    # names cannot be changed once set, so if this account is among the
    # matches it is simply saving itself; otherwise the name is taken.
    $tmp = ReadDBItems( $userdb, 'id', "\n", '', "UPPER(name)=UPPER(?)", $UserData{'username'} );
    my @sameName = grep { $_ ne '' } split( /\n/, $tmp );
    $isnewuser = 0;
    if ( !@sameName ) {
        $isnewuser = 1;
    } elsif ( !grep { $_ eq $UserID } @sameName ) {
        ErrMsg( Ts( 'ERROR: user name %s has already been taken!', QuoteHtml( $UserData{'username'} ) ),
            T('Error'), 1 );
    }
    $tmp = ReadDBItems( $userdb, 'id', "\n", '', "email=?", $UserData{'email'} );
    if ( $tmp ne '' && $tmp ne $UserID ) {
        ErrMsg( Ts( 'ERROR: user email %s has already been taken!', QuoteHtml( $UserData{'email'} ) ),
            T('Error'), 1 );
    }
    $passhash  = ReadDBItems( $userdb, 'pass', "\n", '', "name=?", $UserData{'username'} );
    $encpass   = $UserData{'password'};
    $adminhash = "";
    if ( $UserData{'adminpw'} ne "" ) {
        $adminhash = $UserData{'adminpw'};
    }
    if ( $isnewuser && $UseActivation ) {
        &SetPreRegFlag();
    }
    %extra = (
        'stylesheet'   => $UserData{'stylesheet'},
        'rcdays'       => $UserData{'rcdays'},
        'rcnewtop'     => $UserData{'rcnewtop'},
        'rcchangehist' => $UserData{'rcchangehist'},
        'rcshowedit'   => $UserData{'rcshowedit'},
        'tzoffset'     => $UserData{'tzoffset'},
        'editrows'     => $UserData{'editrows'},
        'editcols'     => $UserData{'editcols'},
        'norcdiff'     => $UserData{'norcdiff'},
        'diffrclink'   => $UserData{'diffrclink'},
        'alldiff'      => $UserData{'alldiff'},
        'defaultdiff'  => $UserData{'defaultdiff'},
        'fn'           => $UserData{'firstname'},
        'sn'           => $UserData{'lastname'},
        'inst'         => $UserData{'inst'},
        'area'         => $UserData{'area'},
    );

    # The randkey column was retired in Stage 5 (replaced by HMAC-
    # signed session cookies). The prefs column was renamed from
    # `stylesheet` and stores JSON instead of $FS2-joined text.
    # WriteDBItems generates a dialect-aware upsert (REPLACE on
    # SQLite, ON CONFLICT DO UPDATE on Postgres).
    require JSON::PP;
    my $prefs_json = JSON::PP::encode_json( \%extra );
    WriteDBItems(
        $userdb,
        "id,name,pass,groupid,lang,email,param,createtime,"
          . "createip,tzoffset,pagecreate,pagemodify,prefs",
        1,
        $UserID,
        $UserData{'username'},
        $encpass,
        $adminhash,
        $UserData{'lang'},
        $UserData{'email'},
        $UserData{'param'},
        $UserData{'createtime'},
        $UserData{'createip'},
        $UserData{'tzoffset'},
        $UserData{'pagecreate'},
        $UserData{'pagemodify'},
        $prefs_json,
    );
    if ( $isnewuser && $UseActivation ) {
        &SendRegMail();
    }

    # need to print log
}

sub SetPreRegFlag {
    $UserData{'param'} = sprintf( "R%08X%08X", int( rand(0x10000000) ), int( rand(0x10000000) ) );
}

sub SendRegMail {
    my $homeurl =
        &SelfUrl()
      . &ScriptLinkChar()
      . "action=activate\&uid=$UserID\&regid="
      . $UserData{'param'}
      . "\&regtime=$Now";
    my $message = <<"END_ACTIVATION_MSG";
Thank you for registering $SiteName.
Click the following link to activate your account:

  $homeurl

Your can only use your account after you activate it
END_ACTIVATION_MSG
    SendEmail( $UserData{'email'}, $EmailFrom, $UserData{'email'}, T("Account activation notice"),
        $message );
}

# == Password reset ====================================================
# A reset link carries uid, expiry and an HMAC over both plus the account's
# current password hash and param. Nothing is stored server-side: the link
# stops working when it expires or as soon as the password changes, which
# also makes it single-use. Accounts imported locked (param "R...", empty
# password) are unlocked by a successful reset, since the owner has just
# proved control of the account's email address.

sub PasswordResetSig {
    my ( $uid, $exp, $pass, $param ) = @_;
    $pass  = '' if ( !defined $pass );
    $param = '' if ( !defined $param );
    return Hmac("pwreset|$uid|$exp|$pass|$param");
}

# Returns the account row (hashref) for a valid, unexpired link, else undef.
sub PasswordResetAccount {
    my ( $uid, $exp, $sig ) = @_;
    return undef if ( !defined($uid) || $uid !~ /\A\d+\z/ || $uid < 1000 );
    return undef if ( !defined($exp) || $exp !~ /\A\d+\z/ || $exp < $Now );
    return undef if ( !defined($sig) || $sig !~ /\A[0-9a-f]{64}\z/ );
    my $userdb = DBTable($UserDir);
    return undef if ( $dbh eq "" || !SafeIdent($userdb) );
    my $row = $dbh->selectrow_hashref( "SELECT id,name,pass,email,param FROM $userdb WHERE id=?", undef, $uid );
    return undef if ( !$row );
    return undef if ( !ConstantEq( $sig, PasswordResetSig( $uid, $exp, $row->{pass}, $row->{param} ) ) );
    return $row;
}

sub DoForgotPasswordForm {
    print &GetHeader( '', T('Forgot your password?'), '' );
    print '<div class="wikiinfo">';
    print '<p>', T('Enter your user name or email address. If it matches an account, a link to set a new password will be emailed to the address on file.'), '</p>';
    print &GetFormStart();
    print &GetHiddenValue( 'forgot_pw', 1 ), "\n";
    print '<br><label class="formlabel">', T('User name or email:'), '</label>',
      $q->textfield( -name => 'p_account', -value => '', -size => 30, -maxlength => 100, -override => 1 );
    print '<br>', PrintCaptcha() if $UseCaptcha;
    print '<br>', $q->submit( -name => 'Send', -value => T('Send reset link') ), "\n";
    print '<hr class="wikilinefooter">';
    print $q->end_form;
    print '</div>';
    print &GetMinimumFooter();
}

sub DoForgotPassword {
    CSRFCheckOrDie();
    if ( $UseCaptcha && !VerifyCaptcha( &GetParam( "captchaans", "" ), &GetParam( "captchaopt", "" ) ) ) {
        PrintMsg( T("Wrong CAPTCHA Answer"), T("Error"), 1 );
    }
    my $ip_key = 'pwreset-ip:' . &RemoteAddr;
    if ( LoginThrottleBlocked($ip_key) ) {
        PrintMsg( T('Too many requests. Try again in a few minutes.'), T('Error'), 1 );
    }
    LoginThrottleHit($ip_key);

    my $account = &GetParam( "p_account", "" );
    $account =~ s/^\s+|\s+$//g;
    if ( $account ne '' && length($account) <= 100 ) {
        my $userdb = DBTable($UserDir);
        my $col    = ( $account =~ /\@/ ) ? 'email' : 'name';
        my $row;
        if ( $dbh ne "" && SafeIdent($userdb) ) {
            $row = $dbh->selectrow_hashref(
                "SELECT id,name,pass,email,param FROM $userdb WHERE UPPER($col)=UPPER(?) LIMIT 1",
                undef, $account );
        }
        if ( $row && $row->{id} >= 1000 && ValidEmail( $row->{email} // '' ) ) {
            my $mail_key = "pwreset-mail:$row->{id}";
            my $last     = $dbh->selectrow_arrayref(
                'SELECT last_ts FROM ' . Habitat::Store::T('login_attempts') . ' WHERE attempt_key=?', undef, $mail_key );
            if ( !$last || $Now - $last->[0] >= $PasswordResetMailGap ) {
                Habitat::Store::WriteDBItems( Habitat::Store::T('login_attempts'), 'attempt_key,attempts,first_ts,last_ts',
                    1, $mail_key, 1, $Now, $Now );
                &SendPasswordResetMail($row);
                AddUserLogDB( $row->{id}, 'pwreset', 'mail' );
            }
        }
    }

    # Same answer whether or not the account exists.
    print &GetHeader( '', T('Forgot your password?'), '' );
    print '<div class="wikiinfo">',
      T('If that user name or email address belongs to an account, a link to set a new password has been sent to its email address. The link is valid for 24 hours.'),
      '</div>';
    print &GetMinimumFooter();
}

sub SendPasswordResetMail {
    my ($row) = @_;
    my $exp  = $Now + $PasswordResetTTL;
    my $sig  = PasswordResetSig( $row->{id}, $exp, $row->{pass}, $row->{param} );
    my $base = ( $SiteBase ne '' ) ? $SiteBase : &SelfUrl();
    my $link = "$base?action=resetpw&uid=$row->{id}&exp=$exp&sig=$sig";
    my $hours = int( $PasswordResetTTL / 3600 );
    my $message = <<"END_RESET_MSG";
Someone (hopefully you) asked to set a new password for the account
"$row->{name}" on $SiteName.

To choose a new password, open this link within $hours hours:

  $link

The link works once. If you did not ask for this, ignore this email;
your account is unchanged.
END_RESET_MSG
    SendEmail( $row->{email}, $EmailFrom, $EmailFrom, "$SiteName: " . T('password reset'), $message );
}

sub PrintResetPasswordInvalid {
    print &GetHeader( '', T('Set a new password'), '' );
    print '<div class="wikiinfo">',
      T('This password reset link is invalid, has expired, or has already been used.'), ' ',
      &ScriptLink( "action=forgotpw", T('Request a new link') ), '</div>';
    print &GetMinimumFooter();
}

sub DoResetPasswordForm {
    my ( $uid, $exp, $sig ) = map { &GetParam( $_, "" ) } qw(uid exp sig);
    my $row = PasswordResetAccount( $uid, $exp, $sig );
    return PrintResetPasswordInvalid() if ( !$row );
    print &GetHeader( '', T('Set a new password'), '' );
    print '<div class="wikiinfo">';
    print '<p>', Ts( 'Choose a new password for %s.', QuoteHtml( $row->{name} ) ), '</p>';
    print &GetFormStart();
    print &GetHiddenValue( 'reset_pw', 1 ), &GetHiddenValue( 'uid', $uid ), &GetHiddenValue( 'exp', $exp ),
      &GetHiddenValue( 'sig', $sig ), "\n";
    print '<br><label class="formlabel">', T('New password:'), '</label>',
      $q->password_field( -name => 'p_newpass', -value => '', -size => 20, -maxlength => 100, -override => 1 );
    print '<br><label class="formlabel">', T('Repeat password:'), '</label>',
      $q->password_field( -name => 'p_newpass2', -value => '', -size => 20, -maxlength => 100, -override => 1 );
    print '<br>', $q->submit( -name => 'Save', -value => T('Set password') ), "\n";
    print '<hr class="wikilinefooter">';
    print $q->end_form;
    print '</div>';
    print &GetMinimumFooter();
}

sub DoResetPassword {
    CSRFCheckOrDie();
    my ( $uid, $exp, $sig ) = map { &GetParam( $_, "" ) } qw(uid exp sig);
    my $row = PasswordResetAccount( $uid, $exp, $sig );
    return PrintResetPasswordInvalid() if ( !$row );
    my $p1 = &GetParam( "p_newpass",  "" );
    my $p2 = &GetParam( "p_newpass2", "" );
    if ( length($p1) < 8 ) {
        PrintMsg( T('The new password must be at least 8 characters long'), T('Error'), 1 );
    }
    if ( $p1 ne $p2 ) {
        PrintMsg( T('Two passwords do not match'), T('Error'), 1 );
    }
    my $userdb = DBTable($UserDir);
    $dbh->do( "UPDATE $userdb SET pass=?, param='' WHERE id=?", undef, HashPassword($p1), $row->{id} );
    Habitat::Store::_commit_if_needed($dbh);
    LoginThrottleClear( 'name:' . lc( $row->{name} ) );
    AddUserLogDB( $row->{id}, 'pwreset', 'done' );
    print &GetHeader( '', T('Set a new password'), '' );
    print '<div class="wikiinfo">', T('Your password has been changed. You can now log in.'), ' ',
      &ScriptLink( "action=login", T('Login') ), '</div>';
    print &GetMinimumFooter();
}

sub DoSearch {
    my ($string) = @_;

    if ( $string eq '' ) {
        &DoIndex();
        return;
    }
    print &GetHeader( '', &QuoteHtml( Ts( 'Search for: %s', $string ) ), '' );
    &PrintPageList( &SearchTitleAndBody($string) );
    print &GetCommonFooter();
}

sub DoWatchPage {
    my ($id) = @_;
    CSRFCheckOrDie();
    my $watchdb = DBTable($EmailFile);
    my $user    = $UserData{'username'};

    if ( not( $UserID <= 1000 || $user eq '' || $id eq '' ) ) {
        if ( ReadDBItems( $watchdb, 'username', ',', '', "page=? and username=?", $id, $user ) eq
            '' )
        {
            &WriteDBItems( $watchdb, 'page,username', 0, ( $id, $user ) );
            AddUserLogDB( $UserID, 'watch', $id );
        }
    }
    print &GetHeader( '', T('Watch Page'), '' );
    print '<div class="wikiinfo">' . Ts( 'Watch activated for page "%s".', QuoteHtml($id) );
    print '</div>';
    print &GetCommonFooter();
}

sub DoUnWatchPage {
    my ($id) = @_;
    CSRFCheckOrDie();
    my $watchdb = DBTable($EmailFile);
    my $user    = $UserData{'username'};

    if ( $dbh && not( $UserID <= 1000 || $user eq '' || $id eq '' ) ) {
        DeleteDBItems( $watchdb, "page=? and username=?", $id, $user );
    }
    print &GetHeader( '', T('Watch Page'), '' );
    print '<div class="wikiinfo">' . Ts( 'Watch removed for page "%s".', QuoteHtml($id) );
    print '</div>';
    print &GetCommonFooter();
}

sub DoBackLinks {
    my ($string) = @_;

    print &GetHeader( '', &QuoteHtml( Ts( 'Backlinks for: %s', $string ) ), '' );

# At this time the backlinks are mostly a renamed search. An initial attempt to match links only failed on subpages
# and free links. Escape some possibly problematic characters:
    $string =~ s/([-'().,])/\\$1/g;
    &PrintPageList( &SearchTitleAndBody($string) );
    print &GetCommonFooter();
}

sub PrintPageList {
    my ( $pagename, $offs, $moretocome );
    print '<div class="wikitext">';
    $offs = 0;
    if ( $_[0] =~ /^Internal:Offset:([0-9]+)([+]*)$/ ) {
        $offs       = $1;
        $moretocome = $2;
    }
    shift(@_);
    print "<h2>", Ts( '%s pages found:', ( $#_ + 1 ) ), "</h2>\n";
    foreach $pagename (@_) {
        print ".... " if ( $pagename =~ m|/| );
        print &GetPageLink($pagename), "<br>\n";
    }
    {
        my $url;
        print "<div class='wikipager'>";
        if ( $offs >= $ListItemCount ) {
            $url =
                "search="
              . UrlEncode( &GetParam("search"), "" )
              . "&dosearch=1&offset="
              . ( $offs - $ListItemCount );
            print &ScriptLink( $url, "&laquo;" . Ts( 'Previous %s pages', $ListItemCount ) );
        }
        if ( defined($moretocome) && $moretocome ne '' ) {
            if ( $offs >= $ListItemCount ) {
                print "&nbsp;&nbsp;";
            }
            $url =
                "search="
              . UrlEncode( &GetParam("search"), "" )
              . "&dosearch=1&offset="
              . ( $offs + $ListItemCount );
            print &ScriptLink( $url, Ts( 'Next %s pages', $ListItemCount ) . "&raquo;" );
        }
        print "</div>";
    }
    print "</div>";
}

sub DoLinks {
    print &GetHeader( '', &QuoteHtml( T('Full Link List') ), '' );
    print "<hr><pre>\n\n\n\n\n";    # Extra lines to get below the logo
    &PrintLinkList( &GetFullLinkList() );
    print "</pre>\n";
    print &GetMinimumFooter();
}

sub PrintLinkList {
    my ( $pagelines, $page,  $names, $editlink );
    my ( $link,      $extra, @links, %pgExists );

    %pgExists = ();
    foreach $page ( &AllPagesList() ) {
        $pgExists{$page} = 1;
    }
    $names    = &GetParam( "names",    1 );
    $editlink = &GetParam( "editlink", 0 );
    foreach $pagelines (@_) {
        @links = ();
        foreach $page ( split( ' ', $pagelines ) ) {
            if ( $page =~ /\:/ ) {    # URL or InterWiki form
                if ( $page =~ /$UrlPattern/ ) {
                    ( $link, $extra ) = &UrlLink( $page, 0 );    # No images
                } else {
                    ( $link, $extra ) = &InterPageLink( $page, 0 );    # No images
                }
            } else {
                if ( $pgExists{$page} ) {
                    $link = &GetPageLink($page);
                } else {
                    $link = $page;
                    if ($editlink) {
                        $link .= &GetEditLink( $page, "?" );
                    }
                }
            }
            push( @links, $link );
        }
        if ( !$names ) {
            shift(@links);
        }
        print join( ' ', @links ), "\n";
    }
}

sub GetFullLinkList {
    my ( $name,     $unique,    $sort, $exists, $empty, $link, $search );
    my ( $pagelink, $interlink, $urllink );
    my ( @found,    @links,     @newlinks, @pglist, %pgExists, %seen );

    $unique    = &GetParam( "unique", 1 );
    $sort      = &GetParam( "sort",   1 );
    $pagelink  = &GetParam( "page",   1 );
    $interlink = &GetParam( "inter",  0 );
    $urllink   = &GetParam( "url",    0 );
    $exists    = &GetParam( "exists", 2 );
    $empty     = &GetParam( "empty",  0 );
    $search    = &GetParam( "search", "" );

    if ( ( $interlink == 2 ) || ( $urllink == 2 ) ) {
        $pagelink = 0;
    }
    %pgExists = ();
    @pglist   = &AllPagesList();
    foreach $name (@pglist) {
        $pgExists{$name} = 1;
    }
    %seen = ();
    foreach $name (@pglist) {
        @newlinks = ();
        if ( $unique != 2 ) {
            %seen = ();
        }
        @links = &GetPageLinks( $name, $pagelink, $interlink, $urllink );
        foreach $link (@links) {
            $seen{$link}++;
            if ( ( $unique > 0 ) && ( $seen{$link} != 1 ) ) {
                next;
            }
            if ( ( $exists == 0 ) && ( $pgExists{$link} == 1 ) ) {
                next;
            }
            if ( ( $exists == 1 ) && ( $pgExists{$link} != 1 ) ) {
                next;
            }
            if ( ( $search ne "" ) && !( $link =~ /$search/ ) ) {
                next;
            }
            push( @newlinks, $link );
        }
        @links = @newlinks;
        if ($sort) {
            @links = sort(@links);
        }
        unshift( @links, $name );
        if ( $empty || ( $#links > 0 ) ) {    # If only one item, list is empty.
            push( @found, join( ' ', @links ) );
        }
    }
    return @found;
}

sub GetPageLinks {
    my ( $name, $pagelink, $interlink, $urllink ) = @_;
    my ( $text, @links );

    @links = ();
    &OpenDefaultPage($name);
    $text = $Pages{$OpenPageName}->{'text'}->{'text'};
    $text =~ s/<html>((.|\n)*?)<\/html>/ /ig;
    $text =~ s/<nowiki>(.|\n)*?\<\/nowiki>/ /ig;
    $text =~ s/<pre>(.|\n)*?\<\/pre>/ /ig;
    $text =~ s/<code>(.|\n)*?\<\/code>/ /ig;
    if ($interlink) {
        $text =~ s/''+/ /g;    # Quotes can adjacent to inter-site links
        $text =~ s/$InterLinkPattern/push(@links, &StripUrlPunct($1)), ' '/ge;
    } else {
        $text =~ s/$InterLinkPattern/ /g;
    }
    if ($urllink) {
        $text =~ s/''+/ /g;    # Quotes can adjacent to URLs
        $text =~ s/$UrlPattern/push(@links, &StripUrlPunct($1)), ' '/ge;
    } else {
        $text =~ s/$UrlPattern/ /g;
    }
    if ($pagelink) {
        if ($FreeLinks) {
            my $fl = $FreeLinkPattern;
            $text =~ s/\[\[$fl\|[^\]]+\]\]/push(@links, &FreeToNormal($1)), ' '/ge;
            $text =~ s/\[\[$fl\]\]/push(@links, &FreeToNormal($1)), ' '/ge;
        }
        if ($WikiLinks) {
            $text =~ s/$LinkPattern/push(@links, &StripUrlPunct($1)), ' '/ge;
        }
    }
    return @links;
}

sub GetDynaPageName {
    my ( $id, $name ) = @_;
    if ( $name eq 'NEW' ) {
        return getnextnum($id);
    }
    return "";
}

sub DoPost {
    CSRFCheckOrDie();
    my ( $editDiff, $old, $newAuthor, $pgtime, $oldrev, $preview, $user, $tt );
    my $string      = &GetParam( "text",        undef );
    my $id          = &GetParam( "title",       "" );
    my $summary     = &GetParam( "summary",     "" );
    my $oldtime     = &GetParam( "oldtime",     "" );
    my $oldconflict = &GetParam( "oldconflict", "" );
    my $isEdit      = 0;
    my $editTime    = $Now;
    my $authorAddr  = &RemoteAddr;
    my ( %pagetype, $pgmode, $Page, $Text, $Section );
    my $editmode = &GetParam( "editmode", "" );
    my $redirect = &GetParam( "redirect", "" );
    my $isdynapg;

    if ( !&UserCanEdit( $id, 1 ) ) {

        # This is an internal interface--we don't need to explain
        &ReportError( Ts( 'Editing not allowed for %s.', $id ) );
        return;
    }
    if (   ( $id eq 'SampleUndefinedPage' )
        || ( $id eq T('SampleUndefinedPage') )
        || ( $id eq 'Sample_Undefined_Page' )
        || ( $id eq T('Sample_Undefined_Page') ) )
    {
        &ReportError( Ts( '%s cannot be defined.', $id ) );
        return;
    }

    if (   $UseCaptcha
        && ( &UserPermission() < 50 )
        && ( &ReadPagePermissions( $id, \%Permissions ) != -999 )
        && not VerifyCaptcha( &GetParam("captchaans"), &GetParam("captchaopt") ) )
    {
        PrintMsg( T("Wrong CAPTCHA Answer"), T("Error"), 1 );
    }
    if ( $id =~ /(.*)\/__([A-Z0-9]+)__$/ ) {
        $isdynapg = $1;
    }
    $id =~ s/(.*)\/__([A-Z0-9]+)__$/"$1\/".GetDynaPageName($1,$2)/geo;

    $string  = &RemoveFS($string);
    $summary = &RemoveFS($summary);
    $summary =~ s/[\r\n]//g;
    if ( length($summary) > 300 ) {    # Too long (longer than form allows)
        $summary = substr( $summary, 0, 300 );
    }

    # Add a newline to the end of the string (if it doesn't have one)
    if ( $editmode ne "replace" || $editmode ne "ireplace" ) {
        $string .= "\n" if ( !( $string =~ /\n$/ ) );
    }

# Lock before getting old page to prevent races Consider extracting lock section into sub, and eval-wrap it? (A few
# called routines can die, leaving locks.)

    &BuildRuleStack($id);    # added 05/13/06 by fangq
    my $pp = ReadPagePermissions( $id, \%Permissions );
    if ( ( defined( $Pages{$id}->{'clearance'} ) && &UserPermission() < $Pages{$id}->{'clearance'} )
        || ( ( $pp ne '' ) && &UserPermission() < $pp ) )
    {
        $UseCache = 0;
        $StaticCacheOK = 0;
        PrintMsg( T("no permission"), T("Error"), 1 );
    }
    $string = &ApplyRegExp( $id, $string, \%NameSpaceE1, $Pages{$id}->{'postedit'} ); # fangq 061206
    $string =~ s/<userip>/$ENV{'REMOTE_ADDR'}/gi;

    if ($LockCrash) {
        &RequestLock() or die( T('Could not get editing lock') );
    } else {
        if ( !&RequestLock() ) {
            &ForceReleaseLock('main');
        }

        # Clear all other locks.

        &ForceReleaseLock('cache');
        &ForceReleaseLock('diff');
        &ForceReleaseLock('index');
    }
    &OpenDefaultPage($id);

    $Page    = \%{ $Pages{$id}->{'page'} };
    $Section = \%{ $Pages{$id}->{'section'} };
    $Text    = \%{ $Pages{$id}->{'text'} };

    $old     = $$Text{'text'};
    $oldrev  = $$Section{'revision'};
    $pgtime  = $$Section{'ts'};
    $preview = 0;
    $preview = 1 if ( &GetParam( "Preview", "" ) ne "" );

    $string =~ s/\r\n\s*$/\n/g;

    if ( !$preview && ( $old eq $string ) ) {    # No changes (ok for preview)
        &ReleaseLock();
        &ReBrowsePage( $id, "", 1 );
        return;
    }
    if ( ( $UserID > 399 ) || ( $$Section{'id'} > 399 ) ) {
        $newAuthor = ( $UserID ne $$Section{'id'} );    # known user(s)
    } else {
        $newAuthor = ( $$Section{'ip'} ne $authorAddr );    # hostname fallback
    }
    $newAuthor = 1 if ( $oldrev == 0 );                     # New page
    $newAuthor = 0 if ( !$newAuthor );                      # Standard flag form, not empty
        # Detect editing conflicts and resubmit edit
    if ( ( $oldrev > 0 ) && ( $newAuthor && ( $oldtime - $pgtime != 0 ) ) ) {
        &ReleaseLock();
        if ( $oldconflict > 0 ) {    # Conflict again...
            &DoEdit( $id, 2, $pgtime, $string, $preview );
        } else {
            &DoEdit( $id, 1, $pgtime, $string, $preview );
        }
        return;
    }

    if ($preview) {
        &ReleaseLock();
        &DoEdit( $id, 0, $pgtime, $string, 1 );
        return;
    }
    $user = &GetParam( "username", "" );

    # If the person doing editing chooses, send out email notification
    if ($EmailNotify) {
        &EmailNotify( $id, $user ) if &GetParam( "do_email_notify", "" ) eq 'on';
    }
    if ( &GetParam( "recent_edit", "" ) eq 'on' ) {
        $isEdit = 1;
    }
    if ( !$isEdit ) {
        &SetPageCache( 'oldmajor', $$Section{'revision'} );
    }
    if ($newAuthor) {
        &SetPageCache( 'oldauthor', $$Section{'revision'} );
    }

    if ( $id =~ /^(.+)\/\.v[01]$/ ) {
        RemovePageCache($1);
    }

    if ( $editmode eq "prepend" ) {
        if ( not( $$Text{'text'} eq $NewText . "\n" ) ) {
            $string = $string . $$Text{'text'};
        }
    } elsif ( $editmode eq "append" ) {
        if ( not( $$Text{'text'} eq $NewText . "\n" ) ) {
            $string = $$Text{'text'} . $string;
        }
    } elsif ( $editmode eq "replace" || $editmode eq "ireplace" ) {
        my $kf = &GetParam( "keyfield", "" );
        my $kb = &GetParam( "keyblock", "" );
        my $kv = &GetParam( "keyval",   "" );

        if ( $kf ne "" && $kb ne "" && $kv ne "" ) {
            my @vv = split( /(<\/$kb>)/, $old );
            if ( not $vv[-1] =~ /[a-zA-Z0-9]/ ) { delete $vv[-1]; }
            for ( my $i = 0 ; $i < @vv ; $i++ ) {
                if ( $vv[$i] =~ /<$kf>\s*$kv\s*<\/$kf>/ ) {
                    if ( $i + 1 < @vv && $vv[ $i + 1 ] eq "</$kb>" ) { delete $vv[ $i + 1 ]; }
                    if ( $editmode eq "replace" ) {
                        delete $vv[$i];
                        $string .= join( "", @vv );
                    } else {
                        $string =~ s/^\s*//s;
                        $string =~ s/\s*$//s;
                        $vv[$i] = $string;
                        $string = join( "", @vv );
                    }
                    last;
                }
            }
        }
    }
    $string .= "\n" if ( !( $string =~ /\n$/ ) );

    # Stage 5: every edit (major or minor) gets its own row in
    # page_revisions. The legacy inline-diff blob (FS4-chained patch
    # chain stored inside page.text) is gone; the $isEdit flag is now
    # just metadata, not a write-path optimization.
    $$Text{'text'}      = $string;
    $$Text{'minor'}     = $isEdit;
    $$Text{'newauthor'} = $newAuthor;
    $$Text{'summary'}   = $summary;
    $$Section{'host'}   = &GetRemoteHost(1);
    &SaveDefaultText($id);
    $pgmode = $Pages{$id}->{'clearance'};
    if ( !defined($pgmode) ) { $pgmode = 0; }

    &SavePageDB($id);
    &WriteRcLogDB( $id, $summary, $isEdit, $editTime, $$Section{'revision'},
        $user, $$Section{'host'}, $pgmode );
    AddUserLogDB( $UserID, 'Wr', $id ) if ( $UserID >= 1000 );

    if ($UseCache) {
        my $htmldb   = DBTable($HtmlDir);
        my $language = &GetParam( "lang", $LangID );
        if ( $dbh eq "" || $htmldb eq "" ) {
            die( T('ERROR: database uninitialized!') );
        }
        DeleteDBItems( $htmldb, "id=?", "$id\[$language\]" );
        if ( $isdynapg ne '' ) {
            DeleteDBItems( $htmldb, "id=?", "$isdynapg\[$language\]" );
        }

    }
    &ReleaseLock();
    if ( $redirect ne "" ) {
        print &GetRedirectPage( $redirect,
            T("if your browser does not support redirect, please click this link"), 0 );
    } else {
        &ReBrowsePage( $id, "", 1 );
    }
}

sub UpdateDiffs {
    my ( $id, $editTime, $old, $new, $isEdit, $newAuthor, $diffstr ) = @_;
    my ( $editDiff, $oldMajor, $oldAuthor );

    if ( not defined($diffstr) ) {
        $editDiff = &GetDiff( $old, $new, 0 );    # 0 = already in lock
    } else {
        $editDiff = $diffstr;
    }
    $oldMajor  = &GetPageCache('oldmajor');
    $oldAuthor = &GetPageCache('oldauthor');
    &SetPageCache( 'diff_default_minor', $editDiff );
    if ( $isEdit || !$newAuthor ) {
        &OpenKeptRevisions( $id, 'text_default' );
    }
    if ( !$isEdit ) {
        &SetPageCache( 'diff_default_major', "1" );
    } else {
        &SetPageCache( 'diff_default_major', &GetKeptDiff( $new, $oldMajor, 0 ) );
    }
    if ($newAuthor) {
        &SetPageCache( 'diff_default_author', "1" );
    } elsif ( $oldMajor == $oldAuthor ) {
        &SetPageCache( 'diff_default_author', "2" );
    } else {
        &SetPageCache( 'diff_default_author', &GetKeptDiff( $new, $oldAuthor, 0 ) );
    }
}

# Translation note: the email messages are still sent in English Send an email message.
# Conservative address check used before an address is stored or
# handed to the mailer: no whitespace, quotes or shell/header
# metacharacters, and a leading alphanumeric so it can never be read
# as a command-line option.
sub ValidEmail {
    my ($addr) = @_;
    return 0 if ( !defined($addr) || length($addr) > 254 );
    return $addr =~
      /\A[A-Za-z0-9][A-Za-z0-9._%+-]*\@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+\z/
      ? 1
      : 0;
}

sub SendEmail {
    my ( $to, $from, $reply, $subject, $message ) = @_;

    # The recipient is user-supplied (registration form). Refuse anything
    # that is not a plain address, and strip line breaks from every
    # header field so nothing can inject extra headers (e.g. Bcc:).
    if ( !ValidEmail($to) ) {
        warn "SendEmail: refusing invalid recipient address\n";
        return;
    }
    s/[\r\n]+/ /g for ( $from, $reply, $subject );

    if ( $SendMail =~ /\/mail$/ ) {
        &MailEmail( $to, $from, $reply, $subject, $message );
        return;
    }

    # sendmail options: -oi : do not treat a lone "." line as end of input.
    # The recipient is passed as its own argument (as on the legacy
    # NeuroJSON wiki) through a list-form pipe open, so no shell ever
    # parses it.
    my $fh;
    if ( !open( $fh, '|-', $SendMail, '-oi', $to ) ) {
        warn "Can't send email: $!\n";
        return;
    }
    print $fh <<"EOF";
From: $from
To: $to
Reply-to: $reply
Subject: $subject\n
$message
EOF
    close($fh) or warn "sendmail didn't close nicely";
}

# Translation note: the email messages are still sent in English Send an email message.
sub MailEmail {
    my ( $to, $from, $reply, $subject, $message ) = @_;
    my $fh;
    if ( !open( $fh, '|-', $SendMail, '-s', $subject, $to ) ) {
        warn "Can't send email: $!\n";
        return;
    }
    print $fh <<"EOF";
$message
EOF
    close($fh) or warn "mail didn't close nicely";
}

sub ReadWatchListDB {
    my ($id) = @_;
    my ( $addr, $userlist );
    my $watchdb = DBTable($EmailFile);
    my $userdb  = DBTable($UserDir);

    if ( $dbh eq "" || $watchdb eq "" || $userdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $userlist = ReadDBItems( $watchdb, 'username', "\n", '', "page=?", $id );
    if ( $userlist ne '' ) {
        my @users        = split( /\n/, $userlist );
        my $placeholders = join( ',', ('?') x scalar(@users) );
        $addr = ReadDBItems( $userdb, 'email', ',', '', "name IN ($placeholders)", @users );
    }
    return $addr;
}

## Email folks who want to know a note that a page has been modified. - JimM.
sub EmailNotify {
    local $/ = "\n";    # don't slurp whole files in this sub.

    if ($EmailNotify) {
        my ( $id, $user ) = @_;
        if ($user) {
            $user = " by $user";
        }
        my $address;
        $address = &ReadWatchListDB($id);

        my $home_url        = &SelfUrl();
        my $page_url        = $home_url . "?" . &UrlEncode("$id");
        my $editors_summary = $q->param("summary");
        if ( ( $editors_summary eq "*" ) or ( $editors_summary eq "" ) ) {
            $editors_summary = "";
        } else {
            $editors_summary = "\n Summary: $editors_summary";
        }
        my $content = <<"END_MAIL_CONTENT";

 The $SiteName page $id at
   $page_url
 has been changed$user to revision $Pages{$id}->{'page'}->{revision}. $editors_summary

 (Replying to this notification will
  send email to the entire mailing list,
  so only do that if you mean to.

  To remove yourself from this list, visit
  ${home_url}?action=editprefs .) 
END_MAIL_CONTENT
        my $subject = "The $id page at $SiteName has been changed.";

# I'm setting the "reply-to" field to be the same as the "to:" field which seems appropriate for a mailing list,
# especially since the $EmailFrom string needn't be a real email address.
        &SendEmail( $address, $EmailFrom, $address, $subject, $content );
    }
}

sub SearchTitleAndBody {
    my ($string) = @_;
    my ( $name, $freeName, @found, @keywords, %cmd, $searchcmd, $sth, $pagedb, $rev, $lim,
        $offset );

    $lim = GetParam( 'listc', $ListItemCount ) + 1;

    $offset = GetParam( 'offset', 0 );

    $pagedb   = DBTable($PageDir);
    @keywords = split( /&&/, $string );
    foreach my $searchstr (@keywords) {
        if ( $searchstr =~ /^\s*([a-z0-9]+)\s*=\s*(.*)\s*/ ) {
            if ( $1 eq "author" || $1 eq "text" || $1 eq "summary" ) {
                $cmd{ $1 . "=" } = $2;
            }
        } elsif ( $searchstr =~ /^\s*([a-z0-9]+)\s*=~\s*(.*)\s*/ ) {
            if ( $1 eq "author" || $1 eq "text" || $1 eq "summary" ) {
                $cmd{ $1 . " LIKE " } = "%$2%";
            }
        } else {
            $cmd{"text LIKE "} = "%$searchstr%";
        }
    }
    $searchcmd = "";
    my @binds;
    foreach my $key ( keys %cmd ) {

      # $key is one of "text=", "author=", "summary=", "text LIKE ", "author LIKE ", "summary LIKE "
      # — all whitelisted above; values are bound as parameters.
        if ( length($searchcmd) ) { $searchcmd .= " AND "; }
        $searchcmd .= "$key ? ";
        push @binds, $cmd{$key};
    }
    if ( $searchcmd eq "" ) { return (); }
    die("SearchTitleAndBody: unsafe table name") if ( !SafeIdent($pagedb) );
    $lim       = int($lim);
    $offset    = int($offset);
    $searchcmd = "select id from $pagedb where $searchcmd group by id limit $lim";
    $searchcmd .= " offset $offset" if ( $offset > 0 );
    $sth = $dbh->selectall_arrayref( $searchcmd, undef, @binds );

    if ( defined $sth->[0] ) {
        foreach my $rec ( @{$sth} ) {
            my ($pgid) = @$rec;
            push( @found, $pgid );
        }
        if ( @{$sth} == $lim ) {
            pop(@found);
            return ( "Internal:Offset:$offset+", @found );
        }
    }
    return ( "Internal:Offset:$offset", @found );

}

sub SearchBody {
    my ($string) = @_;
    my ( $name, @found );
    return &SearchTitleAndBody($string);
}

sub UnlinkHtmlCache {
    my ($id) = @_;
    my $idFile;

    $idFile = &GetHtmlCacheFile($id);
    if ( -f $idFile ) {
        unlink($idFile);
    }
}

sub NewPageCacheClear {
    my ($id) = @_;
    my $htmldb = DBTable($HtmlDir);

    if ( $dbh eq "" || $htmldb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("NewPageCacheClear: unsafe table name") if ( !SafeIdent($htmldb) );
    my $sth = $dbh->prepare("delete from $htmldb");
    $sth->execute();
}

# Note: all diff and recent-list operations should be done within locks.
sub DoUnlock {
    my $LockMessage = T('Normal Unlock.');

    print &GetHeader( '', T('Removing edit lock'), '' );
    print '<p>', T('This operation may take several seconds...'), "\n";
    if ( &ForceReleaseLock('main') ) {
        $LockMessage = T('Forced Unlock.');
    }
    &ForceReleaseLock('cache');
    &ForceReleaseLock('diff');
    &ForceReleaseLock('index');
    print "<br><h2>$LockMessage</h2>";
    print &GetCommonFooter();
}

sub WriteRcLogDB {
    my ( $id, $summary, $isEdit, $editTime, $revision, $name, $rhost, $isadmin ) = @_;
    my ( $extraTemp, $rclogdb, $sth );
    $rclogdb = DBTable($RcFile);
    if ( $dbh eq "" || $rclogdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("WriteRcLogDB: unsafe table name") if ( !SafeIdent($rclogdb) );
    $isadmin = 0 if ( $isadmin eq '' || !defined($isadmin) );
    $sth     = $dbh->prepare(
"insert into $rclogdb (time,id,summary,isedit,host,kind,userid,name,revision,isadmin) values (?,?,?,?,?,?,?,?,?,?)"
    );
    $sth->execute( $editTime, $id, $summary, $isEdit, $rhost, "0", $UserID, $name, $revision,
        $isadmin );
}

sub UserIsEditorOrError {
    if ( !&UserIsEditor() ) {
        print '<div class="wikiinfo">',
          T('This operation is restricted to site editors only...') . "</div>";
        print &GetCommonFooter();
        return 0;
    }
    return 1;
}

sub UserIsAdminOrError {
    if ( !&UserIsAdmin() ) {
        print '<div class="wikiinfo">',
          T('This operation is restricted to administrators only...') . "</div>";
        print &GetCommonFooter();
        return 0;
    }
    return 1;
}

sub DoEditLock {
    my ($fname);

    CSRFCheckOrDie();
    print &GetHeader( '', T('Set or Remove global edit lock'), '' );
    return if ( !&UserIsAdminOrError() );
    $fname = "$DataDir/noedit";
    if ( &GetParam( "set", 1 ) ) {
        &WriteDBItems( Habitat::Store::T("system"), 'id,data,time', 1, ( "lockstate", "1", $Now ) );
        print '<div class="wikiinfo">', T('Edit lock created.'), '</div>';
    } else {
        &WriteDBItems( Habitat::Store::T("system"), 'id,data,time', 1, ( "lockstate", "0", $Now ) );
        print '<div class="wikiinfo">', T('Edit lock removed.'), '</div>';
    }
    print &GetCommonFooter();
}

sub DoPageLock {
    my ( $fname, $id, $tag, $lockdb );

    CSRFCheckOrDie();
    print &GetHeader( '', T('Set or Remove page edit lock'), '' );

    # Consider allowing page lock/unlock at editor level?
    return if ( !&UserIsAdminOrError() );
    $id = &GetParam( "id", "" );
    if ( $id eq "" ) {
        print '<p>', T('Missing page id to lock/unlock...');
        return;
    }
    return if ( !&ValidIdOrDie($id) );    # Consider nicer error?
    $lockdb = DBTable($LockDir);
    $tag    = ReadDBItems( $lockdb, 'tag', '', '', "id=?", $id );
    if ( &GetParam( "set", 1 ) ) {
        if ( not $tag =~ /L/ ) {
            $tag .= "L";
            WriteDBItems( $lockdb, 'id,tag', 1, ( $id, $tag ) );
        }
    } else {
        if ( $tag =~ /L/ ) {
            $tag =~ s/L//g;
            WriteDBItems( $lockdb, 'id,tag', 1, ( $id, $tag ) );
        }
    }
    print '<div class="wikiinfo">';
    if ( &GetParam( "set", 1 ) ) {
        print Ts( 'Lock for %s created.', $id );
    } else {
        print Ts( 'Lock for %s removed.', $id );
    }
    print '</div>';
    print &GetCommonFooter();
}

sub UpdatePageLogDB {
    my ( $dbname, $id ) = @_;
    return if ( $UseDetailedLog != 1 );
    if ( $dbh eq "" || $dbname eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("UpdatePageLogDB: unsafe table name '$dbname'") if ( !SafeIdent($dbname) );
    # Visit counter: bump the row, create it on the first visit. (The
    # old insert-then-update form hit a duplicate-key error on every
    # repeat visit, and died on commit() under AutoCommit.) A race
    # between two first visits loses one count, which is harmless.
    my $n = $dbh->do( "update $dbname set lastvisit=?, visit=visit+1 where id=?", undef, $Now, $id );
    if ( defined $n && $n == 0 ) {
        local $dbh->{PrintError} = 0;
        local $dbh->{RaiseError} = 0;
        $dbh->do( "insert into $dbname (id,lastvisit,visit,x,y,z) values (?,?,1,-1,-1,-1)", undef, $id, $Now );
    }
    Habitat::Store::_commit_if_needed($dbh);
}

sub AddUserLogDB {
    my ( $uid, $action, $target ) = @_;
    my $dbname = DBTable($UserLog);
    return if ( $UseDetailedLog != 1 );
    if ( $dbh eq "" || $dbname eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("AddUserLogDB: unsafe table name '$dbname'") if ( !SafeIdent($dbname) );
    my $sth = $dbh->prepare("insert into $dbname (id,time,ip,action,target) values (?,?,?,?,?);");
    $sth->execute( $uid, $Now, &RemoteAddr, $action, $target );
    Habitat::Store::_commit_if_needed($dbh);
}

sub DoEditBanned {
    my ( $banList, $status );

    print &GetHeader( "", T("Editing Banned list"), "" );
    return if ( !&UserIsAdminOrError() );
    $banList = ReadDBItems( Habitat::Store::T("system"), 'data', "\n", '', "id=?", 'banlist' );
    $status  = 1;

    $banList = "" if ( !$status );
    print &GetFormStart();
    print '<div class="wikiinfo">';
    print GetHiddenValue( "edit_ban", 1 ), "\n";
    print "<b>Banned IP/network/host list:</b><br>\n";
    print "<p>Each entry is either a commented line (starting with #), ",
      "or a Perl regular expression (matching either an IP address or ",
      "a hostname).  <b>Note:</b> To test the ban on yourself, you must ",
      "give up your admin access (remove password in Preferences).";
    print "<p>Example:<br>",
      "# blocks hosts ending with .foocorp.com<br>",
      "\\.foocorp\\.com\$<br>",
      "# blocks exact IP address<br>",
      "^123\\.21\\.3\\.9\$<br>",
      "# blocks whole 123.21.3.* IP network<br>",
      "^123\\.21\\.3\\.\\d+\$<p>";
    print &GetTextArea( 'banlist', $banList, 12, 50 );
    print "<br>", $q->submit( -name => 'Save' ), "\n";
    print '<hr class="wikilinefooter">';
    print $q->end_form;
    print "</div>\n";
    print &GetMinimumFooter();
}

sub DoUpdateBanned {
    my ( $newList, $fname );

    CSRFCheckOrDie();
    print &GetHeader( "", T("Updating Banned list"), "" );
    return if ( !&UserIsAdminOrError() );
    $fname   = "$DataDir/banlist";
    $newList = &GetParam( "banlist", "#Empty file" );
    print '<div class="wikiinfo">';
    if ( $newList eq "" ) {
        print "<p>Empty banned list or error.";
        print "<p>Resubmit with at least one space character to remove.";
    } elsif ( $newList =~ /^\s*$/s ) {
        WriteDBItems( Habitat::Store::T("system"), 'id,data,time', 1, ( "banlist", "", $Now ) );

        print "<p>Removed banned list";
    } else {
        WriteDBItems( Habitat::Store::T("system"), 'id,data,time', 1, ( "banlist", $newList, $Now ) );
        print "<p>Updated banned list";
    }
    print "</div>\n";
    print &GetCommonFooter();
}

# ==== Editing/Deleting pages and links ====
sub DoEditLinks {
    print &GetHeader( "", "Editing Links", "" );
    if ($AdminDelete) {
        return if ( !&UserIsAdminOrError() );
    } else {
        return if ( !&UserIsEditorOrError() );
    }
    print '<div class="wikitext">';
    print &GetFormStart();
    print GetHiddenValue( "edit_links", 1 ), "\n";
    print "<b>" . T('Editing/Deleting page titles') . ":</b><br>\n";
    print "<p>Enter one command on each line.  Commands are:<br>",
      "<tt>!PageName</tt> -- deletes the page called PageName<br>\n",
      "<tt>=OldPageName=NewPageName</tt> -- Renames OldPageName ",
      "to NewPageName and updates links to OldPageName.<br>\n",
      "<tt>|OldPageName|NewPageName</tt> -- Changes links to OldPageName ",
      "to NewPageName.",
      " (Used to rename links to non-existing pages.)<br>\n",
      "<b>Note: page names are case-sensitive!</b>\n";
    print &GetTextArea( 'commandlist', "", 12, 50 );
    print $q->checkbox(
        -name     => "p_changerc",
        -override => 1,
        -checked  => 1,
        -label    => "Edit $RCName"
    );
    print "<br>\n";
    print $q->checkbox(
        -name     => "p_changetext",
        -override => 1,
        -checked  => 1,
        -label    => T("Substitute text for rename")
    );
    print "<br>", $q->submit( -name => 'Edit' ), "\n";
    print '<hr class="wikilinefooter">';
    print $q->end_form;
    print "</div>";
    print &GetMinimumFooter();
}

sub UpdateLinksList {
    my ( $commandList, $doRC, $doText ) = @_;

    if ($doText) {
        &BuildLinkIndex();
    }
    &RequestLock() or die T('UpdateLinksList could not get main lock');
    foreach ( split( /\n/, $commandList ) ) {
        s/\s+$//g;
        next if ( !(/^[=!|]/) );    # Only valid commands.
        print T("Processing") . " $_<br>\n";
        if (/^\!([^,]+)\s*$/) {
            &DeletePage( $1, $doRC, $doText );
        } elsif (/^\!(.+),([0-9.]+)/) {
            &DeletePage( $1, $doRC, $doText, $2 );
        } elsif (/^\=(?:\[\[)?([^]=]+)(?:\]\])?\=(?:\[\[)?([^]=]+)(?:\]\])?/) {
            &RenamePage( $1, $2, $doRC, $doText );
        } elsif (/^\|(?:\[\[)?([^]|]+)(?:\]\])?\|(?:\[\[)?([^]|]+)(?:\]\])?/) {
            &RenameTextLinks( $1, $2 );
        }
    }
    &NewPageCacheClear();
    &ReleaseLock();
}

sub BuildLinkIndex {
    my ( @pglist, $page, @links, $link, %seen );

    @pglist    = &AllPagesList();
    %LinkIndex = ();
    foreach $page (@pglist) {
        &BuildLinkIndexPage($page);
    }
}

sub BuildLinkIndexPage {
    my ($page) = @_;
    my ( @links, $link, %seen );

    @links = &GetPageLinks( $page, 1, 0, 0 );
    %seen  = ();
    foreach $link (@links) {
        if ( defined( $LinkIndex{$link} ) ) {
            if ( !$seen{$link} ) {
                $LinkIndex{$link} .= " " . $page;
            }
        } else {
            $LinkIndex{$link} .= " " . $page;
        }
        $seen{$link} = 1;
    }
}

sub DoUpdateLinks {
    my ( $commandList, $doRC, $doText );

    CSRFCheckOrDie();
    print &GetHeader( "", T('Updating Links'), "" );
    if ($AdminDelete) {
        return if ( !&UserIsAdminOrError() );
    } else {
        return if ( !&UserIsEditorOrError() );
    }
    $commandList = &GetParam( "commandlist", "" );
    $doRC        = &GetParam( "p_changerc",  "0" );
    $doRC        = 1 if ( $doRC eq "on" );
    $doText      = &GetParam( "p_changetext", "0" );
    $doText      = 1 if ( $doText eq "on" );

    print '<div class="wikitext">';
    if ( $commandList eq "" ) {
        print "<p>Empty command list or error.";
    } else {
        &UpdateLinksList( $commandList, $doRC, $doText );
        print "<p>Finished command list.";
    }
    print "</div>";

    print &GetCommonFooter();
}

sub DeletePageRevisionFrom {
    my ( $page, $major, $minor ) = @_;
    my $pagedb = &GetPageDB($page);
    my $revdb  = "${pagedb}_revisions";

    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("DeletePageRevisionFrom: unsafe table name") if ( !SafeIdent($pagedb) );
    die("DeletePageRevisionFrom: unsafe table name") if ( !SafeIdent($revdb) );

    # Stage 5: the legacy inline-diff chain is gone; the $minor index
    # no longer maps to a position inside the text blob. Every
    # revision is now its own row in either `page` (current) or
    # `page_revisions` (history). Delete the matching revision row.
    if ( $minor && $minor > 0 ) {

        # Historical revisions: revision = $major - $minor convention
        # used to be the inline-diff index; with proper rows we just
        # delete the page_revisions row at $major. Keep the call
        # signature for backward source compat; ignore $minor.
    }
    DeleteDBItems( $revdb, "page_id=? AND revision=?", $page, $major );
}

# Delete and rename must be done inside locks.
sub DeletePage {
    my ( $page, $doRC, $doText, $rev ) = @_;
    my ( $fname, $status, $res );

    &PurgeStaticCache();

    $page =~ s/ /_/g;
    $page =~ s/\[+//;
    $page =~ s/\]+//;
    $status = &ValidId($page);
    if ( $status ne "" ) {
        print "Delete-Page: page $page is invalid, error is: $status<br>\n";
        return;
    }
    my $pagedb  = &GetPageDB($page);
    my $rclogdb = DBTable($RcFile);
    my $htmldb  = DBTable($HtmlDir);

    if ( $dbh eq "" || $pagedb eq "" || $rclogdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    if ( $rev ne "" && $rev >= 0 ) {
        if ( $rev =~ /^([0-9]+)\.([0-9]+)/ && $2 > 0 ) {
            my ( $maj, $min ) = ( $1, $2 );
            $res = &CopyDBItems( $pagedb, "deleted$pagedb", "id=? and revision=?", $page, $maj );
            $res = &DeletePageRevisionFrom( $page, $maj, $min );
            $res = &DeleteDBItems( $rclogdb, "id=? and revision=?", $page, $rev ) if ($doRC);
        } else {
            $res = &CopyDBItems( $pagedb, "deleted$pagedb", "id=? and revision=?", $page, $rev );
            $res = &DeleteDBItems( $pagedb,  "id=? and revision=?", $page, $rev );
            $res = &DeleteDBItems( $rclogdb, "id=? and revision=?", $page, $rev ) if ($doRC);
        }
    } else {
        $res = &CopyDBItems( $pagedb, "deleted$pagedb", "id=?", $page );
        $res = &DeleteDBItems( $pagedb,  "id=?", $page );
        $res = &DeleteDBItems( $rclogdb, "id=?", $page ) if ($doRC);
    }
    $res = &DeleteDBItems( $htmldb, "id LIKE ?", "$page\[%\]" );
    &WriteRcLogDB( $page, GetParam( "summary", "" ),
        2, $Now, 0, $UserData{'username'}, $UserData{'email'}, 0 );
    AddUserLogDB( $UserID, 'De', $page ) if ( $UserID >= 1000 );
    return $res;

}

# Given text, returns substituted text
sub SubstituteTextLinks {
    my ( $old, $new, $text ) = @_;

    # Much of this is taken from the common markup
    %$SaveUrl      = ();
    $$SaveUrlIndex = 0;
    $text =~ s/$FS(\d)/$1/g;    # Remove separators (paranoia)
    if ($RawHtml) {
        $text =~ s/(<html>((.|\n)*?)<\/html>)/&StoreRaw($1)/ige;
    }
    $text =~ s/(<pre>((.|\n)*?)<\/pre>)/&StoreRaw($1)/ige;
    $text =~ s/(<code>((.|\n)*?)<\/code>)/&StoreRaw($1)/ige;
    $text =~ s/(<nowiki>((.|\n)*?)<\/nowiki>)/&StoreRaw($1)/ige;
    if ($FreeLinks) {
        $text =~ s/\[\[$FreeLinkPattern\|([^\]]+)\]\]/&SubFreeLink($1,$2,$old,$new)/geo;
        $text =~ s/\[\[$FreeLinkPattern\]\]/&SubFreeLink($1,"",$old,$new)/geo;
    }
    if ($BracketText) {         # Links like [URL text of link]
        $text =~ s/(\[$UrlPattern\s+([^\]]+?)\])/&StoreRaw($1)/geo;
        $text =~ s/(\[$InterLinkPattern\s+([^\]]+?)\])/&StoreRaw($1)/geo;
    }
    $text =~ s/(\[?$UrlPattern\]?)/&StoreRaw($1)/geo;
    $text =~ s/(\[?$InterLinkPattern\]?)/&StoreRaw($1)/geo;
    if ($WikiLinks) {
        $text =~ s/$LinkPattern/&SubWikiLink($1, $old, $new)/geo;
    }

    # Thanks to David Claughton for the following fix
    1 while $text =~ s/$FS(\d+)$FS/$$SaveUrl{$1}/ge;    # Restore saved text
    return $text;
}

sub SubFreeLink {
    my ( $link, $name, $old, $new ) = @_;
    my ($oldlink);

    $oldlink = $link;
    $link =~ s/^\s+//;
    $link =~ s/\s+$//;
    if ( ( $link eq $old ) || ( &FreeToNormal($old) eq &FreeToNormal($link) ) ) {
        $link = $new;
    } else {
        $link = $oldlink;    # Preserve spaces if no match
    }
    $link = "[[$link";
    if ( $name ne "" ) {
        $link .= "|$name";
    }
    $link .= "]]";
    return &StoreRaw($link);
}

sub SubWikiLink {
    my ( $link, $old, $new ) = @_;
    my ($newBracket);

    $newBracket = 0;
    if ( $link eq $old ) {
        $link = $new;
        if ( !( $new =~ /^$LinkPattern$/ ) ) {
            $link = "[[$link]]";
        }
    }
    return &StoreRaw($link);
}

# Legacy flat-file Keep format (FS1/FS2/FS3-separated text in
# $KeepDir/.../<page>.kp). The wiki has been SQL-backed since
# Stage 0; this function only fires if someone has an old `.kp`
# file on disk. New writes never produce one. Leaving the
# original FS-byte parser intact here is the safest path.
sub RenameKeepText {
    my ( $page,     $old,    $new ) = @_;
    my ( $fname,    $status, $data, @kplist, %tempSection, $changed );
    my ( $sectName, $newText );

    $fname = $KeepDir . "/" . &GetPageDirectory($page) . "/$page.kp";
    return if ( !( -f $fname ) );
    ( $status, $data ) = &ReadFile($fname);
    return if ( !$status );
    @kplist = split( /$FS1/, $data, -1 );      # -1 keeps trailing null fields
    return         if ( @kplist == 0 );        # Also empty
    shift(@kplist) if ( $kplist[0] eq "" );    # First can be empty
    return         if ( @kplist == 0 );        # Also empty
    %tempSection = split( /$FS2/, $kplist[0], -1 );

    if ( !defined( $tempSection{'keepts'} ) ) {
        return;
    }

    # First pass: optimize for nothing changed
    $changed = 0;
    foreach (@kplist) {
        %tempSection = split( /$FS2/, $_, -1 );
        $sectName    = $tempSection{'name'};
        if ( $sectName =~ /^(text_)/ ) {
            %{ $Pages{$page}->{'text'} } = split( /$FS3/, $tempSection{'data'}, -1 );
            $newText = &SubstituteTextLinks( $old, $new, $Pages{$page}->{'text'}->{'text'} );
            $changed = 1 if ( $Pages{$page}->{'text'}->{'text'} ne $newText );
        }
    }
    return if ( !$changed );    # No sections changed
    open( OUT, ">$fname" ) or return;
    foreach (@kplist) {
        %tempSection = split( /$FS2/, $_, -1 );
        $sectName    = $tempSection{'name'};
        if ( $sectName =~ /^(text_)/ ) {
            %{ $Pages{$page}->{'text'} } = split( /$FS3/, $tempSection{'data'}, -1 );
            $newText = &SubstituteTextLinks( $old, $new, $Pages{$page}->{'text'}->{'text'} );
            $Pages{$page}->{'text'}->{'text'} = $newText;
            $tempSection{'data'}              = join( $FS3, %{ $Pages{$page}->{'text'} } );
            print OUT $FS1, join( $FS2, %tempSection );
        } else {
            print OUT $FS1, $_;
        }
    }
    close(OUT);
}

sub RenameTextLinks {
    my ( $old,          $new ) = @_;
    my ( $changed,      $file,     $page, $section, $oldText, $newText, $status );
    my ( $oldCanonical, @pageList, $Page, $Section, $Text );

    $old =~ s/ /_/g;
    $oldCanonical = &FreeToNormal($old);
    $new =~ s/ /_/g;
    $status = &ValidId($old);
    if ( $status ne "" ) {
        print "Rename-Text: old page $old is invalid, error is: $status<br>\n";
        return;
    }
    $status = &ValidId($new);
    if ( $status ne "" ) {
        print "Rename-Text: new page $new is invalid, error is: $status<br>\n";
        return;
    }
    $old =~ s/_/ /g;
    $new =~ s/_/ /g;

    # Note: the LinkIndex must be built prior to this routine
    return if ( !defined( $LinkIndex{$oldCanonical} ) );
    @pageList = split( ' ', $LinkIndex{$oldCanonical} );
    foreach $page (@pageList) {
        $changed = 0;

        &OpenPageDB($page);
        $Page    = \%{ $Pages{$page}->{'page'} };
        $Section = \%{ $Pages{$page}->{'section'} };
        $Text    = \%{ $Pages{$page}->{'text'} };

        foreach $section ( keys %$Page ) {
            if ( $section =~ /^text_/ ) {
                &OpenSection( $page, $section );

                # Stage 5: $$Section{data} is a hashref. Legacy
                # fallback handles the older FS3-joined form.
                if ( ref( $$Section{'data'} ) eq 'HASH' ) {
                    %$Text = %{ $$Section{'data'} };
                } else {
                    %$Text = split( /$FS3/, $$Section{'data'}, -1 );
                }
                $oldText = $$Text{'text'};
                $newText = &SubstituteTextLinks( $old, $new, $oldText );
                if ( $oldText ne $newText ) {
                    $$Text{'text'}    = $newText;
                    $$Section{'data'} = {%$Text};
                    $$Page{$section}  = {%$Section};
                    $changed          = 1;
                }
            } elsif ( $section =~ /^cache_diff/ ) {
                $oldText = $$Page{$section};
                $newText = &SubstituteTextLinks( $old, $new, $oldText );
                if ( $oldText ne $newText ) {
                    $$Page{$section} = $newText;
                    $changed = 1;
                }
            }

            # Add other text-sections (categories) here
        }
        &RenameKeepText( $page, $old, $new );
    }
}

sub RenamePage {
    my ( $old, $new, $doRC, $doText ) = @_;
    my ( $oldfname, $newfname, $oldkeep, $newkeep, $status );

    &PurgeStaticCache();

    $old =~ s/ /_/g;
    $new    = &FreeToNormal($new);
    $status = &ValidId($old);
    if ( $status ne "" ) {
        print "Rename: old page $old is invalid, error is: $status<br>\n";
        return;
    }
    $status = &ValidId($new);
    if ( $status ne "" ) {
        print "Rename: new page $new is invalid, error is: $status<br>\n";
        return;
    }
    if ( PageExists($new) ) {
        print "Rename: new page $new already exists--not renamed.<br>\n";
        return;
    }
    if ( !PageExists($old) ) {
        print "Rename: old page $old does not exist--nothing done.<br>\n";
        return;
    }
    my ( $tbname, $sth );
    if ( $dbh eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }

    # Move page rows + RC log rows (id matches the rename key directly).
    for my $tb ( &GetPageDB($old), DBTable($RcFile) ) {
        die("RenamePage: unsafe table name '$tb'") if ( !SafeIdent($tb) );
        my $s = $dbh->prepare("update $tb set id=? where id=?");
        $s->execute( $new, $old );
    }

    # Also move page_revisions rows.
    my $revdb = &GetPageDB($old) . "_revisions";
    if ( SafeIdent($revdb) ) {
        my $s = $dbh->prepare("update $revdb set page_id=? where page_id=?");
        $s->execute( $new, $old );
    }

    # Stage 6: html cache keys are `id[lang]`, not bare `id`. The old
    # `UPDATE set id=? WHERE id=?` never matched anything. Drop every
    # cached language variant for the old id; new pages will repopulate
    # the cache lazily on first read.
    my $htmldb = DBTable($HtmlDir);
    if ( SafeIdent($htmldb) ) {
        DeleteDBItems( $htmldb, "id LIKE ?", "$old\[%\]" );
    }

    $tbname = DBTable($EmailFile);
    die("RenamePage: unsafe table name '$tbname'") if ( !SafeIdent($tbname) );
    $sth = $dbh->prepare("update $tbname set page=? where page=?");
    $sth->execute( $new, $old );
    return;
}

sub DoShowVersion {
    print &GetHeader( "", "Displaying Wiki Version", "" );
    print '<div class="wikiinfo">
<h2>Habitat CMS version 0.5</h2>
$Rev::     $ Last Commit:$Date::                     $ by $Author:: fangq$
<br> based on UseModWiki version 1.0</div>';
    print &GetCommonFooter();
}

# Admin bar contributed by ElMoro (with some changes)
sub GetPageLockLink {
    my ( $id, $status, $name ) = @_;
    my $tok = GenCSRFToken();
    if ($FreeLinks) {
        $id = &FreeToNormal($id);
    }
    return &ScriptLink( "action=pagelock&set=$status&id=$id&csrf_token=$tok", $name );
}

sub GetPageWatchLink {
    my ( $id, $status, $name ) = @_;
    my $tok = GenCSRFToken();
    if ($FreeLinks) {
        $id = &FreeToNormal($id);
    }
    if ($status) {
        return &ScriptLink( "action=watch&id=$id&csrf_token=$tok", $name );
    } else {
        return &ScriptLink( "action=unwatch&id=$id&csrf_token=$tok", $name );
    }
}

sub GetLockState {
    my ($lockstate);
    $lockstate = ReadDBItems( Habitat::Store::T("system"), 'data', '', '', "id=?", 'lockstate' );
    $lockstate = 0 if ( $lockstate != 1 );

    return $lockstate;
}

sub IsPageLocked {
    my ($id) = @_;
    my ( $lockdb, $tag );
    $lockdb = DBTable($LockDir);
    $tag    = ReadDBItems( $lockdb, 'tag', '', '', "id=?", $id );
    if ( $tag =~ /L/ ) {
        return 1;
    }

    return 0;
}

sub GetAdminBar {
    my ($id) = @_;
    my ($result);

    $result =
      '<!--CACHE--><div class="wikiadminbar">' . T('Administration') . '<ul class=adminlist>';
    if ( IsPageLocked($id) ) {
        $result .= '<li>' . &GetPageLockLink( $id, 0, T('Unlock page') ) . '</li>';
    } else {
        $result .= '<li>' . &GetPageLockLink( $id, 1, T('Lock page') ) . '</li>';
    }
    $result .= '<li>' . &GetDeleteLink( $id, T('Delete this page'), 0 );
    $result .= '<li>' . &ScriptLink( "action=editbanned", T("Edit Banned List") );
    ## Maintenance is not really ready
    #$result .= '<li>'. &ScriptLink("action=maintain", T("Run Maintenance"));
    $result .= '<li>' . &ScriptLink( "action=editlinks", T("Edit/Rename pages") );
    my $tok = GenCSRFToken();
    if ( &GetLockState == 1 ) {
        $result .=
          '<li>' . &ScriptLink( "action=editlock&set=0&csrf_token=$tok", T("Unlock site") );
    } else {
        $result .= '<li>' . &ScriptLink( "action=editlock&set=1&csrf_token=$tok", T("Lock site") );
    }
    $result .= '</ul></div><!--/CACHE-->';
    return $result;
}

sub IsPageWatched {
    my ($id) = @_;
    my ( $watchdb, $tag );
    my $user = $UserData{'username'};

    if ( $UserID > 1000 ) {
        $watchdb = DBTable($EmailFile);
        $tag     = ReadDBItems( $watchdb, 'username', '', '', "page=? and username=?", $id, $user );
        if ( $tag ne '' ) {
            return 1;
        }
    }
    return 0;
}

sub GetUserBar {
    my ($id) = @_;
    my ($result);

    $result = '<div class="wikiuserbar">' . T('User toolbar') . '<ul class="userlist">';
    if ( not IsPageWatched($id) ) {
        $result .= '<li>' . &GetPageWatchLink( $id, 1, T('Watch page') ) . '</li>';
    } else {
        $result .= '<li>' . &GetPageWatchLink( $id, 0, T('Unwatch page') ) . '</li>';
    }
    $result .= '</ul></div>';
    return $result;
}

# Thanks to Phillip Riley for original code
sub DoDeletePage {
    my ($id) = @_;
    my ($rev);
    $rev = &GetParam( "revision", "" );

    if ( &ValidId($id) ne "" || !&UserIsAdmin() ) {
        print &GetHeader( '', T('No Permission ...'), '' );
        print '<div class="wikiinfo">'
          . T( "Can not delete page - no permission" . ValidId($id) )
          . "</div>";
        print &GetMinimumFooter();
        return;
    }

    if ( $ConfirmDel && !&GetParam( 'confirm', 0 ) ) {
        print &GetHeader( '', Ts( 'Confirm Delete %s', $id ), '' );
        print &GetFormStart();
        print '<div class="wikitext">';
        print Ts( 'Confirm deletion of %s by following this link:', $id );
        print "<br>"
          . T("Delete reason:")
          . $q->textfield(
            -name  => 'summary',
            -size  => 30,
            -value => '',
            -class => 'wikisearchbox'
          );
        print &GetHiddenValue( "action",  "delete" );
        print &GetHiddenValue( "id",      $id );
        print &GetHiddenValue( "confirm", 1 );
        print $q->submit(
            -name  => 'submitdelete',
            -value => T('Confirm Delete')
        );
        print '</div>';
        print $q->end_form;
        print &GetCommonFooter();
        return;
    }
    CSRFCheckOrDie();
    print &GetHeader( '', Ts( 'Delete %s', $id ), '' );
    print '<div class="wikitext">';
    if ( $id eq $HomePage ) {
        print Ts( '%s can not be deleted.', $HomePage );
    } else {
        if ( IsPageLocked($id) ) {
            print Ts( '%s can not be deleted because it is locked.', $id );
        } else {

            # Must lock because of RC-editing
            &RequestLock() or die( T('Could not get editing lock') );
            DeletePage( $id, 1, 1, $rev );
            &ReleaseLock();
            print Ts( '%s has been deleted.', $id );
        }
    }
    print '</div>';
    print &GetCommonFooter();
}

# Thanks to Ross Kowalski and Iliyan Jeliazkov for original uploading code
sub DoUpload {
    print &GetHeader( '', T('File Upload Page'), '' );
    if ( !$AllUpload ) {
        return if ( &UserPermission() < $PermUseUpload );
    }
    print '<div class="wikitext"><p>'
      . Ts( 'The current upload size limit is %s.',           $MaxPost ) . ' '
      . Ts( 'Change the %s variable to increase this limit.', '$MaxPost' );
    print '</p><br>';
    print '<form method="post" action="' . $ScriptName . '" enctype="multipart/form-data">';
    print '<input type="hidden" name="upload" value="1" />';
    my $tok = GenCSRFToken();
    print qq(<input type="hidden" name="csrf_token" value="$tok" />);
    print
'File to Upload: <input type="file" name="file"><br><br><input type="checkbox" name="dothumb" value="on" />Create thumbnail<br>';
    print '<input type="submit" name="Submit" value="Upload">';
    print '</form></div>';
    print &GetCommonFooter();
}

sub SaveUpload {
    my ( $filename, $printFilename, $uploadFilehandle );

    CSRFCheckOrDie();
    print &GetHeader( '', T('Upload Finished'), '' );
    if ( !$AllUpload ) {
        return if ( &UserPermission() < $PermUseUpload );
    }
    print '<div class="wikitext">';

    $UploadDir .= '/' if ( substr( $UploadDir, -1, 1 ) ne '/' );    # End with /
    $UploadUrl .= '/' if ( substr( $UploadUrl, -1, 1 ) ne '/' );    # End with /
    $filename = $q->param('file');
    $filename =~ s/.*[\/\\](.*)/$1/;                                # Only name after last \ or /
    $filename =~ s/[^A-Za-z0-9._-]/_/g;                             # Whitelist safe chars
    $filename =~ s/^\.+//;                                          # No leading dots (no dotfiles)
    $filename =~ s/\.+/./g;                                         # Collapse runs of dots
    if ( $filename eq '' || length($filename) > 200 ) {
        print '<p>' . &QuoteHtml( T('Invalid upload filename.') ) . '</p></div>';
        print &GetCommonFooter();
        return;
    }
    $uploadFilehandle = $q->upload('file');
    open( UPLOADFILE, '>', "$UploadDir$filename" )
      or do {
        print '<p>' . &QuoteHtml( Ts( 'Could not write upload: %s', $! ) ) . '</p></div>';
        print &GetCommonFooter();
        return;
      };
    binmode UPLOADFILE;
    while (<$uploadFilehandle>) { print UPLOADFILE; }
    close UPLOADFILE;

    print T('The wiki link to your file is:') . "\n<br><br>";
    $printFilename = $filename;
    $printFilename =~ s/ /\%20/g;    # Replace spaces with escaped spaces
    print "upload:" . $printFilename . "<br><br>\n";
    if ( $filename =~ /${ImageExtensions}$/ ) {
        print '<hr><img src="' . $UploadUrl . $filename . '">' . "\n";
        if ( $q->param('dothumb') eq 'on' ) {
            my $src = "$UploadDir$filename";
            my $dst = "$UploadDir/thumb/mini_$filename";
            my $rc  = system {'convert'} 'convert', '-sample', '200x200', $src, $dst;
            if ( $rc == 0 ) {
                print '<hr>upload:thumb/mini_'
                  . $printFilename
                  . '<hr><img src="'
                  . $UploadUrl
                  . '/thumb/mini_'
                  . $filename . '">' . "\n";
            } else {
                print '<hr>' . &QuoteHtml( T('Thumbnail generation failed.') ) . "\n";
            }
        }
    }
    print '</div>';
    print &GetCommonFooter();
}

sub UrlEncode {
    my $str = shift;
    return '' unless $str;
    $str =~ s/([^-_.*~!#=&\/A-Za-z0-9])/sprintf("%%%02X", ord($1))/seg;
    return $str;
}

sub ReadKeyFromPage {
    my ( $kid, $kstr, $kfid, $text ) = @_;
    my $val;
    my @vv;

    if ( $kfid ne "" && $kid ne "" && $kstr ne "" ) {
        @vv = split( /(<$kid>)/, $text );
        for ( my $i = 0 ; $i < @vv ; $i++ ) {
            if ( $vv[$i] =~ /$kstr/ ) {
                if ( $vv[$i] =~ /<$kfid>(.*)</ ) { $val = $1; }
                last;
            }
        }
    }
    return $val;
}

sub ReadRawWikiPage {
    my ( $id, $force ) = @_;
    my ( $status, $data, $inlinerev );
    my %localPage;
    my %localSection;
    my %localText;

    if ( !defined($force) || $force eq '' ) {
        if ( defined( $TextCache{$id} ) ) {
            return $TextCache{$id};
        } elsif ( defined( $Pages{$id}->{'text'}->{'text'} ) ) {
            return $Pages{$id}->{'text'}->{'text'};
        }
    }
    my $pagedb = &GetPageDB($id);
    my ( $sth, $maxversion, $text );

    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    die("ReadRawWikiPage: unsafe table name") if ( !SafeIdent($pagedb) );

    # New shape: page table has one row per page (PRIMARY KEY id).
    # ORDER BY revision DESC LIMIT 1 still works for legacy multi-row
    # tables that haven't been migrated yet, so the read path is
    # forward-compatible during a transition.
    $sth = $dbh->selectall_arrayref(
        "SELECT revision, text FROM $pagedb WHERE id=? ORDER BY revision DESC LIMIT 1",
        undef, $id );
    if ( defined $sth->[0] ) {
        ( $maxversion, $text ) = @{ $sth->[0] };
        if ( defined $maxversion && $maxversion ne "" ) {

            # Stage 5: new writes no longer create inline-diff chains.
            # Old data may still carry them (FS4-separated patches in
            # the text column); PatchPage detects the marker and
            # collapses the chain. On migrated data this is a no-op.
            ( $text, $inlinerev ) = &PatchPage($text)
              if ( !defined($force) || $force eq '' );
            $TextCache{$id} = $text;
            return $text;
        }
    }
    return "" if ( !defined( $BuildinPages{$id} ) || $BuildinPages{$id} eq '' );
    return $BuildinPages{$id};

}

sub ReadPagePermissions {
    my ( $id, $perm ) = @_;
    my ($pat);

    foreach $pat ( keys %$perm ) {
        if ( $id =~ m/$pat/ && $$perm{$pat} ne "" ) {
            return $$perm{$pat};
        }
    }
    return "";
}

sub ReadNameSpaceRules {
    my ($rule) = @_;
    my ( $name, $fname );
    my @ru;

    foreach $name ( keys %$rule ) {
        $fname = $$rule{$name};
        if ( -f $fname ) {

            # `||` binds tighter than `,` — the previous form
            # `open FRULE, "<$fname" || die(...)` opened the string
            # `"<$fname" || "can not read file"` which is always the
            # left operand, so the die() never fired. `or` has lower
            # precedence than `,` and gives the intended short-circuit.
            open( my $fh, '<', $fname )
              or die("ReadNameSpaceRules: cannot read $fname: $!");
            @ru = <$fh>;
            close $fh;
            $$rule{$name} = join( "", @ru );
        } else {
            $$rule{$name} = "";
        }
    }
}

sub BuildNameSpaceRules {
    &ReadNameSpaceRules( \%NameSpaceV0 );
    &ReadNameSpaceRules( \%NameSpaceV1 );
    &ReadNameSpaceRules( \%NameSpaceE0 );
    &ReadNameSpaceRules( \%NameSpaceE1 );
}

sub RemovePageCache {
    my ( $id, $lang ) = @_;
    my $htmldb = DBTable($HtmlDir);
    if ( $dbh eq "" || $htmldb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $lang = '%' if ( $lang eq '' );
    if ( $lang eq '%' ) {
        DeleteDBItems( $htmldb, "id LIKE ?", "$id\[%\]" );
    } else {
        DeleteDBItems( $htmldb, "id=?", "$id\[$lang\]" );
    }
}

sub ErrMsg {
    my ( $msg, $msgtype, $exitflag ) = @_;
    print '<div class="wikimsg">Error: ',
        T($msg)
      . "<hr/><input type='button' onclick='javascript:history.go(-1)' value='"
      . T("Go Back")
      . "'></div>";
    if ($exitflag) { exit; }
}

sub PrintMsg {
    my ( $msg, $msgtype, $exitflag ) = @_;
    print &GetHeader( '', T($msgtype), '' );
    print '<div class="wikiinfo"><span class="wikimsg">',
        T($msg)
      . "</span><hr/><input type='button' onclick='javascript:history.go(-1)' value='"
      . T("Go Back")
      . "'></div>";
    print &GetCommonFooter();
    if ($exitflag) { exit; }
}

sub JSONFormat {
    my ( $id, $text, $callback ) = @_;
    my $FSn = $FS . "n";
    my $FSr = $FS . "r";

    $text = &WikiToHTML( $id, $text );
    $text =~ s/"/\\"/g;
    $text =~ s/\n/\\n/g;
    $text =~ s/\r/\\r/g;
    return "$callback({\npage:\"$id\",\nhtml:\"$text\"\n});";
}

sub RemoteAddr {
    my $remote = $ENV{'REMOTE_ADDR'};
    my $fwd    = $ENV{'HTTP_X_REMOTE_ADDR'} || $ENV{'HTTP_X_FORWARDED_FOR'};
    return $remote unless ( $fwd && $TrustedProxies ne '' && defined($remote) );

    foreach my $tp ( split( /\s*,\s*/, $TrustedProxies ) ) {
        next if ( $tp eq '' );
        if ( $remote eq $tp || index( $remote, $tp ) == 0 ) {
            ( $fwd = $fwd ) =~ s/,.*//;          # X-Forwarded-For can be a list; take leftmost
            $fwd =~ s/^\s+|\s+$//g;
            return $fwd if ( $fwd =~ /^[0-9a-fA-F:.]+$/ );
            last;
        }
    }
    return $remote;
}

sub max {
    my ($max) = shift(@_);
    my ($temp);
    foreach $temp (@_) {
        $max = $temp if $temp > $max;
    }
    return ($max);
}

#END_OF_OTHER_CODE

# Auto-run guard. The test harness sets $_ = 'nocgi' before `require`
# to suppress this; everything else (real CGI, CGI::Compile under
# app.psgi, mod_perl) leaves $_ untouched and the call fires. `caller`
# can't be used as the sentinel — CGI::Compile wraps the script body
# in a sub so caller() is non-empty even when we *do* want to run.
&DoWikiRequest() if ( $RunCGI && ( ( $_ // '' ) ne 'nocgi' ) );

1;

# == End of UseModWiki script. ===========================================
