# -*- Mode: Python; tab-width: 2; indent-tabs-mode:nil; -*-
# vim: set ts=2 et sw=2 tw=80:
#
# Copyright (c) 2013 MathJax Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import print_function

import argparse
import fontforge
import re
import fontUtil

def copyComponent(aPiece, aType, lastPiece=False):
    # Copy a single component
    global STIXMath, STIXSize
    global STIXPUAPointer, STIXPUAContent
    global fontData, MAXSIZE
    glyphname = aPiece[0]

    if glyphname not in STIXPUAContent:
        # New piece: copy it and save the code point.
        pieceCodePoint = STIXPUAPointer
        STIXPUAContent[glyphname] = pieceCodePoint
        fontUtil.moveGlyph(STIXMath, STIXSize[MAXSIZE],
                           glyphname, pieceCodePoint)
        STIXPUAPointer += 1 # move to the next code point
    else:
        # This piece was already copied: retrieve its code point.
        pieceCodePoint = STIXPUAContent[glyphname]

    print("%s:[0x%X,MATHSIZE%d]" % (aType, pieceCodePoint, MAXSIZE),
          file=fontData, end="")

    if not(lastPiece):
        print(", ", file=fontData, end="")

def cmpPiece(aPiece1, aPiece2):
    # the first component has no start overlap (piece[2] == 0)
    # the last component has no end overlap    (piece[3] == 0)
    if aPiece1[2] == 0 or aPiece2[3] == 0:
        return 1
    if aPiece2[2] == 0 or aPiece1[3] == 0:
        return -1
    return 0

def copyComponents(aComponents, aIsHorizontal):
    # Copy the components. The structure of the Open Type Math table is a bit
    # more general than the TeX format, so try to fallback in a reasonable way.

    # Components seem already sorted in STIX fonts but just in case, sort
    # them a bit according to their overlap values.
    components = sorted(aComponents, cmpPiece)
    if len(components) == 0:
        return

    # Try to get the last component
    p = components.pop()
    if p[1] == 0:
        isLast = (len(components) == 0)
        if aIsHorizontal:
            copyComponent(p,  "left", isLast)
        else:
            copyComponent(p,  "top", isLast)
        if isLast:
            return
        p = components.pop()

    # Try to get the middle component
    if p[1] == 0:
        isLast = (len(components) == 0)
        if aIsHorizontal:
            copyComponent(p,  "rep", isLast)
        else:
            copyComponent(p,  "mid", isLast)
        if isLast:
            return
        p = components.pop()
        hasSecondComponent = True
    else:
        hasSecondComponent = False

    # Try to get the extender component
    if p[1] == 1:
        q = p
        # Ignore multiple extenders
        while (len(components) > 0 and components[0][1] == 1):
            p = components.pop()
        isLast = (len(components) == 0)
        copyComponent(q,  "ext", isLast)
        if isLast:
            return
            
    # Try to get the middle component
    if not(hasSecondComponent) and len(components) > 1:
        if aIsHorizontal:
            copyComponent(p,  "rep", False)
        else:
            copyComponent(p,  "mid", False)
        p = components.pop()

    # Try to get the last component
    if aIsHorizontal:
        copyComponent(p,  "right", True)
    else:
        copyComponent(p,  "bot", True)

def copySizeVariant(aGlyph, aSizeVariantTable):
    # Copy the variants of a given glyph into the right STIX_Size* font.
    global STIXMath, STIXSize, fontData
    for i in range(0,len(aSizeVariantTable)):
        # The variant sizes have a name with an extension, for example
        # uni005C.s2 for the size variant 2 of U+005C. We will choose the
        # destination according to the extension of the glyph name:
        # 
        # No extensions: copy into Size0
        # *.s1 or *.dst: copy into Size1
        # *.s2: copy into Size2
        # *.s3: copy into Size3
        # *.s4: copy into Size4
        # *.s5: copy into Size5
        #
        glyphname = aSizeVariantTable[i]
        sizeMatch = re.search("\.s(\d)$", glyphname)
        if sizeMatch:
            j = int(sizeMatch.group(1))
        elif glyphname.find(".") >= 0:
            j = 1
        else:
            j = 0

        # Ask fontforge to copy the glyph
        fontUtil.moveGlyph(STIXMath, STIXSize[j],
                           aSizeVariantTable[i], aGlyph.unicode)

        if i > 0:
            print(",", file=fontData, end="")
        print("[%.3f,MATHSIZE%d]" % (1.,j), file=fontData, end="")

# Parse the command line arguments
parser = argparse.ArgumentParser()
parser.add_argument('fontdir', type=str)
parser.add_argument('maxsize', type=int, nargs='?', default=5)
args = parser.parse_args()
FONTDIR = args.fontdir
MAXSIZE = args.maxsize

# Open the STIXMath font
STIXMathFile = "%s/STIXMath-Regular.otf" % FONTDIR
STIXMath=fontforge.open(STIXMathFile)

# Create a new font for each size
STIXSize=[]
for i in range(0,MAXSIZE+1):
    font = fontUtil.newFont(STIXMathFile, "Size%d" % i, "Regular")
    STIXSize.append(font)

# Pointer to the PUA to store the horizontal/vertical components
STIXPUAPointer=0xE000
STIXPUAContent=dict()

fontData = open("fontdata.txt", "w")

firstGlyph = True

print("DELIMITERS: {", file=fontData)

# Browse the list of all glyphs in STIXMath to find those with stretchy data.
for glyph in STIXMath.glyphs():

    if (glyph.unicode == -1):
        continue

    hasVariants = (glyph.horizontalVariants is not None or
                   glyph.verticalVariants is not None)
    hasComponents = (glyph.horizontalComponents is not None or
                     glyph.verticalComponents is not None)

    if (not hasVariants and not hasComponents):
        # skip non-stretchy glyphs
        continue
    
    if firstGlyph:
        firstGlyph = False
    else:
        print(",", file=fontData)

    if ((glyph.horizontalVariants is not None and
         glyph.verticalVariants is not None) or
        (glyph.horizontalComponents is not None and
         glyph.verticalComponents is not None)):
        raise BaseException("Unable to determine direction")
        
    isHorizontal = (glyph.horizontalVariants is not None or
                    glyph.horizontalComponents is not None)

    print("%s" % glyph.glyphname)

    print("  0x%X:" % glyph.unicode, file=fontData)
    print("  {", file=fontData)

    if isHorizontal:
        print("    dir: H,", file=fontData)
    else:
        print("    dir: V,", file=fontData)

    if hasVariants:
        print("    HW: [", file=fontData, end="")
        if isHorizontal:
            # Copy horizontal size variants
            copySizeVariant(glyph, glyph.horizontalVariants.split())
        else:
            # Copy vertical size variants
            copySizeVariant(glyph, glyph.verticalVariants.split())
        print("]", file=fontData, end="");
        if hasComponents:
            print(",", file=fontData)
        else:
            print(file=fontData)

    if hasComponents:
        print("    stretch: {", file=fontData, end="")
        if isHorizontal:
            # Copy horizontal components
            copyComponents(glyph.horizontalComponents, isHorizontal)
        else:
            # Copy vertical components
            copyComponents(glyph.verticalComponents, isHorizontal)
        print("}", file=fontData)

    print("  }", file=fontData, end="")


print(file=fontData)
print("} // END DELIMITERS", file=fontData)
fontData.close()

# Finally, save the new fonts
for font in STIXSize:
    fontUtil.saveFont(font)

# Save the remaining characters in a separate font
STIXMath.fontname = "STIX_Math-Regular"
STIXMath.fullname = font.fontname
# TODO: this file is big, do we really need to do that?
# fontUtil.saveFont(STIXMath)
