http://www1.chapman.edu/~jipsen/mathml/ASCIIMathML20.js


ASCIIMathML.js
==============
This file contains JavaScript functions to convert ASCII math notation
and LaTeX to Presentation MathML. Simple graphics commands are also
translated to SVG images. The conversion is done while the (X)HTML 
page loads, and should work with Firefox/Mozilla/Netscape 7+ and Internet 
Explorer 6/7 + MathPlayer (http://www.dessci.com/en/products/mathplayer/) +
Adobe SVGview 3.03 (http://www.adobe.com/svg/viewer/install/).

Just add the next line to your (X)HTML page with this file in the same folder:

<script type="text/javascript" src="ASCIIMathML.js"></script>

(using the graphics in IE also requires the file "d.svg" in the same folder).
This is a convenient and inexpensive solution for authoring MathML and SVG.

Version 2.0 Sept 25, 2007, (c) Peter Jipsen http://www.chapman.edu/~jipsen
This version extends ASCIIMathML.js with LaTeXMathML.js and ASCIIsvg.js.
Latest version at http://www.chapman.edu/~jipsen/mathml/ASCIIMathML.js
If you use it on a webpage, please send the URL to jipsen@chapman.edu

The LaTeXMathML modifications were made by Douglas Woodall, June 2006.
(for details see header on the LaTeXMathML part in middle of file)

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation; either version 2.1 of the License, or (at
your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT 
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS 
FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License 
(at http://www.gnu.org/licences/lgpl.html) for more details.

