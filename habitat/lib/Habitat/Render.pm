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
# Local-rule pipeline. Rule pages (.v0/.v1/.e0/.e1) and namespace
# rule files hold regex rewrite rules, either line-oriented (from/to,
# ApplyRegExpRules) or a YAML list (ApplyYamlRules). $EarlyRules /
# $LateRules in the config are a JSON list (EvalLocalRules). The YAML
# and JSON forms share _ApplyRuleList. ApplyRegExp consults
# %$namespace to find which rule set applies to a given page id.
# ----------------------------------------------------------------
sub ApplyRegExp {
    my ( $id, $pageText, $namespace, $pagepath ) = @_;
    my ($name);

    if ( $id =~ /\/\.[^\/]+$/ ) { return $pageText; }

    $id =~ s/(.*)\/__([A-Z0-9]+)__$/"$1\/".GetDynaPageName($1,$2)/geo;

    foreach $name ( keys %$namespace ) {
        if ( $$namespace{$name} ne "" ) {
            if ( $id =~ m/$name/ ) {
                $pageText = &ApplyRuleText( $$namespace{$name}, $pageText );
                last
                  ; # find the first rule match the name pattern, apply the rules, then skip the rest
            }
        }
    }
    if ( defined($pagepath) && ref($pagepath) eq 'ARRAY' && @$pagepath ) {

        # Ancestor rule pages, outermost first. Consecutive line-format
        # pages are joined and run as one rule list, as they always were;
        # a YAML page runs on its own.
        my @lines;
        foreach my $rules (@$pagepath) {
            if ( &IsYamlRules($rules) ) {
                $pageText = &ApplyRegExpRules( join( '', @lines ), $pageText, 0 ) if (@lines);
                @lines    = ();
                $pageText = &ApplyYamlRules( $rules, $pageText );
            } else {
                push( @lines, $rules );
            }
        }
        $pageText = &ApplyRegExpRules( join( '', @lines ), $pageText, 0 ) if (@lines);
    }
    return $pageText;
}

# One rule text, in either page-rule format.
sub ApplyRuleText {
    my ( $rules, $text ) = @_;
    return &IsYamlRules($rules)
      ? &ApplyYamlRules( $rules, $text )
      : &ApplyRegExpRules( $rules, $text, 0 );
}

# A rule page is YAML when its first line that is neither blank nor a
# # comment is "---" or a list item ("- ..."). Line-format rules never
# start that way.
sub IsYamlRules {
    my ($rules) = @_;
    return 0 if ( !defined($rules) );
    foreach my $line ( split( /\r?\n/, $rules ) ) {
        next if ( $line =~ /^\s*(#.*)?$/ );
        return ( $line =~ /^(---\s*$|---\s+#|-\s|-$)/ ) ? 1 : 0;
    }
    return 0;
}

# YAML rule page: a list of steps, applied in order.
#   - from: 'regex'           to: 'text' (\1..\9 / $1..$9)   opt: 'gimsx'
#   - grep: 'regex'           keep only the lines that match
#   - head: N                 keep the first N lines
#   - tail: N                 keep the last N lines
#   - prepend: 'text'         insert text at the start (nothing expanded)
#   - append: 'text'          add text at the end
# Parsed with CPAN::Meta::YAML (core Perl, a YAML subset), never eval'd.
# That parser flattens the indentation of literal blocks and drops
# their blank lines, both of which matter in wiki text, so "key: |"
# blocks are cut out first (_YamlLiftBlocks) and read here with the
# YAML rules: the first line sets the indent, deeper indentation and
# blank lines are kept, "|-" drops the final newline, "|+" keeps all.
sub ApplyYamlRules {
    my ( $rules, $origText ) = @_;
    my $data;
    my ( $yaml, $blocks ) = &_YamlLiftBlocks($rules);
    eval {
        require CPAN::Meta::YAML;
        my $docs = CPAN::Meta::YAML->read_string($yaml);
        $data = [ map { ref($_) eq 'ARRAY' ? @$_ : () } @$docs ];
        die T('Rules must be a YAML list of {from, to, opt} entries.') . "\n"
          if ( !grep { ref($_) eq 'ARRAY' } @$docs );
    };
    if ($@) {
        return $origText . '<hr><b>' . T('Local rule error:') . '</b><br>' . &QuoteHtml($@);
    }
    foreach my $r (@$data) {
        next if ( ref($r) ne 'HASH' );
        foreach my $k ( keys %$r ) {
            $r->{$k} = $blocks->[$1] if ( defined( $r->{$k} ) && $r->{$k} =~ /^__HabitatYamlBlock_(\d+)__$/ );
        }
    }
    return &_ApplyRuleList( $data, $origText, 1 );
}

# Replace each "key: |" literal block by a placeholder scalar; returns
# the new YAML text and the list of block strings.
sub _YamlLiftBlocks {
    my ($yaml) = @_;
    my @in = split( /\r?\n/, $yaml, -1 );
    my ( @out, @blocks );
    for ( my $i = 0 ; $i < @in ; $i++ ) {
        my $line = $in[$i];
        if ( $line !~ /^(\s*(?:-\s+)?)([^\s#'"\-][^:#]*?):\s+\|([1-9]?)([+-]?)([1-9]?)\s*(?:#.*)?$/ ) {
            push( @out, $line );
            next;
        }
        my ( $lead, $key, $chomp ) = ( $1, $2, $4 );
        my $keycol = length($lead);
        my $indent = ( $3 || $5 ) ? $keycol + ( $3 || $5 ) : 0;
        my @body;
        my $j = $i + 1;
        for ( ; $j < @in ; $j++ ) {
            my $l = $in[$j];
            if ( $l =~ /^\s*$/ ) { push( @body, $l ); next; }
            $l =~ /^( *)/;
            my $n = length($1);
            last if ( $n <= $keycol );
            $indent = $n if ( !$indent );
            last if ( $n < $indent );
            push( @body, $l );
        }
        $indent ||= $keycol + 1;
        my @trail;
        unshift( @trail, pop(@body) ) while ( @body && $body[-1] =~ /^\s*$/ );
        my $text = join( "\n", map { length($_) > $indent ? substr( $_, $indent ) : '' } @body );
        if ( $chomp eq '+' ) {
            $text .= "\n" x ( @trail + ( @body ? 1 : 0 ) );
        } elsif ( $chomp ne '-' && @body ) {
            $text .= "\n";
        }
        push( @blocks, $text );
        push( @out, $lead . $key . ": '__HabitatYamlBlock_$#blocks\__'" );
        $i = $j - 1;
    }
    return ( join( "\n", @out ), \@blocks );
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

            # Copy the pattern: each match inside grep() resets $1, and an
            # empty pattern means "the last successful one", so /$1/ kept
            # every line after the first match.
            my $pat = $1;
            @newtext = grep( /(?:$pat)/, split( /\r*\n/, $text ) );
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
                splice( @newtext, 0, @newtext - $1 );    # delete() left empty lines in front
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

    my $parsed;
    require JSON::PP;    # loaded on demand; outside the eval so a missing module is not reported as a rules error
    eval { $parsed = JSON::PP::decode_json($rules); };
    if ( $@ || ref($parsed) ne 'ARRAY' ) {
        my $err = $@ || T('Rules must be a JSON array of {from,to,opt} objects.');
        return $origText . '<hr><b>' . T('Local rule error:') . '</b><br>' . &QuoteHtml($err);
    }

    return &_ApplyRuleList( $parsed, $origText, 0 );
}

# Apply a parsed rule list (JSON config rules or a YAML rule page).
# Steps that are not hashes, or lack from/to and every one of
# grep/head/tail/prepend/append, are skipped. With $pageRule, from ".*" replaces the whole text, as in
# the line format.
sub _ApplyRuleList {
    my ( $list, $text, $pageRule ) = @_;
    foreach my $r (@$list) {
        next if ( ref($r) ne 'HASH' );
        if ( defined( $r->{grep} ) && !ref( $r->{grep} ) ) {
            my $re = eval { qr/$r->{grep}/ };
            if ( !defined($re) ) {
                $text .= '<hr><b>' . T('Local rule error:') . '</b><br>' . &QuoteHtml( $@ || $r->{grep} );
                next;
            }
            $text = join( "\n", grep { /$re/ } split( /\r?\n/, $text ) );
            next;
        }
        if ( defined( $r->{prepend} ) && !ref( $r->{prepend} ) ) {
            $text = $r->{prepend} . $text;
            next;
        }
        if ( defined( $r->{append} ) && !ref( $r->{append} ) ) {
            $text .= $r->{append};
            next;
        }
        if ( defined( $r->{head} ) && $r->{head} =~ /^\d+$/ ) {
            my @l = split( /\r?\n/, $text );
            $text = join( "\n", @l > $r->{head} ? @l[ 0 .. $r->{head} - 1 ] : @l );
            next;
        }
        if ( defined( $r->{tail} ) && $r->{tail} =~ /^\d+$/ ) {
            my @l = split( /\r?\n/, $text );
            $text = join( "\n", @l > $r->{tail} ? @l[ @l - $r->{tail} .. $#l ] : @l );
            next;
        }
        next unless ( defined( $r->{from} ) && defined( $r->{to} ) && !ref( $r->{from} ) && !ref( $r->{to} ) );
        if ( $pageRule && $r->{from} eq '.*' ) {
            $text = &_ExpandBackrefs( $r->{to}, [] );
            next;
        }
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
        require HTML::Scrubber;    # loaded on demand: trusted pages never get here
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
        $StaticCacheOK = 0;    # permission-restricted view
        return "";
    }
    %$SaveUrl         = ();
    %$SaveNumUrl      = ();
    $$SaveUrlIndex    = 0;
    $$SaveNumUrlIndex = 0;

    $pageText = &RemoveFS($pageText);

    # Board posts (Habitat::Board) start with a "<!-- post ... -->"
    # metadata header; it is data, not content.
    $pageText =~ s/\A\s*<!--\s*post\b.*?-->[ \t]*\r?\n?//s if ( $id =~ m{/} && &BoardOf($id) );

    # On an active board, the <board ...> directive line expands to the
    # list of posts (elsewhere it is left as typed).
    my $boardmark = "\x02HABITATBOARD\x02";
    my $hasboard  = 0;
    if ( $pageText =~ /^[ \t]*<board\b/m && &BoardConfig($id) ) {
        if ( $pageText =~ /\A\s*<!--\s*markdown\s*-->/i ) {
            $hasboard = ( $pageText =~ s/^[ \t]*<board\b[^>\n]*>[ \t]*$/$boardmark/m ) ? 1 : 0;
        } else {
            $hasboard = 2;    # after <nowiki> is set aside, below
        }
    }

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
        $html = ScrubRawHtml($html) if ( !$Pages{$id}->{'page'}{'admin_saved'} );
        if ( $hasboard == 1 ) {
            my $idx = &BoardIndexHtml($id);
            $html =~ s/(?:<p>)?\s*\x02?HABITATBOARD\x02?\s*(?:<\/p>)?/$idx/;
        }
        return $html;
    }

    # <nowiki> text is shown as typed: quote it, or HTML typed inside it
    # would reach the page unscrubbed. (Character references survive.)
    $pageText =~ s/<nowiki>((.|\n)*?)<\/nowiki>/&StoreRaw(&QuoteHtml($1))/ige;
    $pageText =~ s/\&lt;nowiki\&gt;((.|\n)*?)\&lt;\/nowiki\&gt;/&StoreRaw($1)/ige;
    if ( $hasboard == 2 ) {
        $pageText =~ s/^[ \t]*<board\b[^>\n]*>[ \t]*$/&StoreRaw(&BoardIndexHtml($id))/me;
    }
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
    # Per-request values: such a page must not go to the static cache.
    $StaticCacheOK = 0 if ( $pageText =~ /&lt;(?:userip|datenow|timenow)&gt;/i );
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
