#
# Habitat::Render — first cut of the rendering pipeline extracted
# from index.cgi. Phase 1 covers the pure utilities:
#
#   - Link/regex pattern initialisation:  InitLinkPatterns
#   - Field-separator placeholders:       StoreRaw, StorePre, StoreHref,
#                                         StoreUrl, GetBracketUrlIndex,
#                                         RestoreSavedText, RemoveFS
#   - Local-rule pipeline:                ApplyRegExp, ApplyRegExpRules,
#                                         EvalLocalRules, _ExpandBackrefs
#   - HTML output safety:                 ScrubRawHtml, QuoteHtml
#
# Phase 2 (later) will pull in WikiToHTML, CommonMarkup,
# WikiLinesToHtml, ParseParagraph and the inter-page/link helpers.
# Those are tighter coupled to %Pages and the page-tree helpers
# (EmbedWikiPage, BuildWikiTree) which stay in index.cgi.
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

1;
