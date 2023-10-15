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
use Crypt::DES;
use Text::Diff;
use Text::Patch;

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
  $FooterNote $EditNote $MaxPost $NewText $NotifyDefault $HttpCharset
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
  $AMathML $AMathMLPath $MathColor $CaptchaKey $UseCaptcha $WikiCipher
  $UserBuildinCSS %BuildinPages %TextCache %Pages $UseDetailedLog
  $PageLog $UserLog $PrintedHeader $PageItemCount $ListItemCount
  $HistoryLimit $RCHistoryLimit $InlineDiffLimit);

# Note: $NotifyDefault is kept because it was a config variable in 0.90
# Other global variables:
use vars qw(%InterSite $SaveUrl $SaveNumUrl
  %KeptRevisions %UserCookie %SetCookie %UserData %IndexHash %Translate
  %LinkIndex $InterSiteInit $SaveUrlIndex $SaveNumUrlIndex $MainPage
  $OpenPageName @IndexList $IndexInit $TableMode
  $q $Now $UserID $TimeZoneOffset $ScriptName $BrowseCode $OtherCode
  $AnchoredLinkPattern @HeadingNumbers $TableOfContents $QuotedFullUrl
  $ConfigError $LangError $UploadPattern $LocalTree %Permissions
  %NameSpaceV0 %NameSpaceV1 %NameSpaceE0 %NameSpaceE1 $DiscussSuffix
  $dbh $DBName $DBUser $DBPass %DBErr %DBPrefix
  %ExtViewer %ExtEditor $UseActivation %ExportPage);

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

$PageEmbed     = 1;                                # 1 = {{page|name}} format
$MaxEmbedDepth = 5;                                # maximum depth for page embedding
$IsPrintTree   = 1;                                # print tree for subpages
$MaxTreeDepth  = 8;
$AMathML       = 0;                                # 1 = allow <amath> tags, 0 = no amath markup
$AMathMLPath   = "";
$MathColor     = "yellow";
$UseCaptcha    = 1;                                # flag to enable captcha
$CaptchaKey = pack( "H16", "0928AD813FED0277" );   # you must change this or redefine in config file
$DiscussSuffix   = '..discuss';
$DBName          = "";
$UseActivation   = 0;
$UseDetailedLog  = 0;
$PageItemCount   = 20;
$ListItemCount   = 100;
$HistoryLimit    = 50;
$RCHistoryLimit  = 100;
$InlineDiffLimit = 50;

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
$UserDir     = "$DataDir/user";                # Stores user data
$KeepDir     = "$DataDir/keep";                # Stores kept (old) page data
$TempDir     = "$DataDir/temp";                # Temporary files and locks
$LockDir     = "$TempDir/lock";                # DB is locked if this exists
$InterFile   = "$DataDir/intermap";            # Interwiki site->url map
$RcFile      = "$DataDir/rclog";               # New RecentChanges logfile
$RcOldFile   = "$DataDir/oldrclog";            # Old RecentChanges logfile
$IndexFile   = "$DataDir/pageidx";             # List of all pages
$EmailFile   = "$DataDir/watch";               # Email notification lists
$UserLog     = "$DataDir/userlog";             # Email notification lists
$PageLog     = "$DataDir/pagelog";             # Email notification lists

if ($RepInterMap) {
    push @ReplaceableFiles, $InterFile;
}

# The "main" program, called at the end of this script file.
sub DoWikiRequest {
    if ( $ENV{'SERVER_SOFTWARE'} =~ /^SimpleHTTP/ )
    {    # running a local wiki
        $DataDir = $ENV{'PWD'} . "/$DataDir" if ( $DataDir =~ /^[^\/]/ );
    }
    if ( $UseConfig && ( -f $ConfigFile ) ) {
        $ConfigError = '';
        if ( !do $ConfigFile ) {    # Some error occurred
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
        if ( $ENV{'SERVER_SOFTWARE'} =~ /^SimpleHTTP/ )
        {    # running a local wiki
            $LogoUrl    = "/$LogoUrl"    if ( $LogoUrl    =~ /^[^\/]/ );
            $StyleSheet = "/$StyleSheet" if ( $StyleSheet =~ /^[^\/]/ );
            $FavIcon    = "/$FavIcon"    if ( $FavIcon    =~ /^[^\/]/ );
        }
    }

    &InitLinkPatterns();
    &InitWikiEnv();
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

sub CleanWikiEnv {
    if ($dbh) { $dbh->disconnect(); }
}

# == Common and cache-browsing code ====================================
sub InitLinkPatterns {
    my ( $UpperLetter, $LowerLetter, $AnyLetter, $LpA, $LpB, $QDelim );

    # Field separators are used in the URL-style patterns below.
    if ($NewFS) {
        $FS = "\x1e\xff\xfe\x1e";    # An unlikely sequence for any charset
    } else {
        $FS = "\x1e";                # The FS character is a superscript "3"
    }
    $FS1 = $FS . "1";                # The FS values are used to separate fields
    $FS2 = $FS . "2";                # in stored hashtables and other data structures.
    $FS3 = $FS . "3";                # The FS character is not allowed in user data.
    $FS4 = $FS . "4";                # The FS character is not allowed in user data.
    $FS5 = $FS . "5";                # The FS character is not allowed in user data.

    $Now = time;                     # Reset in case script is persistent

    $UpperLetter = "[A-Z";
    $LowerLetter = "[a-z";
    $AnyLetter   = "[A-Za-z";
    if ($NonEnglish) {
        $UpperLetter .= "\xc0-\xde";
        $LowerLetter .= "\xdf-\xff";
        if ($NewFS) {
            $AnyLetter .= "\x80-\xff";
        } else {
            $AnyLetter .= "\xc0-\xff";
        }
    }
    if ( !$SimpleLinks ) {
        $AnyLetter .= "_0-9";
    }
    $UpperLetter .= "]";
    $LowerLetter .= "]";
    $AnyLetter   .= "]";

    #  $WikiWord = '[A-Z]+[a-z\x80-\xff]+[A-Z][A-Za-z\x80-\xff]*';

    # Main link pattern: lowercase between uppercase, then anything
    $LpA = $UpperLetter . "+" . $LowerLetter . "+" . $UpperLetter . $AnyLetter . "*";

    # Optional subpage link pattern: uppercase, lowercase, then anything
    $LpB = $UpperLetter . "+" . $LowerLetter . "+" . $AnyLetter . "*";
    if ($UseSubpage) {

        # Loose pattern: If subpage is used, subpage may be simple name
        $LinkPattern = "((?:(?:$LpA)?\\/$LpB)|$LpA)";

 # Strict pattern: both sides must be the main LinkPattern $LinkPattern = "((?:(?:$LpA)?\\/)?$LpA)";
    } else {
        $LinkPattern = "($LpA)";
    }
    $QDelim              = '(?:"")?';    # Optional quote delimiter (not in output)
    $AnchoredLinkPattern = $LinkPattern . '#(\\w+)' . $QDelim if $NamedAnchors;
    $LinkPattern .= $QDelim;

# Inter-site convention: sites must start with uppercase letter (Uppercase letter avoids confusion with URLs)
    $InterSitePattern = $UpperLetter . $AnyLetter . "+";
    $InterLinkPattern = "((?:$InterSitePattern:[^\\]\\s\"<>$FS]+)$QDelim)";
    if ($FreeLinks) {

        # Note: the - character must be first in $AnyLetter definition
        if ($NonEnglish) {

            #      if ($NewFS) {
            $AnyLetter = "[-,.()' _0-9A-Za-z\x80-\xff]";

            #      } else {
            #        $AnyLetter = "[-,.()' _0-9A-Za-z\xc0-\xff]";
            #      }
        } else {
            $AnyLetter = "[-,.()' _0-9A-Za-z]";
        }
    }
    $FreeLinkPattern = "($AnyLetter+)";

    if ($UseSubpage) {
        my $AnyLetterSub = "[-,.()' _0-9A-Za-z\/\x80-\xff]";
        $FreeLinkPattern = "((?:(?:$AnyLetterSub+)?\\/)?$AnyLetter+)";
    }
    $FreeLinkPattern .= $QDelim;

    # Url-style links are delimited by one of:
    #   1.  Whitespace                           (kept in output)
    #   2.  Left or right angle-bracket (< or >) (kept in output)
    #   3.  Right square-bracket (])             (kept in output)
    #   4.  A single double-quote (")            (kept in output)
    #   5.  A $FS (field separator) character    (kept in output)
    #   6.  A double double-quote ("")           (removed from output)
    $UrlProtocols = "http|https|ftp|afs|news|nntp|mid|cid|mailto|wais|" . "prospero|telnet|gopher";
    $UrlProtocols .= '|file' if ( $NetworkFile || !$LimitFileUrl );
    $UrlPattern      = "((?:(?:$UrlProtocols):[^\\]\\s\"<>$FS]+)$QDelim)";
    $ImageExtensions = "(gif|jpg|png|bmp|jpeg)";
    $RFCPattern      = "RFC\\s?(\\d+)";
    $ISBNPattern     = "ISBN:?([0-9- xX]{10,})";
    $UploadPattern   = "upload:([^\\]\\s\"<>$FS]+)$QDelim";
}

sub InitWikiEnv {
    if ( $DBName ne '' ) {
        $dbh = DBI->connect( $DBName, $DBUser, $DBPass, \%DBErr ) or die($DBI::errstr);
        $dbh->func(
            'regexp', 2,
            sub {
                my ( $regex, $string ) = @_;
                return $string =~ /$regex/;
            },
            'create_function'
        );
    } else {
        $ConfigError .= "database $DBName does not exist";
    }
    %Pages      = ( 'page' => (), 'text' => (), 'section' => (), 'embed' => () );
    $WikiCipher = new Crypt::DES($CaptchaKey) if $UseCaptcha;
}

# get parameters before reading cookies
sub InitParam {
    my ( $buffer, @pairs, %param, $value, $name, $pair );
    if ( length( $ENV{'QUERY_STRING'} ) > 0 ) {
        $buffer = $ENV{'QUERY_STRING'};
        @pairs  = split( /&/, $buffer );
        foreach $pair (@pairs) {
            ( $name, $value ) = split( /=/, $pair );
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
    $query = $ENV{'QUERY_STRING'};
    %param = &InitParam();

    if ( ( $query eq "" ) && ( $ENV{'REQUEST_METHOD'} eq "GET" ) ) {
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
    my $htmldb    = ( split( /\//, $HtmlDir ) )[-1];
    my $pagelogdb = ( split( /\//, $PageLog ) )[-1];

    if ( $dbh eq "" || $htmldb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $text = ReadDBItems( $htmldb, 'text', '', '', "id='$query\[$language\]'" );
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
    my @ScriptPath = split( '/', "$ENV{SCRIPT_NAME}" );

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
    $ScriptName = pop(@ScriptPath);    # Name used in links
    $IndexInit  = 0;                   # Must be reset for each request
    if ( !defined($InterSiteInit) ) {
        $InterSiteInit = 0;
        %InterSite     = ();
    }
    $MainPage     = ".";                     # For subpages only, the name of the top-level page
    $OpenPageName = "";                      # Currently open page
    $FullUrl      = $q->url( -full => 1 );

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
    undef $q->{'.cookies'};                    # Clear cache if it exists (for SpeedyCGI)
    %UserData   = ();                          # Fix for persistent environments.
    %UserCookie = $q->cookie($CookieName);
    $UserID     = $UserCookie{'id'};
    $UserID     = 0 if ( !defined $UserID );
    $UserID =~ s/\D//g;                        # Numeric only

    if ( $UserID < 200 ) {
        $UserID = 111;
    } else {
        &LoadUserDataDB($UserID);
    }
    if ( $UserID > 199 ) {
        if (   ( $UserData{'id'} != $UserCookie{'id'} )
            || ( $UserData{'randkey'} != $UserCookie{'randkey'} ) )
        {
            $UserID   = 113;
            %UserData = ();    # Invalid.  Consider warning message.
        }
    }

    if ( $UserData{'tzoffset'} != 0 ) {
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

sub GetPageDB {
    my ($id) = @_;
    my $pref = ReadPagePermissions( $id, \%DBPrefix );
    if ( $pref ne "" ) {
        return $pref;
    } else {
        return ( split( /\//, $PageDir ) )[-1];
    }
}

sub PageExists {
    my ($id) = @_;
    return 1 if ( defined $BuildinPages{$id} );
    my $pagedb = &GetPageDB($id);
    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    my $data = ReadDBItems( $pagedb, 'id', '', '', "id='$id'" );
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

    $id = &GetParam( 'keywords', '' );
    if ($id) {             # Just script?PageName
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
    $action = lc( &GetParam( 'action', '' ) );

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
    my %pgprop = ();

    if ( $id =~ /\/\.[^\/]+$/ ) { return; }

    if ( defined( $Pages{$id}->{'rules'} ) ) {
        return;
    }
    $toptree = &GetPageDirectory($id);
    @dirs    = ( split( /\//, $toptree . "/" . $id ) );
    if ( @dirs < 1 ) { return; }

    $levelcount = ( $toptree =~ tr/\/// ) + 1;

    %{ $Pages{$id} } = ( 'preview' => (), 'postview' => (), 'preedit' => (), 'postedit' => () );
    $Pages{$id}->{'rules'} = 1;

    for ( $i = $levelcount ; $i < @dirs ; $i++ ) {
        $dirname = "";
        for ( $j = $levelcount ; $j <= $i ; $j++ ) {
            if   ( $j == $levelcount ) { $dirname .= $dirs[$j]; }
            else                       { $dirname .= "/" . $dirs[$j]; }
        }
        foreach $ff ( keys %rulefiles ) {
            $fname = $dirname . "/.$ff";
            $rules = &ReadRawWikiPage($fname);
            if ( $rules ne "" ) {
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
    my $pagelogdb = ( split( /\//, $PageLog ) )[-1];

    $extviewer = ReadPagePermissions( $id, \%ExtViewer );
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

    $openKept = 0;
    $revision = &GetParam( 'revision', '' );
    if ( $revision =~ /(\d+)\.(\d+)/ ) {
        $revision  = $1;
        $inlinerev = $2;
    }
    $fullrev = ( $inlinerev eq '' ? $revision : "$revision.$inlinerev" );
    $revision =~ s/\D//g;         # Remove non-numeric chars
    $goodRevision = $revision;    # Non-blank only if exists
    if ( $revision ne '' ) {
        &OpenKeptRevisions( $id, 'text_default', $inlinerev >= 0 );
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
    if ( defined $$Text{'isnew'} && $BuildinPages{$id} ne '' ) {
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
    &UpdateHtmlCacheDB( $id, $fullHtml ) if ( $UseCache && ( $oldId eq '' ) );
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

    $offset = GetParam( 'offset', 1e10 );

    $rclogdb = ( split( /\//, $RcFile ) )[-1];
    if ( $dbh eq "" || $rclogdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    if ( $offset > 0 ) {
        $searchcmd =
"select * from $rclogdb where time>$stime and time<$offset order by time desc limit 0,$lim";
    } else {
        $searchcmd = "select * from $rclogdb where time>$stime order by time desc limit 0,$lim";
    }
    $sth     = $dbh->selectall_arrayref($searchcmd);
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
                $extra{'id'}       = $uid;
                $extra{'revision'} = $rev;
                $extra{'name'}     = $name;
                $extra{'admin'}    = $admin;
                push( @fullrc,
                    "$ts$FS3$pagename$FS3$summary$FS3$isEdit$FS3$host$FS3$kind$FS3"
                      . join( $FS2, %extra ) );
                $mintime = $ts if ( $ts < $mintime );
            }
        }
    }
    if ( $mintime > 0 ) {
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
    if ( @fullrc > 0 && $fullrc[0] =~ /^Internal:Offset:([0-9]+)([+]*)/ ) {
        $offs       = $1;
        $moretocome = $2;
        shift(@fullrc);
    }
    $lastTs = 0;
    if ( @fullrc > 0 ) {    # Only false if no lines in file
        ($lastTs) = split( /$FS3/, $fullrc[$#fullrc] );
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

    # Slice minor edits
    $showedit = &GetParam( "rcshowedit", $ShowEdits );
    $showedit = &GetParam( "showedit",   $showedit );
    if ( $showedit != 1 ) {
        my @temprc = ();
        foreach $rcline (@outrc) {
            ( $ts, $pagename, $summary, $isEdit, $host ) = split( /$FS3/, $rcline );
            if ( $showedit == 0 ) {    # 0 = No edits
                push( @temprc, $rcline ) if ( $isEdit != 1 );
            } else {                   # 2 = Only edits
                push( @temprc, $rcline ) if ($isEdit);
            }
        }
        @outrc = @temprc;
    }

    # Optimize param fetches out of main loop
    $rcchangehist = &GetParam( "rcchangehist", 1 );

    # Optimize translations out of main loop
    $tEdit         = T('(edit)');
    $tDiff         = T('(diff)');
    $tChanges      = T('changes');
    $diffPrefix    = $QuotedFullUrl . &QuoteHtml("?action=browse\&diff=4\&id=");
    $historyPrefix = $QuotedFullUrl . &QuoteHtml("?action=history\&id=");
    foreach $rcline (@outrc) {
        ( $ts, $pagename ) = split( /$FS3/, $rcline );
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
        ( $ts, $pagename, $summary, $isEdit, $host, $kind, $extraTemp ) = split( /$FS3/, $rcline );
        next if ( ( !$all )         && ( $ts < $changetime{$pagename} ) );
        next if ( ( $idOnly ne "" ) && ( $idOnly ne $pagename ) );
        %extra = split( /$FS2/, $extraTemp, -1 );
        next if ( $extra{'admin'} && ( &UserPermission() < $extra{'admin'} ) );
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
    $FullUrl         = $q->url( -full => 1 ) if ( $FullUrl eq "" );
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

    %sect      = split( /$FS2/, $section, -1 );
    %revtext   = split( /$FS3/, $sect{'data'} );
    @textpatch = split( /$FS4/, $revtext{'text'} );

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
    if ( $hint ne '' ) {
        $hint = "title='$hint'";
    }
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
    $style = 'wikipagelink' if ( $style eq '' );
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
    $style = 'wikipageedit' if ( $style eq '' );
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
        $cookie =
            "$CookieName=" . "rev&"
          . $SetCookie{'rev'} . "&id&"
          . $SetCookie{'id'}
          . "&randkey&"
          . $SetCookie{'randkey'}
          . "&lang&"
          . $SetCookie{'lang'};
        $cookie .= ";expires=" . gmtime( time() + 60 * 24 * 3600 ) . " GMT";
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
    $dtd   = '-//W3C//DTD XHTML 1.0 Transitional//EN';
    $html  = qq(<!DOCTYPE HTML PUBLIC "$dtd">\n);
    $title = $q->escapeHTML($title);
    $html .= "<html><head><title>$title</title>\n";
    $html .= "<meta http-equiv=\"content-type\" content=\"text/html; charset=$HttpCharset\"/>";
    if ( $nocache ne '' ) {
        $html .= "<meta http-equiv=\"cache-control\" content=\"$nocache\"/>";
    }
    if ( $FavIcon ne '' ) {
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
      . $ENV{SERVER_NAME}
      . $ENV{SCRIPT_NAME}
      . &ScriptLinkChar()
      . 'action=rss"/>';

    if ( $SiteBase ne "" ) {
        $html .= qq(<base href="$SiteBase">\n);
    }
    $stylesheet = &GetParam( 'stylesheet', $StyleSheet );
    $stylesheet = $StyleSheet if ( $stylesheet eq '' );
    $stylesheet = ''          if ( $stylesheet eq '*' );    # Allow removing override
    $printcss   = $stylesheet;
    $printcss =~ s/\.[Cc][Ss][Ss]$/_print.css/;
    $fontcss = $stylesheet;
    $fontcss =~ s/\.[Cc][Ss][Ss]$/_webfont.css/;

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
    if ( $$Section{'revision'} > 0 ) {
        $result .= '<div class="wikipginfo">';
        if ( $rev eq '' ) {    # Only for most current rev
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
    return $q->start_form( "POST", "$ScriptName", "application/x-www-form-urlencoded" );
}

sub GetGotoBar {
    my ($id) = @_;
    my ( $main, $bartext );

    $bartext = '<ul class="wikiheaderlist"><li>';
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
    if ( $UserData{'username'} eq '' ) {
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

sub GetRedirectPage {
    my ( $newid, $name, $isEdit ) = @_;
    my ( $url, $html );
    my ($nameLink);

    if ( $newid =~ /^http[s:]+\/\// ) {
        $url = $newid;
    } else {

        # Normally get URL from script, but allow override.
        $FullUrl = $q->url( -full => 1 ) if ( $FullUrl eq "" );
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
                $html .=
                    "Set-Cookie: $CookieName=" . "rev&"
                  . $SetCookie{'rev'} . "&id&"
                  . $SetCookie{'id'}
                  . "&randkey&"
                  . $SetCookie{'randkey'}
                  . "&lang&"
                  . $SetCookie{'lang'} . "\n";
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
sub RestoreSavedText {
    my ($text) = @_;

    1 while $text =~ s/$FS(\d+)$FS/$$SaveUrl{$1}/ge;    # Restore saved text
    return $text;
}

sub RemoveFS {
    my ($text) = @_;

    # Note: must remove all $FS, and $FS may be multi-byte/char separator
    $text =~ s/($FS)+(\d)/$2/g;
    return $text;
}

sub ApplyRegExp {
    my ( $id, $pageText, $namespace, $pagepath ) = @_;
    my ($name);

    if ( $id =~ /\/\.[^\/]+$/ ) { return $pageText; }

    $id =~ s/(.*)\/__([A-Z0-9]+)__$/"$1\/".GetDynaPageName($1,$2)/geo;

    foreach $name ( keys %$namespace ) {
        if ( $$namespace{$name} ne "" ) {
            if ( $id =~ m/$name/ ) {
                $pageText = &ApplyRegExpRules( $$namespace{$name}, $pageText, 0 );
                last
                  ; # find the first rule match the name pattern, apply the rules, then skip the rest
            }
        }
    }
    if (@$pagepath) {
        $pageText = &ApplyRegExpRules( join( '', @$pagepath ), $pageText, 0 );
    }
    return $pageText;
}

sub getnextnum {
    my ($id) = @_;
    $id =~ s/\/$//g;
    my @matchitem = split( /\n/,
        ReadDBItems( GetPageDB($id), 'id', "\n", '', "id REGEXP \"^$id\/[0-9]+\" group by id" ) );
    for ( my $i = 0 ; $i < @matchitem ; $i++ ) {
        $matchitem[$i] =~ s/^$id\///;
    }
    return sprintf( "%04d", ( sort(@matchitem) )[-1] + 1 ) if ( @matchitem >= 0 );
}

sub WikiToHTML {
    my ( $id, $pageText ) = @_;
    my ( $toptree, $topnode, $datestr, $timestr, $pagename, $name, $truepage, $Section );
    $TableMode = 0;

    $Section = \%{ $Pages{$id}->{'section'} };

    &RestorePageHash($id);
    &BuildRuleStack($id);    # added 05/13/06 by fangq
    my $pp = ReadPagePermissions( $id, \%Permissions );
    if ( ( defined( $Pages{$id}->{'clearance'} ) && &UserPermission() < $Pages{$id}->{'clearance'} )
        || ( ( $pp ne '' ) && &UserPermission() < $pp ) )
    {
        $UseCache = 0;
        return "";
    }
    %$SaveUrl         = ();
    %$SaveNumUrl      = ();
    $$SaveUrlIndex    = 0;
    $$SaveNumUrlIndex = 0;

    $pageText = &RemoveFS($pageText);

    #  if($id=~ /\//) { $pageText .= "<localtree>";}

    $pageText =~ s/<nowiki>((.|\n)*?)<\/nowiki>/&StoreRaw($1)/ige;
    $pageText =~ s/\&lt;nowiki\&gt;((.|\n)*?)\&lt;\/nowiki\&gt;/&StoreRaw($1)/ige;
    if ( $PageEmbed == 1 ) {    # added by FangQ, 2006/4/16
        $pageText =~
s/\{\(($FreeLinkPattern)(::($FreeLinkPattern)){0,1}(\|(.*)){0,1}\)\}/&EmbedWikiPageRaw($1,$5,$7)/geo;
    }
    $pageText = &ApplyRegExp( $id, $pageText, \%NameSpaceV0, $Pages{$id}->{'preview'} );
    if ( $id =~ /(.*)$DiscussSuffix$/ ) {
        $truepage = $1;
        $pageText =~ s/&lt;origpagename&gt;/$truepage/gi;
    }
    $pageText =~ s/&lt;fullpagename&gt;/$id/gi;
    $pageText =~ s/&lt;userip&gt;/$ENV{'REMOTE_ADDR'}/gi;

    $pagename = ( split( /\//, $id ) )[-1];
    $pageText =~ s/&lt;pagename&gt;/$pagename/gi;

    $datestr = &CalcDayNum( $$Section{'tscreate'} );
    $timestr = &CalcTime( $$Section{'tscreate'} );

    $pageText =~ s/&lt;date&gt;/$datestr/gi;
    $pageText =~ s/&lt;time&gt;/$timestr/gi;

    $datestr = &CalcDayNum($Now);
    $timestr = &CalcTime($Now);

    $pageText =~ s/&lt;datenow&gt;/$datestr/gi;
    $pageText =~ s/&lt;timenow&gt;/$timestr/gi;

    if ($RawHtml) {
        $pageText =~ s/<html>((.|\n)*?)<\/html>/&StoreRaw($1)/ige;
    }
    $pageText = &QuoteHtml($pageText);
    $pageText =~ s/\\ *\r?\n/ /g;    # Join lines with backslash at end
    if ($ParseParas) {

        # Note: The following 3 rules may span paragraphs, so they are
        #       copied from CommonMarkup
        $pageText =~ s/\&lt;pre\&gt;((.|\n)*?)\&lt;\/pre\&gt;/&StorePre($1, "pre")/ige;
        $pageText =~ s/\&lt;code\&gt;((.|\n)*?)\&lt;\/code\&gt;/&StorePre($1, "code")/ige;
        $pageText =~ s/((.|\n)+?\n)\s*\n/&ParseParagraph($1)/geo;
        $pageText =~ s/(.*)<\/p>(.+)$/$1.&ParseParagraph($2)/seo;
    } else {
        $pageText = &CommonMarkup( $pageText, 1, 0 );    # Multi-line markup
        $pageText = &WikiLinesToHtml($pageText);         # Line-oriented markup
    }
    while (@HeadingNumbers) {
        pop @HeadingNumbers;
        $TableOfContents .= "</dd></dl>\n\n";
    }
    $TableOfContents = "" if ( !defined $TableOfContents );
    $pageText =~ s/&lt;toc&gt;/$TableOfContents/gi;
    $pageText =~ s/&lt;localtree&gt;/&GetLocalTree($id)/geo;
    $pageText =~
      s/&lt;listxml\s+name=['"](.*)['"]\s+format=['"](.*)['"]&gt;/&GetLocalTree($id,$1,$2)/geo;
    if ( $LateRules ne '' ) {
        $pageText = &EvalLocalRules( $LateRules, $pageText, 0 );
    }

    if ( $PageEmbed == 1 ) {    # added by FangQ, 2006/4/16
        $pageText =~
s/\{\{($FreeLinkPattern)::(\w+),(\w+)=(\w+)\}\}/&ReadKeyFromPage($4,$5,$3,&ReadRawWikiPage($2))."::$2#$5"/geo;
        $pageText =~
s/\{\{($FreeLinkPattern)(::($FreeLinkPattern)){0,1}(\|(.*)){0,1}\}\}/&EmbedWikiPage($1,$5,$7)/geo;
        $pageText =~ s/\{\{($FreeLinkPattern)\s*\{([^\}]+)\}\}\}/&EmbedWikiPage($1,'','',$3)/geo;
    }
    &RestorePageHash($id);
    $pageText = &RestoreSavedText($pageText);
    $pageText = &ApplyRegExp( $id, $pageText, \%NameSpaceV1, $Pages{$id}->{'postview'} );

    return $pageText;
}

sub GetLocalTree {
    my ( $id, $namepat, $format ) = @_;
    my ( $toptree, $topnode );
    if ( !( defined $LocalTree ) && $IsPrintTree ) {
        my @matchitem = split(
            /\n/,
            ReadDBItems(
                GetPageDB($id), 'id', "\n", '', "id REGEXP \"$id\/$namepat\" group by id"
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
    my $pagehash;

    #   $pagehash=crypt($id,unpack("H16",$CaptchaKey));
    #   $pagehash=~ s/\./_/;
    #   $pagehash=substr($pagehash,0,10);
    #   $pagehash=~ s/\s//;
    $pagehash = $id;

    $SaveUrl         = "SaveUrl$pagehash";
    $SaveNumUrl      = "SaveNumUrl$pagehash";
    $SaveUrlIndex    = "SaveUrlIndex$pagehash";
    $SaveNumUrlIndex = "SaveNumUrlIndex$pagehash";
}

# added by FangQ, 2006/4/16

sub EmbedWikiPage {
    my ( $id, $uri, $name, $text ) = @_;
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
                $res = &WikiToHTML( $id, ReadRawWikiPage($id) );
            } else {
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
            $res = &GetVariable( &ReadRawWikiPage($id) );
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

sub CommonMarkup {
    my ( $text, $useImage, $doLines ) = @_;
    local $_ = $text;

    if ( $doLines < 2 ) {    # 2 = do line-oriented only
                             # The <nowiki> tag stores text with no markup (except quoting HTML)
        s/\&lt;nowiki\&gt;((.|\n)*?)\&lt;\/nowiki\&gt;/&StoreRaw($1)/ige;

        # The <pre> tag wraps the stored text with the HTML <pre> tag
        s/\&lt;pre\&gt;((.|\n)*?)\&lt;\/pre\&gt;/&StorePre($1, "pre")/ige;
        s/\&lt;code\&gt;((.|\n)*?)\&lt;\/code\&gt;/&StorePre($1, "code")/ige;
        s/\&lt;amathml\&gt;/<script type="text\/javascript" 
src="$AMathMLPath"><\/script><script>mathcolor="$MathColor"<\/script>/g if $AMathML;

        # remove variable definitions added by FangQ, 2006/4/16
        s/\{\{\{$FreeLinkPattern\}((.|\n)*?)\}\}/$2/g;

        if ( $EarlyRules ne '' ) {
            $_ = &EvalLocalRules( $EarlyRules, $_, !$useImage );
        }
        s/\[\#(\w+)\]/&StoreHref(" name=\"$1\"")/ge if $NamedAnchors;
        if ($HtmlTags) {
            my ($t);
            foreach $t (@HtmlPairs) {
                s/\&lt;$t(\s[^<>]+?)?\&gt;(.*?)\&lt;\/$t\&gt;/<$t$1>$2<\/$t>/gis;
            }
            foreach $t (@HtmlSingle) {
                s/\&lt;$t(\s[^<>]+?)?\&gt;/<$t$1>/gi;
            }
        } else {

            # Note that these tags are restricted to a single line
            s/\&lt;b\&gt;(.*?)\&lt;\/b\&gt;/<b>$1<\/b>/gi;
            s/\&lt;i\&gt;(.*?)\&lt;\/i\&gt;/<i>$1<\/i>/gi;
            s/\&lt;strong\&gt;(.*?)\&lt;\/strong\&gt;/<strong>$1<\/strong>/gi;
            s/\&lt;em\&gt;(.*?)\&lt;\/em\&gt;/<em>$1<\/em>/gi;
        }
        s/\&lt;tt\&gt;(.*?)\&lt;\/tt\&gt;/<tt>$1<\/tt>/gis;    # <tt> (MeatBall)
        s/\&lt;br\&gt;/<br>/gi;                                # Allow simple line break anywhere
        if ($HtmlLinks) {
            s/\&lt;A(\s[^<>]+?)\&gt;(.*?)\&lt;\/a\&gt;/&StoreHref($1, $2)/gise;
        }
        if ($FreeLinks) {

# Consider: should local free-link descriptions be conditional? Also, consider that one could write [[Bad
# Page|Good Page]]?
            s/\[\[$FreeLinkPattern\|([^\]]+)\]\]/&StorePageOrEditLink($1, $2)/geo;
            s/\[\[$FreeLinkPattern\]\]/&StorePageOrEditLink($1, "")/geo;

            s/\[\[$FreeLinkPattern#$FreeLinkPattern\]\]/&StoreRaw(&GetPageOrEditAnchoredLink($1,
                             $2, ""))/geo if $NamedAnchors;
        }
        if ($BracketText) {    # Links like [URL text of link]
            s/\[$UrlPattern\s+([^\]]+?)\]/&StoreBracketUrl($1, $2, $useImage)/geos;
            s/\[$InterLinkPattern\s+([^\]]+?)\]/&StoreBracketInterPage($1, $2,
                                                             $useImage)/geos;
            if ( $WikiLinks && $BracketWiki ) {    # Local bracket-links
                s/\[$LinkPattern\s+([^\]]+?)\]/&StoreBracketLink($1, $2)/geos;
                s/\[$AnchoredLinkPattern\s+([^\]]+?)\]/&StoreBracketAnchoredLink($1,
                                               $2, $3)/geos if $NamedAnchors;
            }
        }
        s/\[$UrlPattern\]/&StoreBracketUrl($1, "", 0)/geo;
        s/\[$InterLinkPattern\]/&StoreBracketInterPage($1, "", 0)/geo;
        s/\b$UrlPattern/&StoreUrl($1, $useImage)/geo;
        s/\b$InterLinkPattern/&StoreInterPage($1, $useImage)/geo;
        if ($PermUseUpload) {
            s/$UploadPattern/&StoreUpload($1)/geo;
        }

        if ($WikiLinks) {
            s/$AnchoredLinkPattern/&StoreRaw(&GetPageOrEditAnchoredLink($1,
                             $2, ""))/geo if $NamedAnchors;

            # CAA: Putting \b in front of $LinkPattern breaks /SubPage links
            #      (subpage links without the main page)
            s/$LinkPattern/&GetPageOrEditLink($1, "")/geo;
        }
        s/\b$RFCPattern/&StoreRFC($1)/geo;
        s/\b$ISBNPattern/&StoreISBN($1)/geo;
        if ($ThinLine) {
            if ($OldThinLine) {    # Backwards compatible, conflicts with headers
                s/====+/<hr noshade class="wikiline" size=2>/g;
            } else {               # New behavior--no conflict
                s/------+/<hr noshade class="wikiline" size=2>/g;
            }
            s/----+/<hr noshade class="wikiline" size=1>/g;
        } else {
            s/----+/<hr class="wikiline">/g;
        }
    }
    if ($doLines) {    # 0 = no line-oriented, 1 or 2 = do line-oriented
         # The quote markup patterns avoid overlapping tags (with 5 quotes) by matching the inner quotes for the strong
         # pattern.
        s/('*)'''(.*?)'''/$1<strong>$2<\/strong>/g;
        s/''(.*?)''/<em>$1<\/em>/g;
        s/`(.*?)`/<code>$1<\/code>/g;
        if ($UseHeadings) {

            #      s/(^|\n)\s*(\=+)\s+([^\n]+)\s+\=+/&WikiHeading($1, $2, $3)/geo;
            s/(^|\n)\s*(\=+)\s+(.+)\s+\=+/&WikiHeading($1, $2, $3)/geo;
        }
        if ($TableMode) {
            if (m/\|\|_+/) {
s/((\|\|)+)(\_*)/"<\/td><td". (length($1)>2 ? (" colspan='" . (length($1)\/2) . "'") : "") . (length($3)<=1 ? "" : " rowspan='".
                (length($3)). "'") . ">"/ge;
            } else {
s/((\|\|)+)/"<\/td><td". (length($1)>2 ? (" colspan='" . (length($1)\/2) . "'") : "") .">"/ge;
            }

            if (m/\!\!_+/) {
s/((\!\!)+)(\_*)/"<\/th><th". (length($1)>2 ? (" colspan='" . (length($1)\/2) . "'") : "") . (length($3)<=1 ? "" : " rowspan='".
                (length($3)). "'") . ">"/ge;
            } else {
s/((\!\!)+)/"<\/th><th". (length($1)>2 ? (" colspan='" . (length($1)\/2) . "'") : "") . ">"/ge;
            }
        }
    }
    return $_;
}

sub WikiLinesToHtml {
    my ($pageText) = @_;
    my ( $pageHtml, @htmlStack, $code, $codeAttributes, $depth, $oldCode );

    @htmlStack = ();
    $depth     = 0;
    $pageHtml  = "";
    foreach ( split( /\n/, $pageText ) ) {    # Process lines one-at-a-time
        $code           = '';
        $codeAttributes = '';
        $TableMode      = 0;
        $_ .= "\n";
        if (s/^(\;+)([^:]+\:?)\:/<dt>$2<dd>/) {
            $code           = "dl";
            $depth          = length $1;
            $codeAttributes = "class='wikiddllevel$depth'";
        } elsif (s/^(\:+)/<dt><dd>/) {
            $code           = "dl";
            $depth          = length $1;
            $codeAttributes = "class='wikidllevel$depth'";
        } elsif (s/^(\*+)/<li>/) {
            $code           = "ul";
            $depth          = length $1;
            $codeAttributes = "class='wikiullevel$depth'";
        } elsif (s/^(\#+)/<li>/) {
            $code           = "ol";
            $depth          = length $1;
            $codeAttributes = "class='wikiollevel$depth'";
        } elsif (
            $TableSyntax
            && s/^((\|\|)+)(\_+)(.*)\|\|\s*$/"<tr>"
                       . "<td". (length($1)>2 ? (" colspan='"
                       . (length($1)\/2) . "'") : "") . (length($3)<=1 ? "" : (" rowspan='".length($3))."'" ).">$4<\/td><\/tr>\n"/e
          )
        {
            $code           = 'table';
            $codeAttributes = "class='wikitable'";
            $TableMode      = 1;
            $depth          = 1;
        } elsif (
            $TableSyntax
            && s/^((\|\|)+)(.*)\|\|\s*$/"<tr>"
                   . "<td". (length($1)>2 ? (" colspan='"
                   . (length($1)\/2) ."'") : "") . ">$3<\/td><\/tr>\n"/e
          )
        {
            $code           = 'table';
            $codeAttributes = "class='wikitable'";
            $TableMode      = 1;
            $depth          = 1;
        } elsif (
            $TableSyntax
            && s/^((\!\!)+)(\_+)(.*)\!\!\s*$/"<tr>"
                       . "<th". (length($1)>2 ? (" colspan='"
                       . (length($1)\/2) . "'") : "") . (length($3)<=1 ? "" :" rowspan='".length($3)."'").">$4<\/th><\/tr>\n"/e
          )
        {
            $code           = 'table';
            $codeAttributes = "border='1'";
            $TableMode      = 1;
            $depth          = 1;
        } elsif (
            $TableSyntax
            && s/^((\!\!)+)(.*)\!\!\s*$/"<tr>"
                   . "<th". (length($1)>2 ? (" colspan='"
                   . (length($1)\/2)."'") : "") . ">$3<\/th><\/tr>\n"/e
          )
        {
            $code           = 'table';
            $codeAttributes = "class='wikitable'";
            $TableMode      = 1;
            $depth          = 1;
        } elsif (/^[ \t].*\S/) {
            $code  = "pre";
            $depth = 1;
        } else {
            $depth = 0;
        }
        while ( @htmlStack > $depth ) {    # Close tags as needed
            $pageHtml .= "</" . pop(@htmlStack) . ">\n";
        }
        if ( $depth > 0 ) {
            $depth = $IndentLimit if ( $depth > $IndentLimit );
            if (@htmlStack) {              # Non-empty stack
                $oldCode = pop(@htmlStack);
                if ( $oldCode ne $code ) {
                    $pageHtml .= "</$oldCode><$code>\n";
                }
                push( @htmlStack, $code );
            }
            while ( @htmlStack < $depth ) {
                push( @htmlStack, $code );
                $pageHtml .= "<$code $codeAttributes>\n";
            }
        }
        if ( !$ParseParas ) {
            s/^\s*$/<p>\n/;    # Blank lines become <p> tags
        }
        $pageHtml .= &CommonMarkup( $_, 1, 2 );    # Line-oriented common markup
    }
    while ( @htmlStack > 0 ) {                     # Clear stack
        $pageHtml .= "</" . pop(@htmlStack) . ">\n";
    }
    return $pageHtml;
}

sub ApplyRegExpRules {
    my ( $rules, $origText, $isDiff ) = @_;
    my ( $text, $reportError, $line, $from, $to, $opt, $FSA );
    my @rulelist;
    my @newtext;

    $FSA = $FS . "A";
    $rules =~ s/\\\s*\r*\n/$FSA/g;    # remove line continuation sign
    @rulelist = split( /\n/, $rules );
    $text     = $origText;

    foreach $line (@rulelist) {
        $line =~ s/[\r\n]$//;

        #       $line =~ s/^#.*$//g;
        #       $line =~ s/([^\\])#.*$/$1/g; # remove comments
        if ( $line eq "" ) { next; }

        if ( $line =~ /^GREP\s+(.*)/ ) {
            @newtext = grep( /$1/, split( /\r*\n/, $text ) );
            $text    = join( "\n", @newtext );
            next;
        }
        if ( $line =~ /^HEAD\s+(.*)/ ) {
            @newtext = split( /\r*\n/, $text );
            if ( $1 <= $#newtext ) {
                delete @newtext[ $1 .. $#newtext ];
            }
            $text = join( "\n", @newtext );
            next;
        }
        if ( $line =~ /^TAIL\s+(.*)/ ) {
            @newtext = split( /\r*\n/, $text );
            if ( $#newtext - $1 >= 0 ) {
                delete @newtext[ 0 .. $#newtext - $1 ];
            }
            $text = join( "\n", @newtext );
            next;
        }
        if ( $line =~ /(.*[^\\])\/(.*[^\\])(\/([mgi])){0,1}$/ ) {
            $opt  = "";
            $from = $1;
            $to   = $2;
            if (0) {
                if ( $from =~ /(.*[^\\])\/(.*)/ ) {
                    $opt  = $to;
                    $from = $1;
                    $to   = $2;
                } elsif ( $to =~ /(.*[^\\])\/(.*)/ ) {
                    $from = $1;
                    $to   = $2;
                }
            }
            $to =~ s/\\\//\//g;
            $to =~ s/\\\$/\$/g;
            $to =~ s/\\N/\n/g;

            if ( $from eq "^" || $from eq "\$" ) {
                $text =~ s/$from/$to/;
            } elsif ( $to =~ /\\([0-9])/ ) {
                $text =~ s/$from/$to/geo;
            } elsif ( $from eq ".*" ) {
                $text = $to;
            } else {
                if ( $opt eq "m" ) {
                    $text =~ s/$from/$to/mg;
                } elsif ( $opt eq "g" || $opt eq "" ) {
                    $text =~ s/$from/$to/g;
                }
            }
        }
    }
    $text =~ s/$FSA/\n/g;
    return $text;
}

sub EvalLocalRules {
    my ( $rules, $origText, $isDiff ) = @_;
    my ( $text, $reportError, $errorText );

    $text        = $origText;
    $reportError = 1;

# Basic idea: the $rules should change $text, possibly with different behavior if $isDiff is true (no images or
# color changes?) Note: for fun, the $rules could also change $reportError and $origText
    if ( !eval $rules ) {
        $errorText = $@;
        if ( $errorText eq '' ) {

            # Search for "Unknown Error" for the reason the next line is commented
            $errorText = T('Unknown Error (no error text)');
        }
        if ( $errorText ne '' ) {
            $text = $origText;    # Consider: should partial results be kept?
            if ($reportError) {
                $text .= '<hr><b>' . T('Local rule error:') . '</b><br>' . &QuoteHtml($errorText);
            }
        }
    }
    return $text;
}

sub QuoteHtml {
    my ($html) = @_;

    $html =~ s/&/&amp;/g;
    $html =~ s/</&lt;/g;
    $html =~ s/>/&gt;/g;
    $html =~ s/&amp;([#a-zA-Z0-9]+);/&$1;/g;    # Allow character references
    return $html;
}

sub ParseParagraph {
    my ($text) = @_;

    $text = &CommonMarkup( $text, 1, 0 );       # Multi-line markup
    $text = &WikiLinesToHtml($text);            # Line-oriented markup
    return "<p>$text</p>\n";
}

sub StoreInterPage {
    my ( $id, $useImage ) = @_;
    my ( $link, $extra );

    ( $link, $extra ) = &InterPageLink( $id, $useImage );

    # Next line ensures no empty links are stored
    $link = &StoreRaw($link) if ( $link ne "" );
    return $link . $extra;
}

sub InterPageLink {
    my ( $id, $useImage ) = @_;
    my ( $name, $site, $remotePage, $url, $punct );

    ( $id, $punct ) = &SplitUrlPunct($id);
    $name = $id;
    ( $site, $remotePage ) = split( /:/, $id, 2 );
    $url = &GetSiteUrl($site);
    return ( "", $id . $punct ) if ( $url eq "" );
    $remotePage =~ s/&amp;/&/g;    # Unquote common URL HTML
    $url .= $remotePage;
    return ( &UrlLinkOrImage( $url, $name, $useImage ), $punct );
}

sub StoreBracketInterPage {
    my ( $id, $text, $useImage ) = @_;
    my ( $site, $remotePage, $url, $index );

    ( $site, $remotePage ) = split( /:/, $id, 2 );
    $remotePage =~ s/&amp;/&/g;    # Unquote common URL HTML
    $url = &GetSiteUrl($site);
    if ( $text ne "" ) {
        return "[$id $text]" if ( $url eq "" );
    } else {
        return "[$id]" if ( $url eq "" );
        $text = &GetBracketUrlIndex($id);
    }
    $url .= UrlEncode($remotePage);
    if ( $BracketImg && $useImage && &ImageAllowed($text) ) {
        $text = "<img src='$text'>";
    } else {
        $text = "$text";
    }
    return &StoreRaw("<a href='$url' class='wikiinterpage'>$text</a>");
}

sub GetBracketUrlIndex {
    my ($id) = @_;
    my ( $index, $key );

    # Consider plain array?
    if ( $$SaveNumUrl{$id} > 0 ) {
        return $$SaveNumUrl{$id};
    }
    $$SaveNumUrlIndex++;    # Start with 1
    $$SaveNumUrl{$id} = $$SaveNumUrlIndex;
    return $$SaveNumUrlIndex;
}

sub GetSiteUrl {
    my ($site) = @_;
    my ( $data, $status );

    if ( !$InterSiteInit ) {
        ( $status, $data ) = &ReadFile($InterFile);
        if ($status) {
            %InterSite = split( /\s+/, $data );    # Consider defensive code
        }

        # Check for definitions to allow file to override automatic settings
        if ( !defined( $InterSite{'LocalWiki'} ) ) {
            $InterSite{'LocalWiki'} = $ScriptName . &ScriptLinkChar();
        }
        if ( !defined( $InterSite{'Local'} ) ) {
            $InterSite{'Local'} = $ScriptName . &ScriptLinkChar();
        }
        $InterSiteInit = 1;    # Init only once per request
    }
    return $InterSite{$site} if ( defined( $InterSite{$site} ) );
    return '';
}

sub StoreRaw {
    my ($html) = @_;

    $$SaveUrl{$$SaveUrlIndex} = $html;
    return $FS . $$SaveUrlIndex++ . $FS;
}

sub StorePre {
    my ( $html, $tag ) = @_;

    return &StoreRaw( "<$tag>" . $html . "</$tag>" );
}

sub StoreHref {
    my ( $anchor, $text ) = @_;

    return "<a" . &StoreRaw($anchor) . ">$text</a>";
}

sub StoreUrl {
    my ( $name, $useImage ) = @_;
    my ( $link, $extra );

    ( $link, $extra ) = &UrlLink( $name, $useImage );

    # Next line ensures no empty links are stored
    $link = &StoreRaw($link) if ( $link ne "" );
    return $link . $extra;
}

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
    my ( %sect, %data, $oldText, $inlinerev, $vmajor, $vminor );

    $oldText = "";
    ( $vmajor, $vminor ) = split( /\./, $oldRevision );
    if ( defined( $KeptRevisions{$vmajor} ) ) {
        %sect = split( /$FS2/, $KeptRevisions{$vmajor}, -1 );
        %data = split( /$FS3/, $sect{'data'},           -1 );
        ( $oldText, $inlinerev ) = &PatchPage( $data{'text'}, $vminor );
    }
    return "" if ( $oldText eq "" );    # Old revision not found
    return &GetDiff( $oldText, $newText, $lock );
}

sub GetDiff {
    my ( $old, $new, $lock ) = @_;
    my ( $diff_out, $oldName, $newName, $key );

    return diff( \$old, \$new, { STYLE => 'OldStyle' } );
}

sub PatchText {
    my ( $base, $patch, $lock ) = @_;
    my ( $patch_out, $oldName, $newName, $key );

    if ( $patch =~ /^\@\@/ ) {
        return patch( $base, $patch, { STYLE => 'Unified' } );
    }
    return patch( $base, $patch, { STYLE => 'OldStyle' } );
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
    $$Page{$name}         = join( $FS2, %$Section );     # Replace with save?
}

sub OpenNewText {
    my ( $id, $name ) = @_;                              # Name of text (usually "default")
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
    &OpenNewSection( $id, "text_$name", join( $FS3, %$Text ) );
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
    if ( $rev eq "" ) {
        $sth = $dbh->selectall_arrayref("select max(revision),* from $pagedb where id='$id'");
    } else {
        $sth = $dbh->selectall_arrayref(
            "select revision,* from $pagedb where id='$id' and revision=$rev limit 1");
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
    my ( $fname, $data, $pagedb, $sth, $maxversion );
    my (
        $pgid,    $version, $author, $revision,  $tupdate, $tcreate, $ip, $host,
        $summary, $text,    $minor,  $newauthor, $Page,    $Text,    $Section
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
    $sth = $dbh->selectall_arrayref("select max(revision),* from $pagedb where id='$id'");
    if ( defined $sth->[0] ) {
        (
            $maxversion, $pgid, $version, $author, $revision, $tupdate,   $tcreate,
            $ip,         $host, $summary, $text,   $minor,    $newauthor, $data
        ) = @{ $sth->[0] };
        if ( $pgid eq "" || $revision eq "" ) {
            &OpenNewPage($id);
            &OpenNewText( $id, 'default' );
        } else {
            $$Page{'name'}     = $pgid;
            $$Page{'version'}  = $version;
            $$Page{'revision'} = $revision;
            $$Page{'tscreate'} = $tcreate;
            $$Page{'ts'}       = $tupdate;

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

            $$Section{'data'} = join( $FS3, %$Text );
            $$Page{ $$Section{'name'} } = join( $FS2, %$Section );
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
    } else {
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
        %$Text = split( /$FS3/, $$Section{'data'}, -1 );
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

    %$Section = split( /$FS2/, $KeptRevisions{$revision}, -1 );
    %$Text    = split( /$FS3/, $$Section{'data'},         -1 );
    ( $$Text{'text'}, $inlinerev ) = &PatchPage( $$Text{'text'}, $inlinerev );
}

sub GetPageCache {
    my ($name) = @_;

    return $Pages{$OpenPageName}->{'page'}->{"cache_$name"};
}

sub SavePageDB {
    my ($name) = @_;
    my ( $pagedb, $sth );
    my (
        $pgid, $version, $author, $revision, $tupdate,   $tcreate, $ip,
        $host, $summary, $text,   $minor,    $newauthor, $data
    );
    my ( $Page, $Text, $Section );

    $Page    = \%{ $Pages{$name}->{'page'} };
    $Section = \%{ $Pages{$name}->{'section'} };
    $Text    = \%{ $Pages{$name}->{'text'} };

    $pagedb = &GetPageDB($name);

    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $$Page{'name'} = $name;

    $sth = $dbh->selectall_arrayref("select max(revision),data from $pagedb where id='$name';");
    if ( defined $sth->[0] ) {
        ( $version, $data ) = @{ $sth->[0] };
        $$Page{'revision'} = $version;
        if ( $$Text{'minor'} != 1 ) {
            $$Page{'revision'} = $version + 1;
        }
    } else {
        $$Page{'revision'} = 0;
    }

    $pgid     = $$Page{'name'};
    $version  = $$Page{'version'};
    $revision = $$Page{'revision'};
    $tcreate  = $$Page{'tscreate'};
    $tupdate  = $Now;

    # $$Section{'name'}=$pgid; $$Section{'version'}=$version;
    if ( $$Text{'minor'} != 1 ) {
        $$Section{'revision'} += 1;
    }

    # $$Section{'tscreate'}=$tcreate; $$Section{'ts'}=$tupdate;
    $ip     = $$Section{'ip'};
    $host   = $$Section{'host'};
    $data   = $UserData{'id'};
    $author = $UserData{'username'};

    $text      = $$Text{'text'};
    $newauthor = $$Text{'newauthor'};
    $minor     = $$Text{'minor'};
    $summary   = $$Text{'summary'};

    if ($minor) {
        $sth = $dbh->do("delete from $pagedb where id='$pgid' and revision=$revision");
        $dbh->commit;
    }
    $sth =
      $dbh->prepare( "insert into $pagedb (id,version,author,revision,tupdate,"
          . "tcreate,ip,host,summary,text,minor,newauthor,data) values (?,?,?,?,?,?,?,?,?,?,?,?,?)"
      ) or die "Couldn't prepare statement: " . $dbh->errstr;
    $sth->execute(
        $pgid, $version, $author, $revision, $tupdate,   $tcreate, $ip,
        $host, $summary, $text,   $minor,    $newauthor, $data
    );

    # need to print log
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
    $$Page{$name}         = join( $FS2, %$Section );
}

sub SaveText {
    my ( $id, $name ) = @_;

    &SaveSection( "text_$name", join( $FS3, %{ $Pages{$id}->{'text'} } ) );
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
    my ($nopatch) = @_;    # Name of section
    my ( $fname, $data, %sections, %texts, $sth, $lim, $offset, $searchcmd, $moretocome );
    my $pagedb = &GetPageDB($OpenPageName);
    my (
        $pgid, $version, $author, $revision, $tupdate,   $tcreate,  $ip,
        $host, $summary, $text,   $minor,    $newauthor, @KeptList, $inlinerev
    );

    $lim    = GetParam( 'listc',  $HistoryLimit ) + 1;
    $offset = GetParam( 'offset', 0 );

    @KeptList = ();

    $searchcmd = "select * from $pagedb where id='$OpenPageName' limit $lim";
    if ( $offset ne '' && $offset > 0 ) {
        $searchcmd .= " offset $offset";
    }
    $sth = $dbh->selectall_arrayref($searchcmd);
    if ( defined $sth->[0] ) {
        if ( @{$sth} == $lim ) {
            pop( @{$sth} );
            $moretocome = "+";
        }
        foreach my $rec ( @{$sth} ) {
            my (
                $pgid, $version, $author, $revision, $tupdate,   $tcreate, $ip,
                $host, $summary, $text,   $minor,    $newauthor, $data
            ) = @$rec;
            if ( $pgid eq "" or $revision eq "" ) { next; }

            %texts = ();
            if ( $nopatch != 1 ) {
                ( $texts{'text'}, $inlinerev ) = &PatchPage($text);
            } else {
                $texts{'text'} = $text;
                if ( $text =~ /$FS4/ ) {
                    $inlinerev = ( split( /$FS4/, $text ) ) - 1;
                }
            }
            $texts{'minor'}     = $minor;
            $texts{'newauthor'} = $newauthor;
            $texts{'summary'}   = $summary;

            %sections              = ();
            $sections{'name'}      = "text_default";
            $sections{'version'}   = $version;
            $sections{'revision'}  = $revision;
            $sections{'inlinerev'} = $inlinerev if ( $inlinerev ne '' );
            $sections{'tscreate'}  = $tcreate;
            $sections{'ts'}        = $tupdate;
            $sections{'ip'}        = $ip;
            $sections{'host'}      = $host;
            $sections{'id'}        = $data;
            $sections{'username'}  = $author;
            $sections{'data'}      = join( $FS3, %texts );
            $KeptList[$revision]   = join( $FS2, %sections );
        }
    }
    return ( "Internal:Offset:$offset$moretocome", @KeptList );
}

sub OpenKeptRevisions {
    my ( $id, $name, $nopatch ) = @_;    # Name of section
    my ( $fname, $data, %tempSection, @KeptList, $rev );
    @KeptList      = &OpenKeptListDB($nopatch);
    %KeptRevisions = ();
    foreach $rev (@KeptList) {
        next if ( $rev eq '' );
        if ( $rev =~ /^Internal:Offset:([0-9]+[+]*)/ ) {
            $KeptRevisions{"Internal:Offset"} = $1;
            next;
        }
        %tempSection = split( /$FS2/, $rev, -1 );
        next if ( $tempSection{'name'} ne $name );
        $KeptRevisions{ $tempSection{'revision'} } = $rev;
    }
}

sub LoadUserDataDB {
    my ( $uid, $uname ) = @_;
    %UserData = ();
    my $userdb = ( split( /\//, $UserDir ) )[-1];
    my $sth;
    my (
        $id,         $name,       $pass,       $randkey,  $group,    $lang,
        $email,      $param,      $createtime, $createip, $tzoffset, $pagecreate,
        $pagemodify, $stylesheet, $extradata,  %extra
    );

    if ( $dbh eq "" || $userdb eq "" ) {
        return T('ERROR: database uninitialized!');
    }
    if ( $uname eq "" ) {
        $sth = $dbh->selectall_arrayref("select * from $userdb where id=$uid limit 1");
    } else {
        if ( $uname =~ /\@/ ) {
            $sth =
              $dbh->selectall_arrayref("select * from $userdb where email like '$uname' limit 1");
        } else {
            $sth =
              $dbh->selectall_arrayref("select * from $userdb where name like '$uname' limit 1");
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
            $id,       $name,     $pass,       $randkey,    $group,
            $lang,     $email,    $param,      $createtime, $extradata,
            $createip, $tzoffset, $pagecreate, $pagemodify
        ) = @{ $sth->[0] };
        %extra = split( /$FS2/, $extradata );
    }
    $UserData{'id'}         = $id;
    $UserData{'username'}   = $name;
    $UserData{'password'}   = $pass;
    $UserData{'adminpw'}    = $group;
    $UserData{'rawrandkey'} = $randkey;
    if ( $randkey =~ /$FS2/ ) {
        my %rkey = split( /$FS2/, $randkey );
        $UserData{'randkey'} = $rkey{&RemoteAddr};
    } else {
        $UserData{'randkey'} = $randkey;
    }
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
    $data   = ReadDBItems( "system", 'data', "\n", '', "id='banlist'" );
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
    } elsif ( $UserID > 1000 && $UserData{'id'} ne '' ) {
        $up = 1;
    } else {
        $up = -1;
    }
    $UserData{'clearance'} = $up;
    return $up;
}

sub UserIsAdmin {
    my ( @pwlist, $userPassword );

    return 0 if ( $AdminPass eq "" );
    $userPassword = &GetParam( "adminpw", "" );
    return 0 if ( $userPassword eq "" );
    foreach ( split( /\s+/, $AdminPass ) ) {
        next     if ( $_ eq "" );
        return 1 if ( crypt( $_, $userPassword ) eq $userPassword );
    }
    return 0;
}

sub UserIsEditor {
    my ( @pwlist, $userPassword );

    return 1 if ( &UserIsAdmin() );                # Admin includes editor
    return 0 if ( $EditPass eq "" );
    $userPassword = &GetParam( "adminpw", "" );    # Used for both
    return 0 if ( $userPassword eq "" );
    foreach ( split( /\s+/, $EditPass ) ) {
        next     if ( $_ eq "" );
        return 1 if ( crypt( $_, $userPassword ) eq $userPassword );
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
    my $htmldb = ( split( /\//, $HtmlDir ) )[-1];
    my ( $sth, $language );
    $language = &GetParam( 'lang', $LangID );

    if ( $dbh eq "" || $htmldb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $sth = $dbh->prepare("replace into $htmldb (id,time,text) values (?,?,?)");
    $sth->execute( "$id\[$language\]", $Now, $html );

    # need to print log
}

sub GenerateAllPagesListDB {
    my @pages;
    my $pagedb = GetParam( "dbprefix", "" ) . ( split( /\//, $PageDir ) )[-1];
    my ( $sth, $pg, $lim, $offset, $searchcmd );

    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $lim       = GetParam( 'listc',  $ListItemCount ) + 1;
    $offset    = GetParam( 'offset', 0 );
    $searchcmd = "select id from $pagedb group by id limit " . $lim;
    if ( $offset ne '' && $offset > 0 ) {
        $searchcmd .= " offset $offset";
    }
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

    $ts += $TimeZoneOffset;
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

    $ts += $TimeZoneOffset;
    my ( $sec, $min, $hour, $mday, $mon, $year ) = localtime($ts);
    return ( $year + 1900 ) . '-' . ( $mon + 1 ) . '-' . $mday;
}

sub CalcTime {
    my ($ts) = @_;
    my ( $ampm, $mytz );

    $ts += $TimeZoneOffset;
    my ( $sec, $min, $hour, $mday, $mon, $year ) = localtime($ts);
    $mytz = "";
    if ( ( $TimeZoneOffset == 0 ) && ( $ScriptTZ ne "" ) ) {
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

    $rhost = $ENV{REMOTE_HOST};
    if ( $UseLookup && ( $rhost eq "" ) ) {

        # Catch errors (including bad input) without aborting the script
        eval 'use Socket; $iaddr = inet_aton(&RemoteAddr);'
          . '$rhost = gethostbyaddr($iaddr, AF_INET)';
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

    $userdb = ( split( /\//, $UserDir ) )[-1];
    $regkey = &ReadDBItems( $userdb, 'param', '', '', "id='$uid'" );

    if ( $regkey eq $regid ) {
        if ( $dbh eq "" || $userdb eq "" ) {
            die( T('ERROR: database uninitialized!') );
        }
        $sth = $dbh->selectall_arrayref("select id from $userdb where id=$uid limit 1");
        if ( defined $sth->[0] ) {
            $sth = $dbh->prepare("update $userdb set param='' where id=$uid limit 1");
            $sth->execute();
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
    print '<span class="span_prefinfo"><label class="formlabel">' . T('User name:') . '</label>';
    if ( $UserData{'username'} ne '' ) {
        print "<span class='span_username'>" . $UserData{'username'} . "</span> ($UserID)";
        print &GetHiddenValue( 'p_username', $UserData{'username'} ), "\n";
    } else {
        print &GetFormText( 'username', "", 20, 30 ) . "<strong>*</strong>";
        print T('(IP address will be used if not supplied)');
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
      '</span><br/>';
    print '<span class="span_prefinfo"><label class="formlabel">' . T('Email Address:'), '</label>',
      &GetFormText( 'email', "", 20, 60 ) . '<strong>*</strong></span><hr class="wikilinepref"/>';
    if ( ( $AdminPass ne '' ) || ( $EditPass ne '' ) ) {
        print '<span class="span_prefinfo"><label class="formlabel">'
          . T('Administrator Password:'), '</label>',
          $q->password_field(
            -name      => 'p_adminpw',
            -value     => '*',
            -size      => 20,
            -maxlength => 50
          ),
          ' ', T('(blank to remove password)'), '</span><br>',
          T('(Administrator passwords are used for special maintenance.)');
    }
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
    my ( $username, $password, $password2, $newpass, $stylesheet, $lang, $email );

    # All link bar settings should be updated before printing the header
    &UpdatePrefCheckbox("toplinkbar");
    &UpdatePrefCheckbox("linkrandom");
    $username  = &GetParam( "p_username",   "" );
    $password  = &GetParam( "p_password",   "" );
    $password2 = &GetParam( "p_password2",  "" );
    $newpass   = &GetParam( "new_password", "" );
    $email     = &GetParam( "p_email",      "" );

    if ( $UserID < 1001 ) {
        &DoNewLoginDB() if ( $UserID < 400 );
        if ($UseActivation) {
            undef $SetCookie{'id'};
        }
        if ( $email eq "" ) {
            PrintMsg( T("You have to give an email address"), T("Error"), 1 );
        }
    } else {    # for existing users, you have to match password before changing anything
        if ( $UserData{'password'} ne crypt( $password, $UserData{'password'} ) ) {
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
    if ( $username eq "" ) {

        #removing username is not allowed now
        #print T('UserName removed.'), '<br>';
        #undef $UserData{'username'};
        die( T('User name can not be empty.') );
    } elsif ( ( !$FreeLinks ) && ( !( $username =~ /^$LinkPattern$/ ) ) ) {
        die Ts( 'Invalid UserName %s: not saved.', $username ), "<br>\n";
    } elsif ( $FreeLinks && ( !( $username =~ /^$FreeLinkPattern$/ ) ) ) {
        die Ts( 'Invalid UserName %s: not saved.', $username ), "<br>\n";
    } elsif ( length($username) > 50 ) {    # Too long
        die T('UserName must be 50 characters or less. (not saved)'), "<br>\n";
    } else {
        $UserData{'username'} = $username;
    }
    if ( $password eq "" ) {
        die( T("User must set an non-empty password.") );
    } elsif ( length($password) < 8 ) {
        die( T("Password is shorter than 8 char.") );
    } elsif ( $password =~ /[^a-zA-Z0-9_@^\]\[!@\$%^&]/ ) {
        die( T("Password can only contain basic latin, digits or one of '[]!\@\$%^&'.") );
    } elsif ( $password ne "*" ) {
        print T('Password changed.'), '<br>';
        $UserData{'password'} = crypt( $password, unpack( "H16", $CaptchaKey ) );
    }
    if ( ( $AdminPass ne "" ) || ( $EditPass ne "" ) ) {
        $password = &GetParam( "p_adminpw", "" );
        if ( $password eq "" ) {
            print T('Administrator password removed.'), '<br>';
            undef $UserData{'adminpw'};
        } elsif ( $password ne "*" ) {
            print T('Administrator password changed.'), '<br>';
            $UserData{'adminpw'} = crypt( $password, unpack( "H16", $CaptchaKey ) );
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
    &SaveUserDataDB();
    if ( $UserID >= 1000 ) {
        AddUserLogDB( $UserID, 'Sp', '' );
    }
    print '<b>', T('Preferences saved.'), '</b>';
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

# Create a new user file/cookie pair
sub DoNewLoginDB {

    # Consider warning if cookie already exists (maybe use "replace=1" parameter)
    $SetCookie{'id'}      = &GetNewUserIdDB();
    $SetCookie{'randkey'} = sprintf( "%08X%08X", int( rand(0x10000000) ), int( rand(0x10000000) ) );
    $SetCookie{'rev'}     = 1;
    $SetCookie{'lang'}    = $LangID;
    %UserCookie           = %SetCookie;
    $UserID               = $SetCookie{'id'};

    # The cookie will be transmitted in the next header
    %UserData               = %UserCookie;
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
    my ( $uid, $uname, $password, $admpass, $success, $err );

    $success = 0;
    $uid     = &GetParam( "p_userid", "" );
    $uid =~ s/\D//g;
    $uname    = &GetParam( "p_username",  "" );
    $password = &GetParam( "p_password",  "" );
    $admpass  = &GetParam( "p_adminpass", "" );

    if ( ( $password ne "" ) && ( $password ne "*" ) ) {
        if ( $uname ne "" ) {
            $err = &LoadUserDataDB( -1, $uname );
        } else {
            $err = &LoadUserDataDB($uid);
        }
        $UserID = $UserData{'id'};
        if ( $UserID > 199 ) {
            if ( $UserData{'param'} =~ /^R/ ) {
                $err = T("account has not yet been activated");
            } elsif ( defined( $UserData{'password'} )
                && ( $UserData{'password'} eq crypt( $password, $UserData{'password'} ) ) )
            {
                $success = 1;
                $SetCookie{'id'} = $UserData{'id'};
            } else {
                $err .= T("wrong password");
            }
        }
    }
    if ($success) {
        my $refurl = &GetParam( "refer_url", "" );
        ResetRandKeyDB( $UserID, $UserData{'param'} );
        if ( $refurl =~ /^http/i ) {
            AddUserLogDB( $UserID, 'login', $uname );
            print &GetRedirectPage( $refurl,
                T("if your browser does not support redirect, please click this link"), 1 );
            return;
        }
    }

    print &GetHeader( '', T('Login Results'), '' );
    print '<div class="wikiinfo">';
    if ($success) {
        print Ts( 'Login for user %s complete.', "$uname" );
        AddUserLogDB( $UserID, 'login', $uname );
    } else {
        print Tss( 'Login for user %1 failed. Error: %2', "$uname", $err );
        AddUserLogDB( $UserID, 'login', '-F' );
    }
    print '<hr class="wikilinefooter">';
    print $q->end_form;
    print "</div>";
    print &GetMinimumFooter();
}

sub ResetRandKeyDB {
    my ( $uid, $param ) = @_;
    my $userdb = ( split( /\//, $UserDir ) )[-1];
    my $sth;

    if ( $UseActivation && $param =~ /^R/ ) {
        return;
    }
    $SetCookie{'id'}      = $uid;
    $SetCookie{'randkey'} = sprintf( "%08X%08X", int( rand(0x10000000) ), int( rand(0x10000000) ) );
    $UserData{'randkey'}  = $SetCookie{'randkey'};

    if ( $dbh eq "" || $userdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $sth = $dbh->selectall_arrayref("select id from $userdb where id=$uid limit 1");
    if ( defined $sth->[0] ) {
        my %rkey;
        if ( $sth =~ /$FS2/ ) {
            %rkey = split( /$FS2/, $sth );
        }
        $rkey{&RemoteAddr} = $UserData{'randkey'};
        $sth = $dbh->prepare("update $userdb set randkey= ? where id=$uid");
        $sth->execute( join( $FS2, %rkey ) );
    }
}

sub GetNewUserIdDB {
    my ( $id, $rest, $count );
    my $userdb = ( split( /\//, $UserDir ) )[-1];
    my $sth;

    if ( $dbh eq "" || $userdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
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
    my $userdb = ( split( /\//, $UserDir ) )[-1];
    my (
        $id,       $sth,     $encpass,   $isnewuser, $tmp,   $name,
        $passhash, $randkey, $adminhash, $linkchr,   %extra, %rkey
    );

    if ( $dbh eq "" || $userdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $tmp       = ReadDBItems( $userdb, 'id', "\n", '', "name='" . $UserData{'username'} . "'" );
    $isnewuser = 0;
    if ( $tmp eq '' ) {
        $isnewuser = 1;
    } elsif ( $tmp ne $UserID ) {
        die( Ts( 'ERROR: user name %s has already been taken!', $UserData{'username'} ) );
    }
    $tmp = ReadDBItems( $userdb, 'id', "\n", '', "email='" . $UserData{'email'} . "'" );
    if ( $tmp ne '' && $tmp ne $UserID ) {
        die( Ts( 'ERROR: user email %s has already been taken!', $UserData{'email'} ) );
    }
    $passhash  = ReadDBItems( $userdb, 'pass', "\n", '', "name='" . $UserData{'username'} . "'" );
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
    );
    if ( defined( $UserData{'rawrandkey'} ) ) {
        %rkey = split( /$FS2/, $UserData{'rawrandkey'} );
    }
    $rkey{&RemoteAddr} = $UserData{'randkey'};

    $sth = $dbh->prepare(
            "replace into $userdb (id,name,pass,randkey,groupid,lang,email,param,createtime,"
          . "createip,tzoffset,pagecreate,pagemodify,stylesheet) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    );
    $sth->execute(
        $UserID,                 $UserData{'username'},
        $encpass,                join( $FS2, %rkey ),
        $adminhash,              $UserData{'lang'},
        $UserData{'email'},      $UserData{'param'},
        $UserData{'createtime'}, $UserData{'createip'},
        $UserData{'tzoffset'},   $UserData{'pagecreate'},
        $UserData{'pagemodify'}, join( $FS2, %extra )
    ) or die($DBI::errstr);
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
        $q->url( -full => 1 )
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
    my ($id)    = @_;
    my $watchdb = ( split( /\//, $EmailFile ) )[-1];
    my $user    = $UserData{'username'};

    if ( not( $UserID <= 1000 || $user eq '' || $id eq '' ) ) {
        if ( ReadDBItems( $watchdb, 'user', ',', '', "page='$id' and user='$user'" ) eq '' ) {
            &WriteDBItems( $watchdb, 'page,user', 0, ( $id, $user ) );
            AddUserLogDB( $UserID, 'watch', $id );
        }
    }
    print &GetHeader( '', T('Watch Page'), '' );
    print '<div class="wikiinfo">' . Ts( 'Watch activated for page "%s".', $id );
    print '</div>';
    print &GetCommonFooter();
}

sub DoUnWatchPage {
    my ($id)    = @_;
    my $watchdb = ( split( /\//, $EmailFile ) )[-1];
    my $user    = $UserData{'username'};

    if ( $dbh && not( $UserID <= 1000 || $user eq '' || $id eq '' ) ) {
        my $sth = $dbh->do("delete from $watchdb where page='$id' and user='$user'");
        $dbh->commit;
    }
    print &GetHeader( '', T('Watch Page'), '' );
    print '<div class="wikiinfo">' . Ts( 'Watch removed for page "%s".', $id );
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
        if ( $moretocome ne '' ) {
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

    if ($UseDiff) {
        my $diffstr = &GetDiff( $old, $string, 0 );
        if ( ( $isEdit || length($diffstr) < length($old) * 0.25 ) && $diffstr ne '' ) {
            my $rawdata = &ReadRawWikiPage( $id, 1 );
            my @oldrec  = split( /$FS4/, $rawdata );
            if ( @oldrec <= $InlineDiffLimit ) {
                my $revstr = "$Now|$user|" . &GetRemoteHost(1) . "|$summary$FS5";
                $string               = $rawdata . $FS4 . $revstr . $diffstr;
                $$Section{'revision'} = $oldrev;
                $isEdit               = 1;
            } else {
                $isEdit = 0;
            }
        }
    }
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
        my $htmldb   = ( split( /\//, $HtmlDir ) )[-1];
        my $language = &GetParam( "lang", $LangID );
        if ( $dbh eq "" || $htmldb eq "" ) {
            die( T('ERROR: database uninitialized!') );
        }
        DeleteDBItems( $htmldb, "id='$id\[$language\]'" );
        if ( $isdynapg ne '' ) {
            DeleteDBItems( $htmldb, "id='$isdynapg\[$language\]'" );
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
sub SendEmail {
    my ( $to, $from, $reply, $subject, $message ) = @_;

    if ( $SendMail =~ /\/mail$/ ) {
        open FF, ">debugmail.log";
        print FF "$to, $from, $reply, $subject, $message\n\n$SendMail";
        close(FF);
        &MailEmail( $to, $from, $reply, $subject, $message );
        return;
    }

# sendmail options:
#    -odq : send mail to queue (i.e. later when convenient) -oi : do not wait for "." line to exit -t : headers
#    determine recipient.
    open( SENDMAIL, "| $SendMail -oi -t " ) or die "Can't send email: $!\n";
    print SENDMAIL <<"EOF";
From: $from
To: $to
Reply-to: $reply
Subject: $subject\n
$message
EOF
    close(SENDMAIL) or warn "sendmail didn't close nicely";
}

# Translation note: the email messages are still sent in English Send an email message.
sub MailEmail {
    my ( $to, $from, $reply, $subject, $message ) = @_;
    open( SENDMAIL, "| $SendMail -s '$subject' '$to'" ) or die "Can't send email: $!\n";
    print SENDMAIL <<"EOF";
$message
EOF
    close(SENDMAIL) or warn "mail didn't close nicely";
}

sub ReadWatchListDB {
    my ($id) = @_;
    my ( $addr, $userlist );
    my $watchdb = ( split( /\//, $EmailFile ) )[-1];
    my $userdb  = ( split( /\//, $UserDir ) )[-1];

    if ( $dbh eq "" || $watchdb eq "" || $userdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $userlist = ReadDBItems( $watchdb, 'user', "\n", '', "page='$id'" );
    if ( $userlist ne '' ) {
        my @users  = split( /\n/, $userlist );
        my $sqlcmd = "'" . join( "','", @users ) . "'";
        $addr = ReadDBItems( $userdb, 'email', ',', '', "name IN ($sqlcmd)" );
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

        my $home_url        = $q->url( -full => 1 );
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

    $pagedb   = ( split( /\//, $PageDir ) )[-1];
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
    foreach my $key ( keys %cmd ) {
        if ( length($searchcmd) ) { $searchcmd .= " AND "; }
        $searchcmd .= "$key '" . $cmd{$key} . "' ";
    }
    if ( $searchcmd eq "" ) { return (); }
    $searchcmd = "select id from $pagedb where $searchcmd group by id limit $lim";
    if ( $offset ne '' && $offset > 0 ) {
        $searchcmd .= " offset $offset";
    }
    $sth = $dbh->selectall_arrayref($searchcmd);
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
    my $htmldb = ( split( /\//, $HtmlDir ) )[-1];

    if ( $dbh eq "" || $htmldb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
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
    $rclogdb = ( split( /\//, $RcFile ) )[-1];
    if ( $dbh eq "" || $rclogdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
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

    print &GetHeader( '', T('Set or Remove global edit lock'), '' );
    return if ( !&UserIsAdminOrError() );
    $fname = "$DataDir/noedit";
    if ( &GetParam( "set", 1 ) ) {
        &WriteDBItems( "system", 'id,data,time', 1, ( "lockstate", "1", $Now ) );
        print '<div class="wikiinfo">', T('Edit lock created.'), '</div>';
    } else {
        &WriteDBItems( "system", 'id,data,time', 1, ( "lockstate", "0", $Now ) );
        print '<div class="wikiinfo">', T('Edit lock removed.'), '</div>';
    }
    print &GetCommonFooter();
}

sub DoPageLock {
    my ( $fname, $id, $tag, $lockdb );

    print &GetHeader( '', T('Set or Remove page edit lock'), '' );

    # Consider allowing page lock/unlock at editor level?
    return if ( !&UserIsAdminOrError() );
    $id = &GetParam( "id", "" );
    if ( $id eq "" ) {
        print '<p>', T('Missing page id to lock/unlock...');
        return;
    }
    return if ( !&ValidIdOrDie($id) );    # Consider nicer error?
    $lockdb = ( split( /\//, $LockDir ) )[-1];
    $tag    = ReadDBItems( $lockdb, 'tag', '', '', "id='$id'" );
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
    my ($sth);
    return if ( $UseDetailedLog != 1 );
    if ( $dbh eq "" || $dbname eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $sth =
      $dbh->do("insert into $dbname (id,lastvisit,visit,x,y,z) values ('$id',$Now,0,-1,-1,-1);");
    $dbh->commit;    # sqlite does not support "on duplicate key update"
    $sth = $dbh->do("update $dbname set lastvisit=$Now, visit=visit+1 where id='$id';");
    $dbh->commit or die "Can't execute: ", $dbh->errstr;
}

sub AddUserLogDB {
    my ( $uid, $action, $target ) = @_;
    my $dbname = ( split( /\//, $UserLog ) )[-1];
    return if ( $UseDetailedLog != 1 );
    if ( $dbh eq "" || $dbname eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $dbh->do( "insert into $dbname (id,time,ip,action,target) values ($uid,$Now,'"
          . &RemoteAddr
          . "','$action','$target');" );
    $dbh->commit or die "Can't execute: ", $dbh->errstr;
}

sub WriteDBItems {
    my ( $dbname, $fields, $doreplace, @vals ) = @_;
    my ( @res, $sth, $action, $holder );
    if ( $dbh eq "" || $dbname eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $fields = "*" if ( $fields eq "" );
    $action = "insert";
    $action = "replace" if $doreplace;    #this is dangerous, you have to give the full record
    $holder = $fields;
    $holder =~ s/[0-9a-zA-Z_]+/?/g;
    $sth = $dbh->prepare("$action into $dbname ($fields) values ($holder);")
      or die "Can't prepare: ", $dbh->errstr;
    $sth->execute(@vals) or die "Can't execute: ", $dbh->errstr;
}

sub CopyDBItems {
    my ( $db1, $db2, $conditions ) = @_;
    my ( @res, $sth );

    if ( $dbh eq "" || $db1 eq "" || $db2 eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    if ( $conditions ne "" ) {
        $sth = $dbh->do("replace into $db2 select * from $db1 where $conditions;");
        $dbh->commit;
    }
    if ( defined $sth ) {
        return $sth;
    }
    return 0;
}

sub DeleteDBItems {
    my ( $dbname, $conditions ) = @_;
    my ( @res, $sth );

    if ( $dbh eq "" || $dbname eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    if ( $conditions eq "" ) {

        #$sth=$dbh->do("delete from $dbname;");
        #this will empty everything, it is dangerous, so skip
    } else {
        $sth = $dbh->do("delete from $dbname where $conditions;");
        $dbh->commit;
    }
    if ( defined $sth ) {
        return $sth;
    }
    return 0;
}

sub ReadDBItems {
    my ( $dbname, $fields, $glue1, $glue2, $conditions ) = @_;
    my ( @res, $sth );
    if ( $dbh eq "" || $dbname eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $fields = "*" if ( $fields eq "" );
    if ( $conditions eq "" ) {
        $sth = $dbh->selectall_arrayref("select $fields from $dbname;");
    } else {
        $sth = $dbh->selectall_arrayref("select $fields from $dbname where $conditions;");
    }
    if ( defined $sth->[0] ) {
        foreach my $rec (@$sth) {
            if ( @{$rec} > 0 ) {
                push( @res, join( $glue2, @{$rec} ) );
            }
        }
    }
    return join( $glue1, @res );
}

sub DoEditBanned {
    my ( $banList, $status );

    print &GetHeader( "", T("Editing Banned list"), "" );
    return if ( !&UserIsAdminOrError() );
    $banList = ReadDBItems( "system", 'data', "\n", '', "id='banlist'" );
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

    print &GetHeader( "", T("Updating Banned list"), "" );
    return if ( !&UserIsAdminOrError() );
    $fname   = "$DataDir/banlist";
    $newList = &GetParam( "banlist", "#Empty file" );
    print '<div class="wikiinfo">';
    if ( $newList eq "" ) {
        print "<p>Empty banned list or error.";
        print "<p>Resubmit with at least one space character to remove.";
    } elsif ( $newList =~ /^\s*$/s ) {
        WriteDBItems( "system", 'id,data,time', 1, ( "banlist", "", $Now ) );

        print "<p>Removed banned list";
    } else {
        WriteDBItems( "system", 'id,data,time', 1, ( "banlist", $newList, $Now ) );
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
    my ( $text, @patches );
    my $pagedb = &GetPageDB($page);

    if ( $dbh eq "" || $pagedb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $text = ReadDBItems( $pagedb, 'text', '', '', "id='$page' and revision=$major" );
    if ( $text eq "" ) {
        die( T('ERROR: specified revision does not exist!') . "$page:$major.$minor" );
    }
    @patches = split( /$FS4/, $text );
    if ( $#patches >= $minor ) {
        my $sth =
          $dbh->prepare("update $pagedb set text= ? where id='$page' and revision='$major'");
        splice( @patches, $minor, @patches - $minor );
        $sth->execute( join( $FS4, @patches ) );
    }
}

# Delete and rename must be done inside locks.
sub DeletePage {
    my ( $page, $doRC, $doText, $rev ) = @_;
    my ( $fname, $status, $res );

    $page =~ s/ /_/g;
    $page =~ s/\[+//;
    $page =~ s/\]+//;
    $status = &ValidId($page);
    if ( $status ne "" ) {
        print "Delete-Page: page $page is invalid, error is: $status<br>\n";
        return;
    }
    my $pagedb  = &GetPageDB($page);
    my $rclogdb = ( split( /\//, $RcFile ) )[-1];
    my $htmldb  = ( split( /\//, $HtmlDir ) )[-1];

    if ( $dbh eq "" || $pagedb eq "" || $rclogdb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    if ( $rev ne "" && $rev >= 0 ) {
        if ( $rev =~ /^([0-9]+)\.([0-9]+)/ && $2 > 0 ) {
            $res = &CopyDBItems( $pagedb, "deleted$pagedb", "id='$page' and revision=$1" );
            $res = &DeletePageRevisionFrom( $page, $1, $2 );
            $res = &DeleteDBItems( $rclogdb, "id='$page' and revision=$rev" ) if ($doRC);
        } else {
            $res = &CopyDBItems( $pagedb, "deleted$pagedb", "id='$page' and revision=$rev" );
            $res = &DeleteDBItems( $pagedb,  "id='$page' and revision=$rev" );
            $res = &DeleteDBItems( $rclogdb, "id='$page' and revision=$rev" ) if ($doRC);
        }
    } else {
        $res = &CopyDBItems( $pagedb, "deleted$pagedb", "id='$page'" );
        $res = &DeleteDBItems( $pagedb,  "id='$page'" );
        $res = &DeleteDBItems( $rclogdb, "id='$page'" ) if ($doRC);
    }
    $res = &DeleteDBItems( $htmldb, "id LIKE '$page\[%\]'" );
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

# Rename is mostly copied from expire
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
                %$Text   = split( /$FS3/, $$Section{'data'}, -1 );
                $oldText = $$Text{'text'};
                $newText = &SubstituteTextLinks( $old, $new, $oldText );
                if ( $oldText ne $newText ) {
                    $$Text{'text'}    = $newText;
                    $$Section{'data'} = join( $FS3, %$Text );
                    $$Page{$section}  = join( $FS2, %$Section );
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
    $tbname = &GetPageDB($old);
    $sth    = $dbh->prepare("update $tbname set id='$new' where id='$old'");
    $sth->execute();

    $tbname = ( split( /\//, $RcFile ) )[-1];
    $sth    = $dbh->prepare("update $tbname set id='$new' where id='$old'");
    $sth->execute();

    $tbname = ( split( /\//, $HtmlDir ) )[-1];
    $sth    = $dbh->prepare("update $tbname set id='$new' where id='$old'");
    $sth->execute();

    $tbname = ( split( /\//, $EmailFile ) )[-1];
    $sth    = $dbh->prepare("update $tbname set page='$new' where page='$old'");
    $sth->execute();
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

    if ($FreeLinks) {
        $id = &FreeToNormal($id);
    }
    return &ScriptLink( "action=pagelock&set=$status&id=$id", $name );
}

sub GetPageWatchLink {
    my ( $id, $status, $name ) = @_;

    if ($FreeLinks) {
        $id = &FreeToNormal($id);
    }
    if ($status) {
        return &ScriptLink( "action=watch&id=$id", $name );
    } else {
        return &ScriptLink( "action=unwatch&id=$id", $name );
    }
}

sub GetLockState {
    my ($lockstate);
    $lockstate = ReadDBItems( "system", 'data', '', '', "id='lockstate'" );
    $lockstate = 0 if ( $lockstate != 1 );

    return $lockstate;
}

sub IsPageLocked {
    my ($id) = @_;
    my ( $lockdb, $tag );
    $lockdb = ( split( /\//, $LockDir ) )[-1];
    $tag    = ReadDBItems( $lockdb, 'tag', '', '', "id='$id'" );
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
    if ( &GetLockState == 1 ) {
        $result .= '<li>' . &ScriptLink( "action=editlock&set=0", T("Unlock site") );
    } else {
        $result .= '<li>' . &ScriptLink( "action=editlock&set=1", T("Lock site") );
    }
    $result .= '</ul></div><!--/CACHE-->';
    return $result;
}

sub IsPageWatched {
    my ($id) = @_;
    my ( $watchdb, $tag );
    my $user = $UserData{'username'};

    if ( $UserID > 1000 ) {
        $watchdb = ( split( /\//, $EmailFile ) )[-1];
        $tag     = ReadDBItems( $watchdb, 'user', '', '', "page='$id' and user='$user'" );
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
    print
'File to Upload: <input type="file" name="file"><br><br><input type="checkbox" name="dothumb" value="on" />Create thumbnail<br>';
    print '<input type="submit" name="Submit" value="Upload">';
    print '</form></div>';
    print &GetCommonFooter();
}

sub SaveUpload {
    my ( $filename, $printFilename, $uploadFilehandle );

    print &GetHeader( '', T('Upload Finished'), '' );
    if ( !$AllUpload ) {
        return if ( &UserPermission() < $PermUseUpload );
    }
    print '<div class="wikitext">';

    $UploadDir .= '/' if ( substr( $UploadDir, -1, 1 ) ne '/' );    # End with /
    $UploadUrl .= '/' if ( substr( $UploadUrl, -1, 1 ) ne '/' );    # End with /
    $filename = $q->param('file');
    $filename =~ s/.*[\/\\](.*)/$1/;                                # Only name after last \ or /
    $uploadFilehandle = $q->upload('file');
    open UPLOADFILE, ">$UploadDir$filename";
    while (<$uploadFilehandle>) { print UPLOADFILE; }
    close UPLOADFILE;

    print T('The wiki link to your file is:') . "\n<br><br>";
    $printFilename = $filename;
    $printFilename =~ s/ /\%20/g;    # Replace spaces with escaped spaces
    print "upload:" . $printFilename . "<br><br>\n";
    if ( $filename =~ /${ImageExtensions}$/ ) {
        print '<hr><img src="' . $UploadUrl . $filename . '">' . "\n";
        if ( $q->param('dothumb') eq 'on' ) {
            system(
"convert -sample 200x200 \"$UploadDir$filename\" \"$UploadDir/thumb/mini_$filename\""
            );
            print '<hr>upload:thumb/mini_'
              . $printFilename
              . '<hr><img src="'
              . $UploadUrl
              . '/thumb/mini_'
              . $filename . '">' . "\n";
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
    $sth = $dbh->selectall_arrayref("select max(revision),text from $pagedb where id='$id';");
    if ( defined $sth->[0] ) {
        ( $maxversion, $text ) = @{ $sth->[0] };
        if ( defined $maxversion && $maxversion ne "" ) {
            ( $text, $inlinerev ) = &PatchPage($text) if ( $force eq '' );
            $TextCache{$id} = $text;
            return $text;
        }
    }
    return "" if ( $BuildinPages{$id} eq '' );
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
            $fname = $$rule{$name};
            open FRULE, "<$fname" || die("can not read file");
            @ru = <FRULE>;
            close FRULE;
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
    my $htmldb = ( split( /\//, $HtmlDir ) )[-1];
    if ( $dbh eq "" || $htmldb eq "" ) {
        die( T('ERROR: database uninitialized!') );
    }
    $lang = '%' if ( $lang eq '' );
    DeleteDBItems( $htmldb, "id='$id\[$lang\]'" );
}

sub PrintCaptcha {
    my ( $opA, $opB, $opR, $opt, $cryres, $plusbuf );

    $opA = int( rand(24) + 1 );
    $opB = int( rand(24) + 1 );

    #$opR=(rand()>0.5)?"+":"-";
    $opR     = "+";
    $plusbuf = " " x int( rand(3) );

    $opt = ( rand() > 0.5 ) ? "$opA$opR$plusbuf$opB" : "$opA$plusbuf$opR$opB";
    $opt .= " " x ( 8 - length($opt) );

    $cryres = unpack( "H16", $WikiCipher->encrypt($opt) );

    return
"<span class='wikicaptcha'>$opA+$opB=<input type='text' id='captchaans' size='4' name='captchaans' 
title='type your answer here'/> <input type='hidden' name='captchaopt' id='captchaopt' value='$cryres' /></span>\n";
}

sub VerifyCaptcha {
    my ( $userans, $cryres ) = @_;

    my $opt = $WikiCipher->decrypt( pack( 'H16', $cryres ) );
    my $trueans;
    if ( $opt =~ /([0-9]+)\s*\+\s*([0-9]+)/ ) {
        $trueans = $1 + $2;
    }
    if   ( $opt eq "" || $cryres eq "" ) { return 0; }
    else                                 { return ( $userans == $trueans ); }
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
    $remote = $ENV{'HTTP_X_REMOTE_ADDR'}
      if $ENV{'HTTP_X_REMOTE_ADDR'} && ( !$remote || $remote =~ /^(127|192)\./ );

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

&DoWikiRequest()
  if ( $RunCGI && ( $_ ne 'nocgi' ) );    # Do everything. 1; # In case we are loaded from elsewhere

# == End of UseModWiki script. ===========================================
