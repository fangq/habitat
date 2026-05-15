#
# Habitat::Render — the wiki's rendering pipeline, extracted from
# index.cgi across two phases:
#
#   Phase 1 (utilities, ~370 lines moved):
#     - Link/regex pattern initialisation:  InitLinkPatterns
#     - Field-separator placeholders:       StoreRaw, StorePre, StoreHref,
#                                           StoreUrl, GetBracketUrlIndex,
#                                           RestoreSavedText, RemoveFS
#     - Local-rule pipeline:                ApplyRegExp, ApplyRegExpRules,
#                                           EvalLocalRules, _ExpandBackrefs
#     - HTML output safety:                 ScrubRawHtml, QuoteHtml
#
#   Phase 2 (the wiki-syntax pipeline, ~440 lines moved):
#     - Top-level entry:                    WikiToHTML
#     - Multi-line + line-oriented syntax:  CommonMarkup, WikiLinesToHtml,
#                                           ParseParagraph
#     - Inter-site link helpers:            StoreInterPage, InterPageLink,
#                                           StoreBracketInterPage, GetSiteUrl
#
# Still in index.cgi (tightly coupled to %Pages and the filesystem
# layer): RestorePageHash, BuildRuleStack, GetLocalTree, EmbedWikiPage,
# EmbedWikiPageRaw, BuildWikiTree, GetVariable, GetXMLFields. These
# walk page directories, read raw page files, and resolve inclusions —
# moving them would be a separate cut (Phase 3) once their I/O is
# centralised.
#
# Why `package HabitatEngine` here, not `package Habitat::Render`?
# Every renderer sub reads/writes a dozen-plus engine globals (the
# %SaveUrl table, the link-pattern regexes, $FS, $Pages, …) and
# calls other engine subs via barewords. Declaring the new file
# under HabitatEngine means all those names resolve naturally —
# `&UrlLink(...)` finds index.cgi's UrlLink, `$LinkPattern` is the
# package global both files share. This is plumbing — the file
# split is for human navigation, the package is the same one
# index.cgi already declares at the top.
#
# To extend: add a new sub here, delete the corresponding sub block
# from index.cgi, run `prove -j4 test/*.t`. No import list to keep
# in sync — the `use Habitat::Render;` line in index.cgi just loads
# the file and the package globals are populated.

package HabitatEngine;

# index.cgi already declares globals via `use vars qw(...)`. Re-
# declaring is harmless on the second `package HabitatEngine` block,
# but unnecessary — these names are visible because we are literally
# the same package.

# ----------------------------------------------------------------
# Link/regex pattern initialisation. Called once at startup and
# again whenever the relevant config flags ($FreeLinks, $UseSubpage,
# $NonEnglish, …) might have changed. Resets $LinkPattern,
# $FreeLinkPattern, $UrlPattern, etc. used by the wiki-syntax
# regex pipeline.
# ----------------------------------------------------------------
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
            $AnyLetter = "[-,.()' _0-9A-Za-z\x80-\xff]";
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

# ----------------------------------------------------------------
# Field-separator placeholder protocol. The wiki text pipeline
# replaces "complex" matches (raw HTML blocks, pre/code spans,
# generated links) with `$FS<index>$FS` sentinels and stashes the
# real output in %$SaveUrl. After the line-oriented regex pass
# completes, RestoreSavedText swaps the sentinels back. RemoveFS
# is the failsafe last-pass cleanup if any sentinel survived.
# ----------------------------------------------------------------
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
    $text = '' if ( !defined($text) );
    return "<a" . &StoreRaw($anchor) . ">$text</a>";
}

sub StoreUrl {
    my ( $name, $useImage ) = @_;
    my ( $link, $extra );

    ( $link, $extra ) = &UrlLink( $name, $useImage );
    $link  = '' if ( !defined($link) );
    $extra = '' if ( !defined($extra) );

    # Next line ensures no empty links are stored
    $link = &StoreRaw($link) if ( $link ne "" );
    return $link . $extra;
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

# ----------------------------------------------------------------
# Local-rule pipeline. Each page can optionally carry a body of
# regex rewrite rules (line-oriented for ApplyRegExpRules, or a
# structured JSON form for EvalLocalRules) that run BEFORE the wiki
# syntax pass. ApplyRegExp consults %$namespace to find which
# rule set applies to a given page id.
# ----------------------------------------------------------------
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
    if ( defined($pagepath) && ref($pagepath) eq 'ARRAY' && @$pagepath ) {
        $pageText = &ApplyRegExpRules( join( '', @$pagepath ), $pageText, 0 );
    }
    return $pageText;
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

sub _ExpandBackrefs {
    my ( $tpl, $caps ) = @_;
    $tpl =~
      s{\\(\d)|\$(\d)}{ defined $caps->[ ( $1 || $2 ) - 1 ] ? $caps->[ ( $1 || $2 ) - 1 ] : '' }ge;
    return $tpl;
}

# $rules is a JSON array of {from, to, opt} objects, applied in order.
#   from : regex source (no /.../ delimiters)
#   to   : replacement string; \1..\9 or $1..$9 expand to capture groups
#   opt  : any of "gimsx"; "g" controls global replace (defaults on)
# An empty/undef $rules is a no-op. Parse errors and per-rule regex
# compilation errors are reported inline; we never eval user-supplied
# Perl. $isDiff is reserved for future use (e.g. skipping image rules).
sub EvalLocalRules {
    my ( $rules, $origText, $isDiff ) = @_;
    return $origText if ( !defined($rules) || $rules eq '' );

    my $text = $origText;
    my $parsed;
    eval { $parsed = decode_json($rules); };
    if ( $@ || ref($parsed) ne 'ARRAY' ) {
        my $err = $@ || T('Rules must be a JSON array of {from,to,opt} objects.');
        return $origText . '<hr><b>' . T('Local rule error:') . '</b><br>' . &QuoteHtml($err);
    }

    foreach my $r (@$parsed) {
        next unless ( ref($r) eq 'HASH' && defined( $r->{from} ) && defined( $r->{to} ) );
        my $from = $r->{from};
        my $to   = $r->{to};
        my $opt  = defined( $r->{opt} ) ? $r->{opt} : 'g';
        $opt =~ s/[^gimsx]//g;
        my $global = ( $opt =~ /g/ ) ? 1 : 0;
        ( my $flags = $opt ) =~ s/g//g;

        my $re;
        eval { $re = qr/(?$flags:$from)/; };
        if ( $@ || !defined($re) ) {
            $text .= '<hr><b>' . T('Local rule error:') . '</b><br>' . &QuoteHtml( $@ || $from );
            next;
        }
        if ($global) {
            $text =~ s/$re/&_ExpandBackrefs($to,[$1,$2,$3,$4,$5,$6,$7,$8,$9])/ge;
        } else {
            $text =~ s/$re/&_ExpandBackrefs($to,[$1,$2,$3,$4,$5,$6,$7,$8,$9])/e;
        }
    }
    return $text;
}

# ----------------------------------------------------------------
# HTML output safety. ScrubRawHtml is the XSS guard at the boundary
# between page content and the rendered output. QuoteHtml is the
# inverse — encode `<`, `>`, `&` so user-typed text never looks like
# markup. Both run after the wiki-syntax pipeline so they see what
# is about to be emitted.
# ----------------------------------------------------------------
sub ScrubRawHtml {
    my ($html) = @_;
    if ( !defined $HtmlScrubber ) {
        $HtmlScrubber =
          HTML::Scrubber->new( default => [ 0, { '*' => 0 } ], comment => 0, process => 0 );
        my %attr = (
            class       => 1,
            id          => 1,
            title       => 1,
            alt         => 1,
            name        => 1,
            width       => 1,
            height      => 1,
            align       => 1,
            valign      => 1,
            border      => 1,
            colspan     => 1,
            rowspan     => 1,
            cellpadding => 1,
            cellspacing => 1,
        );
        my @plain = qw(b i u em strong s strike code tt kbd var sub sup
          big small span div p br hr h1 h2 h3 h4 h5 h6
          ul ol li dl dt dd table thead tbody tfoot tr td th
          caption blockquote pre cite q mark abbr acronym
          font center header nav section article aside footer);
        my @rules = map { ( $_ => \%attr ) } @plain;
        push @rules,
          (
            a => {
                href   => qr!^(?:https?:|ftp:|mailto:|/|\#)!i,
                name   => 1,
                class  => 1,
                id     => 1,
                title  => 1,
                target => qr/^_(blank|self|parent|top)$/i,
            },
            img => {
                src    => qr!^(?:https?:|/|\./|data:image/(?:png|jpe?g|gif|webp);base64,)!i,
                alt    => 1,
                class  => 1,
                id     => 1,
                title  => 1,
                name   => 1,
                width  => 1,
                height => 1,
                border => 1,
                align  => 1,
            }
          );
        $HtmlScrubber->rules(@rules);
    }
    return $HtmlScrubber->scrub($html);
}

sub QuoteHtml {
    my ($html) = @_;

    $html =~ s/&/&amp;/g;
    $html =~ s/</&lt;/g;
    $html =~ s/>/&gt;/g;
    $html =~ s/&amp;([#a-zA-Z0-9]+);/&$1;/g;    # Allow character references
    return $html;
}

# ----------------------------------------------------------------
# Phase 2: wiki-syntax pipeline.
#
# WikiToHTML is the top-level entry. It runs in three passes:
#
#   1. Pre-pass: extract <nowiki>/<html> protected regions, apply
#      EarlyRules + per-page ApplyRegExp, expand <variable> tags,
#      embed {(Page)} raw includes.
#   2. Middle pass: HTML-quote, then ParseParagraph -> CommonMarkup
#      + WikiLinesToHtml for the wiki-syntax rules. CommonMarkup
#      handles inline rules (links, quotes, headers, tables); the
#      line-oriented pass builds lists/tables/code blocks.
#   3. Post-pass: TOC substitution, <localtree>, {{Page}} embeds,
#      RestoreSavedText replays the protected regions back in,
#      ApplyRegExp again with the postview namespace.
#
# Page-tree helpers (RestorePageHash, BuildRuleStack, GetLocalTree,
# EmbedWikiPage, EmbedWikiPageRaw, BuildWikiTree, GetVariable,
# GetXMLFields) stay in index.cgi — they reach deep into %Pages
# and the page-id/filesystem layer.
# ----------------------------------------------------------------

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

    # Stage 6: per-page Markdown opt-in. A page whose first line is
    #   <!-- markdown -->
    # gets rendered by Text::Markdown::Discount instead of the wiki
    # rule pipeline. Output is scrubbed through ScrubRawHtml so
    # Markdown's raw-HTML passthrough can't introduce XSS. The marker
    # is per-page; pages without it render exactly as before.
    if ( $pageText =~ s/\A\s*<!--\s*markdown\s*-->\s*\n//i ) {
        my $body = $pageText;
        my $html = eval {
            require Text::Markdown::Discount;
            Text::Markdown::Discount::markdown($body);
        };
        if ( $@ || !defined($html) ) {
            return
                "<div class='wikimsg'>"
              . T('Markdown renderer not available: ')
              . QuoteHtml( $@ // '?' )
              . "</div>";
        }
        return $Pages{$id}->{'page'}{'admin_saved'} ? $html : ScrubRawHtml($html);
    }

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

        # Author-only gate: pages whose current revision was saved by
        # an admin bypass ScrubRawHtml and can carry <script>, AJAX,
        # CORS-using JS, etc. Pages last saved by anyone else stay
        # scrubbed, even if the page was previously trusted, because
        # admin_saved is recaptured at every save.
        if ( $Pages{$id}->{'page'}{'admin_saved'} ) {
            $pageText =~ s/<html>((.|\n)*?)<\/html>/&StoreRaw($1)/ige;
        } else {
            $pageText =~ s/<html>((.|\n)*?)<\/html>/&StoreRaw(&ScrubRawHtml($1))/ige;
        }
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

        if ( defined($EarlyRules) && $EarlyRules ne '' ) {
            $_ = &EvalLocalRules( $EarlyRules, $_, !$useImage );
        }
        s/\[\#(\w+)\]/&StoreHref(" name=\"$1\"")/ge if $NamedAnchors;
        if ($HtmlTags) {
            my ($t);
            foreach $t (@HtmlPairs) {

                # The (\s[^<>]+?)? capture is optional; when absent $1 is
                # undef. Use /e to materialize it as '' rather than emit
                # "Use of uninitialized value" each iteration.
s{\&lt;$t(\s[^<>]+?)?\&gt;(.*?)\&lt;\/$t\&gt;}{"<$t" . (defined($1)?$1:"") . ">$2</$t>"}gise;
            }
            foreach $t (@HtmlSingle) {
                s{\&lt;$t(\s[^<>]+?)?\&gt;}{"<$t" . (defined($1)?$1:"") . ">"}gie;
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

sub ParseParagraph {
    my ($text) = @_;

    $text = &CommonMarkup( $text, 1, 0 );          # Multi-line markup
    $text = &WikiLinesToHtml($text);               # Line-oriented markup
    return "<p>$text</p>\n";
}

# ----------------------------------------------------------------
# Inter-site link helpers. The %InterSite map (loaded once per
# request from $InterFile via GetSiteUrl) translates Site:remote
# tokens into outbound URLs.
# ----------------------------------------------------------------

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
    $punct = '' if ( !defined($punct) );
    $name  = $id;
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

1;
