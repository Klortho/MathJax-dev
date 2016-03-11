# -*- Mode: Python; tab-width: 2; indent-tabs-mode:nil; -*-
# vim: set ts=2 et sw=2 tw=80:
#
# Copyright (c) 2013 The MathJax Consortium
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

import sys
from shutil import copyfile
import fontforge
from fontSplitting import FONTSPLITTING, COPYRIGHT
from copy import deepcopy
from math import ceil

def copyPUAGlyphs(aFont, aWeight):
    PUAfont = fontforge.open("X-%s.otf" % aWeight)
    PUAfont.selection.select(("ranges", None), 0xEFFD, 0xEFFF)
    PUAfont.copy()
    aFont.selection.select(("ranges", None), 0xEFFD, 0xEFFF)
    aFont.paste()
    PUAfont.close()

def newFont(aFamily, aFontFrom, aConfig, aName, aWeight):
    print("New font %s-%s..." % (aName, aWeight))

    # Create a copy of the original font, to preserve all the metadata.
    fileName = "%s/otf/%s.%s.tmp" % (aFamily, aName, aWeight)
    copyfile(aFontFrom, fileName)

    # Now open the new font and rename it.
    font = fontforge.open(fileName)

    font.familyname = "%s %s" % (aConfig.FONTFAMILY_PREFIX, aName)
    font.fontname = "%s_%s-%s" % (aConfig.FONTNAME_PREFIX, aName, aWeight)

    font.fullname = font.fontname
    font.encoding = "UnicodeFull"

    # Update the copyright notice.
    font.copyright = "%s\n%s" % (font.copyright, COPYRIGHT);

    # Clear all but the space glyphs.
    font.selection.all()
    font.selection.select(("less", None), 0x20)
    font.selection.select(("less", None), 0xA0)
    font.clear()

    # Copy the three PUA glyphs used to detect Web Fonts availability
    copyPUAGlyphs(font, aWeight)

    return font

def saveFont(aFamily, aFont):
    # Check that the font has more than 6 glyphs before saving it.
    # - the 2 space glyphs (0x20, 0xA0)
    # - the 3 PUA glyphs (0xEFFD, 0xEFFE, 0xEFFF)
    # - the ".notdef" glyph added by sourceforge
    i = 6
    for g in aFont.glyphs():
        i -= 1
        if i == 0:
            break
    if i > 0:
        return

    # Save the new font.
    print("Generating %s..." % aFont.fontname)

    # When we have copied indivual stretchy characters, we may also have
    # copied the associated information from the Open Type Math table.
    # Hence we need to remove that table.
    aFont.math.clear()

    aFont.generate("%s/otf/%s.otf" % (aFamily, aFont.fontname))
    aFont.generate("%s/ttf/%s.ttf" % (aFamily, aFont.fontname))
    aFont.generate("%s/svg/%s.svg" % (aFamily, aFont.fontname))

def hasNonEmptyGlyph(aFont, aGlyphName):
    # Check that the font has the glyph and that this glyph is not empty.
    if not(aGlyphName in aFont and
           aFont[aGlyphName].isWorthOutputting()):
        return False

    return True

def moveGlyph(aFontFrom, aFontTo, aOldPosition, aNewPosition = None):
    # Ignore glyphs that have already been deleted before
    # (Otherwise, FontForge will copy them as "blank" glyphs)
    if not hasNonEmptyGlyph(aFontFrom, aOldPosition):
        return

    # Move the glyph from the font aFontFrom at position aOldPosition
    # to the font aFontTo at position aNewPosition. 
    if aNewPosition is None:
        aNewPosition = aOldPosition
    aFontFrom.selection.select(aOldPosition)
    aFontFrom.cut()
    aFontTo.selection.select(aNewPosition)
    aFontTo.paste()

def moveRange(aFontFrom, aFontTo, aRangeStart, aRangeEnd):
    # Move the glyphs in the range [aRangeStart, aRangeEnd]
    # from the font aFontFrom to the font aFontTo.
    for codePoint in range(aRangeStart, aRangeEnd+1):
        moveGlyph(aFontFrom, aFontTo, codePoint)

def moveSubset(aFontFrom, aFontTo, aSubset):
    for r in aSubset:
        if type(r) == int:
            # Single code point: move one glyph.
            moveGlyph(aFontFrom, aFontTo, r)
        elif type(r) == tuple:
            if type(r[0]) == int:
                # (start, end): move the range of glyphs.
                moveRange(aFontFrom, aFontTo, r[0], r[1])
            elif type(r[0]) == str:
                # (glyphname, newcodepoint): move a non-Unicode glyph
                moveGlyph(aFontFrom, aFontTo, r[0], r[1])

def removeSubset(aFont, aSubset):
    aFont.selection.none()
    for r in aSubset:
        if type(r) == int:
            # Single code point: select one glyph.
            aFont.selection.select(("more",None),r)
        elif type(r) == tuple:
            # (start, end): move the range of glyphs.
            aFont.selection.select(("ranges","more"), r[0], r[1])
    aFont.clear()

def getTestString(aFont, aMaxLength):
    s = ""
    # Pick at most 10 glyphs from the font to build a test string
    i = aMaxLength
    for glyph in aFont.glyphs():
        v = glyph.unicode

        if (0xEFFD <= v and v <= 0xEFFF):
            # Ignore PUA glyphs
            continue

        # ignore some ASCII characters...

        if ((0x80 <= v and v <= 0xD7FF) or
            (0xE000 <= v and v <= 0xFFFF)):
            # BMP character
            s += "\\u%04X" % v
        elif (0x10000 <= v and v <= 0x10FFFF):
            # Surrogate pair
            v -= 0x10000
            trail = 0xD800 + (v >> 10)
            lead = 0xDC00 + (v & 0x3FF)
            s += "\\u%04X\\u%04X" % (trail, lead)
        else:
            continue

        i -= 1
        if i == 0:
            break

    return s

class stretchyOp:
    def __init__(self, aIsHorizontal):
        self.mIsHorizontal = aIsHorizontal
        self.mSizeVariants = None
        self.mComponents = None
        self.mAlias = None

class mathFontSplitter:
    def __init__(self, aFontFamily, aFontDir, aConfig):
        self.mFontFamily = aFontFamily

        self.mDelimiters = aConfig.DELIMITERS
        self.mDelimitersExtra = aConfig.DELIMITERS_EXTRA
        self.mFontSplittingExtra = aConfig.FONTSPLITTING_EXTRA

        # Open the fonts
        self.mMathFont = fontforge.open("%s/%s" % (aFontDir, aConfig.MATHFONT))
        self.mMainFonts = {}
        for key in aConfig.MAINFONTS:
            self.mMainFonts[key] = \
                fontforge.open("%s/%s" % (aFontDir, aConfig.MAINFONTS[key]))

        # Pointer to the PUA to store the horizontal/vertical components
        self.mPUAPointer=0xE000
        self.mPUAContent=dict()

        self.mMovedNonUnicodeGlyphs=dict()

        # Lists of stretchy operators
        self.mStretchyOperators=dict()

        # List of normal size glyphs
        self.mNormalSize=[]

        # Determine the maximum size
        self.mMaxSize = 0
        for glyph in self.mMathFont.glyphs():
            if (glyph.unicode == -1):
                continue

            if (glyph.horizontalVariants is not None):
                variants = glyph.horizontalVariants.split()
            elif (glyph.verticalVariants is not None):
                variants = glyph.verticalVariants.split()
            else:
                continue

            n = len(variants)
            if variants[0] == glyph.glyphname:
                n -= 1 # ignore the normal size variant
            self.mMaxSize = max(self.mMaxSize, n)

        # Create a new font for each size
        self.mMathSize=[]
        for i in range(0, self.mMaxSize):
            self.mMathSize.append(newFont(self.mFontFamily,
                                          "%s/%s" % (aFontDir,
                                                     aConfig.MATHFONT),
                                          aConfig,
                                          "Size%d" % (i+1), "Regular"))
        
    def split(self):
        # Browse the list of all glyphs to find those with stretchy data
        for glyph in self.mMathFont.glyphs():

            if (glyph.unicode == -1):
                continue

            hasVariants = (glyph.horizontalVariants is not None or
                           glyph.verticalVariants is not None)
            hasComponents = (glyph.horizontalComponents is not None or
                             glyph.verticalComponents is not None)

            if (not hasVariants and not hasComponents):
                # skip non-stretchy glyphs
                continue

            if (glyph.unicode in self.mDelimiters):
                item = self.mDelimiters[glyph.unicode]
                if ("redefine" not in item or not(item["redefine"])):
                        raise BaseException("0x%X is already in the list of \
stretchy operators from the Open Type MATH table but is redefined in DELIMITERS. Please use \"redefine\": true to force that or remove this operator from DELIMITERS." % glyph.unicode)
                else:
                    # skip this operator since it is redefined in config.py
                    continue

            if ((glyph.horizontalVariants is not None and
                 glyph.verticalVariants is not None) or
                (glyph.horizontalComponents is not None and
                 glyph.verticalComponents is not None)):
                raise BaseException("Unable to determine direction")
        
            print("%s" % glyph.glyphname)

            # We always use the normal font for the size=0 variant
            self.mNormalSize.append(glyph.unicode)

            isHorizontal = (glyph.horizontalVariants is not None or
                            glyph.horizontalComponents is not None)

            operator = stretchyOp(isHorizontal)

            if hasVariants:
                if isHorizontal:
                    # Copy horizontal size variants
                    operator.mSizeVariants = \
                        self.copySizeVariants(glyph,
                                              glyph.horizontalVariants.split(),
                                              isHorizontal)
                else:
                    # Copy vertical size variants
                    operator.mSizeVariants = \
                        self.copySizeVariants(glyph,
                                              glyph.verticalVariants.split(),
                                              isHorizontal)
            else:
                # Just pass an empty table, the normal size character will
                # be added by copySizeVariants.
                operator.mSizeVariants = \
                    self.copySizeVariants(glyph, [], isHorizontal)

            if hasComponents:
                if isHorizontal:
                    # Copy horizontal components
                    operator.mComponents = \
                        self.copyComponents(glyph.horizontalComponents,
                                            isHorizontal)
                else:
                    # Copy vertical components
                    operator.mComponents = \
                        self.copyComponents(glyph.verticalComponents,
                                            isHorizontal)

            self.mStretchyOperators[glyph.unicode] = operator

        # Add custom operators
        self.addStretchyOperators(self.mDelimiters)

        # Finally, save the new fonts
        for font in self.mMathSize:
            saveFont(self.mFontFamily, font)

    def addStretchyOperators(self, aStretchyOperators):
        # Add some stretchy operators that are not in the Open Type Math table

        for codePoint in aStretchyOperators:

            item = aStretchyOperators[codePoint]
            isHorizontal = (item["dir"] == "H")
            operator = stretchyOp(isHorizontal)

            if "alias" in item:
                # This is an alias
                operator.mAlias = item["alias"]
                self.mStretchyOperators[codePoint] = operator
                continue

            # Size variants
            if "HW" in item:
                i = 0
                operator.mSizeVariants = []
                for c in item["HW"]:
                    if type(c) == int or type(c) == str:
                        data = self.copySizeVariant(isHorizontal, i,
                                                    codePoint, c)
                    else:
                        data = self.copySizeVariant(isHorizontal, i,
                                                    codePoint, c[0], c[1])

                    operator.mSizeVariants.append(data)
                    i += 1
            else:
                raise BaseException("Missing mandatory HW entry for 0x%X" %
                                    codePoint)

            # Components
            if "stretch" in item:
                operator.mComponents = []
                for piece in item["stretch"]:
                    c = piece[0]
                    if type(c) == int or type(c) == str:
                        data = self.copyComponent(c, piece[1])
                    else:
                        data = self.copyComponent(c[0], piece[1], c[1])

                    # add the optional dx,dy,scale,dh,dd parameters
                    if len(piece) > 2:
                        for i in range(2,len(piece)):
                            data.append(piece[i])

                    operator.mComponents.append(data)

            self.mStretchyOperators[codePoint] = operator

    def verifyTeXSizeVariants(self, aTeXFactor, aDelimiters):
        # Ensure that some TeX delimiters have enough variants to provide
        # different sizes for the \big, \bigg... commands.
        for codePoint in aDelimiters:
            if codePoint not in self.mStretchyOperators:
                raise BaseException("0x%X is not in the list of stretchy \
operators. Please add a construction for it in DELIMITERS." %
                                    codePoint)

            # It's an alias, check the reference instead
            if (self.mStretchyOperators[codePoint].mAlias is not None):
                codePoint = self.mStretchyOperators[codePoint].mAlias

            # Target sizes (these values are from the TeX input jax)
            p_height = 1.2/.85
            bigSizes = [0.85,1.15,1.45,1.75]
            for i in range(0,len(bigSizes)):
                bigSizes[i] *= p_height*aTeXFactor

            # These are the available variant sizes
            variantSizes = []
            variants = self.mStretchyOperators[codePoint].mSizeVariants
            for i in range(0,len(variants)):
                em = variants[i][2]
                variantSizes.append(em)

            # See https://groups.google.com/d/msg/mathjax-dev/3mdLfPrG1vg/74WbQnz2aj4J
            # Note that we browse the target/available list in reverse order
            variants2 = []
            while len(bigSizes) > 0:

                # Get the target size
                size = bigSizes.pop()

                if len(variantSizes) == 0:
                    raise BaseException("Not enough variants!")

                if variantSizes[-1] < size:
                    # The current size is not large enough to reach the target
                    # size, so scale it.
                    old=variants[-1]
                    # round to upper values
                    newsize = ceil(1000*size)/1000.
                    newscale = ceil(1000*size/old[2])/1000.
                    variants2.append((old[0],old[1],newsize,newscale))
                    continue

                # Copy the variants that are larger than the target size
                while (len(variantSizes) > 1
                       and variantSizes[-1] >= size):
                    variantSizes.pop()
                    variants2.append(variants.pop())

            # Copy the remaining variants
            while len(variants) > 0:
                variants2.append(variants.pop())

            # Update the variant list for this code point
            variants2.reverse()
            self.mStretchyOperators[codePoint].mSizeVariants = variants2

    def verifyFONTSPLITTING(self):
        for subset in FONTSPLITTING:
            name = subset[0]
            codePoint = None
            for i in range(1, len(subset)):
                r = subset[i]
                if type(r) == int:
                    if (codePoint is not None and codePoint >= r):
                        raise BaseException("Bad entry in FONTSPLITTING>%s: \
0x%X" % (name, r))
                    else:
                        codePoint = r
                else:
                    if (r[1] <= r[0] or
                        (codePoint is not None and codePoint >= r[0])):
                        raise BaseException("Bad entry in FONTSPLITTING>%s: \
(0x%X,0x%X)" % (name, r[0], r[1]))
                    else:
                        codePoint = r[1]

    def computeNormalSizeSplitting(self):
        self.verifyFONTSPLITTING()

        # Determine the name of the font to use for the fontSize variant
        size0 = dict()
        for codePoint in self.mNormalSize:
            if codePoint in size0:
                # Ignore duplicate
                continue

            found = False

            if 0xE000 <= codePoint and codePoint <= 0xF8FF:
                # Try to find the glyph in mFontSplittingExtra
                for name in self.mFontSplittingExtra:
                    for r in self.mFontSplittingExtra[name]:
                        if type(r) == int:
                            if r == codePoint:
                                found = True
                                break
                        elif type(r) == tuple and type(r[0]) == int:
                            if (r[0] <= codePoint and codePoint <= r[1]):
                                found = True
                                break
                        # We ignore (glyphname, newcodepoint)

                    if found:
                        size0[codePoint] = name.upper()
                        break

            if not(found):
                for subset in FONTSPLITTING:
                    name = subset[0]
                    for i in range(1, len(subset)):
                        r = subset[i]
                        if type(r) == int:
                            if r == codePoint:
                                found = True
                                break
                            elif codePoint < r:
                                break
                        else:
                            if (r[0] <= codePoint and codePoint <= r[1]):
                                found = True
                                break
                            elif codePoint < r[0]:
                                break
        
                    if found:
                        size0[codePoint] = name.upper()
                        break

            if not(found):
                size0[codePoint] = "NONUNICODE"

        self.mNormalSize = size0

    def printDelimiters(self, aStream, aMode, aIndent, aExtra = False):
        # Print the delimiters
        if type(self.mNormalSize) != dict:
            self.computeNormalSizeSplitting()

        indent=""
        while aIndent > 0:
            indent += " "
            aIndent -= 1

        isFirst = True
        for key in sorted(self.mStretchyOperators.iterkeys()):

            operator = self.mStretchyOperators[key]

            if operator.mIsHorizontal:
                d = "H"
            else:
                d = "V"

            if aExtra:
                if key not in self.mDelimitersExtra:
                    continue

            if isFirst:
                isFirst = False
            else:
                print(",", file=aStream)

            if not(aExtra) and key in self.mDelimitersExtra:
                print("%s  0x%X: EXTRA%s" % (indent, key, d),
                      file=aStream, end="")
                continue

            if operator.mAlias is not None:
                print("%s  0x%X: {alias: 0x%X, dir: %s}" %
                      (indent, key, operator.mAlias, d), file=aStream, end="")
                continue

            print("%s  0x%X:" % (indent, key), file=aStream)
            print("%s  {" % indent, file=aStream)

            print("%s    dir: %s," % (indent, d), file=aStream)

            # Print the size variants
            print("%s    HW: [" % indent, file=aStream, end="")

            for j in range(0, len(operator.mSizeVariants)):

                if j > 0:
                    print(", ", file=aStream, end="")

                v = operator.mSizeVariants[j]
                codePoint = v[1]
                em = v[2]
                scale = v[3]
                if type(v[0]) == str:
                    style = v[0].upper()
                    if style == "REGULAR":
                        style = ""
                    fontname = "%s%s" % (self.mNormalSize[codePoint],
                                         style)
                else:
                    style = None
                    size = v[0]
                    fontname = "SIZE%d" % size
            
                if aMode == "HTML-CSS":
                    data = "%.3f,%s" % (em, fontname)
                else: # SVG
                    data = "%d,%s" % (em*1000, fontname)

                if scale != 1.0:
                    data += ",%.3f" % scale
                if codePoint != key:
                    if scale == 1.0:
                        data += ",null,0x%X" % codePoint
                    else:
                        data += ",0x%X" % codePoint

                print("[%s]" % data, file=aStream, end="")
                
            print("]", file=aStream, end="");

            if operator.mComponents is None:
                    print(file=aStream)
            else:
                print(",", file=aStream)
                # Print the components
                print("%s    stretch: {" % indent, file=aStream, end="")

                for j in range(0, len(operator.mComponents)):
                    if j > 0:
                        print(", ", file=aStream, end="")
                    v = operator.mComponents[j]
                    codePoint = v[1]
                    pieceType = v[2]
                    if type(v[0]) == str:
                        style = v[0].upper()
                        if style == "REGULAR":
                            style = ""
                        fontname = "%s%s" % (self.mNormalSize[codePoint],
                                             style)
                    else:
                        fontname = "SIZE%d" % v[0]

                    data = "0x%X,%s" % (codePoint, fontname)
                    if len(v) > 3:
                        for i in range(3,len(v)):
                            data += ",%.3f" % v[i]

                    print("%s:[%s]" % (pieceType, data), file=aStream, end="")

                print("}", file=aStream)

            print("%s  }" % indent, file=aStream, end="")
    
        print(file=aStream)

    def isPrivateCharacter(self, aGlyphName):
        if aGlyphName not in self.mMathFont:
            if type(aGlyphName) == int:
                c = "0x%X" % aGlyphName
            else:
                c = aGlyphName
            raise BaseException("No such glyph: %s" % c)

        codePoint = self.mMathFont[aGlyphName].unicode
        return (codePoint == -1 or
                (0xE000 <= codePoint and codePoint <= 0xF8FF) or
                (0xF0000 <= codePoint and codePoint <= 0xFFFFD) or
                (0x100000 <= codePoint and codePoint <= 0x10FFFD))

    def moveToPlane0PUA(self, aGlyphName):

        if aGlyphName not in self.mPUAContent:
            # New piece: copy it into the PUA and save the code point.
            if self.mPUAPointer > 0xF8FF:
                raise BaseException("Too many characters in the Plane 0 PUA. Not supported by the font splitter.")
            codePoint = self.mPUAPointer
            self.mMathFont.selection.select(aGlyphName)
            self.mMathFont.copy()
            self.mMathSize[self.mMaxSize-1].selection.select(codePoint)
            self.mMathSize[self.mMaxSize-1].paste()
            self.mPUAContent[aGlyphName] = codePoint
            self.mPUAPointer += 1 # move to the next code point
            self.mMovedNonUnicodeGlyphs[aGlyphName] = True
        else:
            # This piece was already copied into the PUA:
            # retrieve its code point.
            codePoint = self.mPUAContent[aGlyphName]

        return codePoint

    def copySizeVariant(self, aIsHorizontal, aSize,
                        aCodePoint, aGlyphName, aStyle=None):
        codePoint = aCodePoint

        if aStyle is not None:
            style = aStyle
        elif aSize == 0:
            if self.isPrivateCharacter(aGlyphName):
                print("Warning: non-Unicode glyphs %s used for the normal size! Will be copied to the PUA of Size %d..." % (aGlyphName, self.mMaxSize), file=sys.stderr)
                style = None
                codePoint = self.moveToPlane0PUA(aGlyphName)
                size = self.mMaxSize
            else:
                # This a normal Unicode character
                # We assume that the normal characters from the Math font
                # are the same as those from the Regular font.
                style = "Regular"
        else:
            if  self.isPrivateCharacter(aGlyphName):
                self.mMovedNonUnicodeGlyphs[aGlyphName] = True
            self.mMathFont.selection.select(aGlyphName)
            self.mMathFont.copy()
            self.mMathSize[aSize-1].selection.select(aCodePoint)
            self.mMathSize[aSize-1].paste()
            style = None
            size = aSize

        if style is None:
            boundingBox = self.mMathFont[aGlyphName].boundingBox()
        else:
            boundingBox = self.mMainFonts[style][aGlyphName].boundingBox()
               
        if aIsHorizontal:
            s = float(boundingBox[2] - boundingBox[0])
        else:
            s = float(boundingBox[3] - boundingBox[1])

        if s == 0:
            raise BaseException("Invalid size.")

        if style is None:
            return (size, codePoint, s/self.mMathFont.em, 1.0)
        else:
            codePoint = self.mMainFonts[style][aGlyphName].unicode
            if codePoint == -1:
                raise BaseException("Not supported")
            self.mNormalSize.append(codePoint)
            return (style, codePoint, s/self.mMathFont.em, 1.0)

    def copySizeVariants(self, aGlyph, aSizeVariantTable, aIsHorizontal):
        # Copy the variants of a given glyph into the right Size* font.

        rv = []
        aSizeVariantTable.reverse()

        # Always add the size = 0 (main font) if it is not there.
        if (len(aSizeVariantTable) == 0 or
            aSizeVariantTable[-1] != aGlyph.glyphname):
            aSizeVariantTable.append(aGlyph.glyphname)

        i = 0
        while aSizeVariantTable:
            glyphname = aSizeVariantTable.pop()
            rv.append(self.copySizeVariant(aIsHorizontal, i,
                                           aGlyph.unicode, glyphname))
            i += 1

        return rv

    def copyComponent(self, aGlyphName, aType, aStyle = None):
        # Copy a single component
        if aStyle is not None:
            style = aStyle
        else:
            if self.isPrivateCharacter(aGlyphName):
                style = None
            else:
                # This a normal Unicode character
                # We assume that the normal characters from the Math font
                # are the same as those from the Regular font.
                style = "Regular"

        if style is not None:
            codePoint = self.mMainFonts[style][aGlyphName].unicode
            if codePoint == -1:
                raise BaseException("Not supported")
            self.mNormalSize.append(codePoint)
            return [style, codePoint, aType]

        codePoint = self.moveToPlane0PUA(aGlyphName)
        
        return [self.mMaxSize, codePoint, aType]

    def copyComponents(self, aComponents, aIsHorizontal):
        # Copy the components. The structure of the Open Type Math table is a
        # bit more general than the TeX format, so try to fallback in a
        # reasonable way.
        #
        # Each piece is a table with the following values:
        # 0: glyph name
        # 1: whether it is an extender
        # 2: start overlap
        # 3: end overlap
        # 4: glyph size
        #
        # We will use the two first values. We assume that the pieces are
        # listed from bottom to top (vertical) or from left to right
        # (horizontal).
        #
        if (len(aComponents) == 0):
            raise BaseException("Empty aComponents")

        rv = []

        # Count the number of non extender pieces
        count = 0
        for p in aComponents:
            if p[1] == 0:
                count += 1
        if count > 3:
            raise BaseException("Not supported: too many pieces")

        # Browse the list of pieces

        # 0 = look for a left/bot glyph
        # 1 = look for an extender between left/bot and mid
        # 2 = look for a mid glyph
        # 3 = look for an extender between mid and right/top
        # 4 = look for a right/top glyph
        # 5 = no more piece expected
        state = 0 

        # First extender char found.
        extenderChar = None 

        for p in aComponents:

            if (state == 1 or state == 2) and count < 3:
                # do not try to find a middle glyph
                state += 2

            if p[1] == 1:
                # Extender
                if extenderChar is None:
                    extenderChar = p[0]
                    if aIsHorizontal:
                        rv.append(self.copyComponent(p[0],  "rep"))
                    else:
                        rv.append(self.copyComponent(p[0],  "ext"))
                elif p[0] != extenderChar:
                    raise BaseException("Not supported: different extenders")

                if state == 0: # or state == 1
                    # ignore left/bot piece and multiple successive extenders
                    state = 1
                elif state == 2: # or state == 3
                    # ignore mid piece and multiple successive extenders
                    state = 3
                elif state >= 4:
                    raise BaseException("Not supported: unexpected extender")
            else:
                if state == 0:
                    if aIsHorizontal:
                        rv.append(self.copyComponent(p[0],  "left"))
                    else:
                        rv.append(self.copyComponent(p[0],  "bot"))
                    state = 1
                    continue
                elif state == 1 or state == 2:
                    if aIsHorizontal:
                        rv.append(self.copyComponent(p[0],  "mid"))
                    else:
                        rv.append(self.copyComponent(p[0],  "mid"))
                    state = 3
                    continue
                elif state == 3 or state == 4:
                    if aIsHorizontal:
                        rv.append(self.copyComponent(p[0],  "right"))
                    else:
                        rv.append(self.copyComponent(p[0],  "top"))
                    state = 5
                    continue

        return rv

