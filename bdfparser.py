# Simple BDF to BMP tool in Python
# 
# Copyright (c) 2017 tomchen.org (tomchen.org)
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation self.files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# works for .bdf where every entry has one and only one STARTCHAR, BBX, BITMAP, ENDCHAR, and no empty line inside BITMAP

import re

class BdfParser(object):

	REGEX = (r'(\s*ENCODING\s*(\d+)\s*\n'
	r'(?:.*?\n)*?'
	r'\s*BBX\s*([-\d]+)\s*([-\d]+)\s*([-\d]+)\s*([-\d]+)\s*\n'
	r'(?:.*?\n)*?'
	r'\s*BITMAP\s*\n'
	r'(?:\s*?\n)*?'
	r'((?:\s*\w+\s*\n)*?)'
	r'(?:\s*?\n)*?'
	r'\s*ENDCHAR\s*)')

	def __init__(self, bdfFileName):
		self.file = open(bdfFileName, 'r')
		self.bdfContent = self.file.read()
		fbbResult = re.search(r'^\s*FONTBOUNDINGBOX\s*(?P<fbbw>[-\d]+)\s*(?P<fbbh>[-\d]+)\s*(?P<fbbxoff>[-\d]+)\s*(?P<fbbyoff>[-\d]+)\s*$', self.bdfContent, re.MULTILINE)
		# FONTBOUNDINGBOX FBBw FBBh Xoff Yoff
		self.fbbW         = int(fbbResult.group('fbbw'))
		self.fbbWShadowed = int(fbbResult.group('fbbw')) + 1
		self.fbbWGlowed   = int(fbbResult.group('fbbw')) + 2
		self.fbbH         = int(fbbResult.group('fbbh'))
		self.fbbHShadowed = int(fbbResult.group('fbbh')) + 1
		self.fbbHGlowed   = int(fbbResult.group('fbbh')) + 2
		self.fbbXOff      = int(fbbResult.group('fbbxoff'))
		self.fbbYOff      = int(fbbResult.group('fbbyoff'))
		regexfDwx0 = (r'(.*?\n)*'
		r'\s*ENDPROPERTIES\s*')
		propResult = re.match(regexfDwx0, self.bdfContent, re.MULTILINE)
		fDwx0Result = re.search(r'^\s*DWIDTH\s*(?P<fdwx0>[-\d]+)\s*[-\d]+\s*$', propResult.group(0), re.MULTILINE)
		# DWIDTH fdwx0 0
		if fDwx0Result:
			self.fDwx0 = int(fDwx0Result.group('fdwx0'))
		else:
			self.fDwx0 = self.fbbW
		result = re.findall(self.REGEX, self.bdfContent, re.MULTILINE)
		self.resultDict = {}
		for val in result:
			self.resultDict[int(val[1])] = val

	# hex (string) to 4*n-bit binary (string) then get a 'number'-character substring from left
	def __hex2bin(self, hexStr, number):
		theInt = int(hexStr, 16)
		lenTemp = number % 8
		if lenTemp == 0:
			lenTemp = number
		else:
			lenTemp = number + 8 - lenTemp
		res = format(theInt, '0' + str(lenTemp) + 'b')
		res = res[:number]
		return res

	def __cutOrPad(self, string, margin, isLeft):
		number = len(string) + margin
		if margin == 0:
			return string
		elif margin > 0:
			if isLeft:
				return string.rjust(number, '0')
			else:
				return string.ljust(number, '0')
		else:
			if isLeft:
				return string[-number:]
			else:
				return string[:number]

	def __bytes2string(self, hexStr, number):
		theInt = int(hexStr, 16)
		lenTemp = number % 8
		if lenTemp == 0:
			lenTemp = number
		else:
			lenTemp = number + 8 - lenTemp
		res = format(theInt, '0' + str(lenTemp) + 'b')
		res = res[:number]
		return res

	def getCharBmpByUnicode(self, uCode):
		thisGlyphInfo = self.getGlyphInfo(uCode)
		dwx0   = thisGlyphInfo['dwx0']
		bbW    = thisGlyphInfo['bbW']
		bbH    = thisGlyphInfo['bbH']
		bbXOff = thisGlyphInfo['bbXOff']
		bbYOff = thisGlyphInfo['bbYOff']
		bitmap = thisGlyphInfo['bitmap']
		marginLeft   = bbXOff - self.fbbXOff
		marginBottom = bbYOff - self.fbbYOff
		marginRight  = dwx0 + self.fbbXOff - bbW - bbXOff
		marginTop    = self.fbbH + self.fbbYOff - bbH - bbYOff
		bitmapProd = ''
		if marginTop > 0:
			bitmapProd += ('0' * dwx0 + '\n') * marginTop
		bitmapLineList = bitmap.splitlines()
		bitmapLineListLen = len(bitmapLineList)
		if bitmapLineListLen != bbH:
			print('Warning: The number of lines is not equal to the defined bbH for ' + str(uCode))
		for index, line in enumerate(bitmapLineList):
			if (index >= bbH) or (marginTop < 0 and index < -marginTop) or (marginBottom < 0 and index >= bitmapLineListLen + marginBottom):
				continue
			bitmapProdLine = self.__hex2bin(line, bbW)
			bitmapProdLine = self.__cutOrPad(bitmapProdLine, marginLeft, True)
			bitmapProdLine = self.__cutOrPad(bitmapProdLine, marginRight, False)
			bitmapProd += bitmapProdLine
			bitmapProd += '\n'
		bitmapProd = bitmapProd.rstrip()
		if marginBottom > 0:
			bitmapProd += ('\n' + '0' * dwx0) * marginBottom
		bitmapProd = bitmapProd.lstrip()
		return bitmapProd

	def getShadowedCharBmpByUnicode(self, uCode):
		thisGlyphInfo = self.getGlyphInfo(uCode)
		dwx0 = thisGlyphInfo['dwx0']
		bitmap = self.getCharBmpByUnicode(uCode) + '\n' + '0' * dwx0
		bitmapLineList = bitmap.splitlines()
		# bitmapLineListLen = len(bitmapLineList)
		thisLineTemp = []
		lastLineCharList = []
		for index, thisLine in enumerate(bitmapLineList):
			thisLineTemp = thisLine
			thisLineCharList = list(thisLine + '0')
			if len(lastLineCharList) != 0:
				for i, char in enumerate(lastLineCharList):
					if (char == '1') and (thisLineCharList[i+1] == '0'):
						thisLineCharList[i+1] = '2'
			bitmapLineList[index] = ''.join(thisLineCharList)
			lastLineCharList = list(thisLineTemp)
		return '\n'.join(bitmapLineList)

	def getGlowedCharBmpByUnicode(self, uCode):
		thisGlyphInfo = self.getGlyphInfo(uCode)
		dwx0 = thisGlyphInfo['dwx0']
		bitmap = '0' * dwx0 + '\n' + self.getCharBmpByUnicode(uCode) + '\n' + '0' * dwx0
		bitmapLineList = bitmap.splitlines()
		bitmapLineProdList = []
		bitmapLineListLen = len(bitmapLineList)
		for index, thisLine in enumerate(bitmapLineList):
			thisLineCharList = list(thisLine)
			thisLineCharListLen = len(thisLineCharList)
			if thisLineCharList[0] == '1':
				thisLineCharPrefix = '2'
			else:
				thisLineCharPrefix = '0'
			for i, char in enumerate(thisLineCharList):
				if index > 0:
					lastLineTest = bitmapLineList[index - 1][i] == '1'
				else:
					lastLineTest = False
				if index < bitmapLineListLen - 1:
					nextLineTest = bitmapLineList[index + 1][i] == '1'
				else:
					nextLineTest = False
				if i > 0:
					lastCharTest = thisLineCharList[i - 1] == '1'
				else:
					lastCharTest = False
				if i < thisLineCharListLen - 1:
					nextCharTest = thisLineCharList[i + 1] == '1'
				else:
					nextCharTest = False
				if ((lastLineTest or nextLineTest or lastCharTest or nextCharTest) and (char == '0')):
					thisLineCharList[i] = '2'
			if thisLineCharList[thisLineCharListLen - 1] == '1':
				thisLineCharSuffix = '2'
			else:
				thisLineCharSuffix = '0'
			thisLineCharList.insert(0, thisLineCharPrefix)
			thisLineCharList.append(thisLineCharSuffix)
			bitmapLineProdList.append(''.join(thisLineCharList))
		return '\n'.join(bitmapLineProdList)

	def getCharHexByUnicode(self, uCode):
		return self.getCharHex(self.getCharBmpByUnicode(uCode))

	def getShadowedCharHexByUnicode(self, uCode):
		return self.getCharHex(self.getShadowedCharBmpByUnicode(uCode))

	def getGlowedCharHexByUnicode(self, uCode):
		return self.getCharHex(self.getGlowedCharBmpByUnicode(uCode))

	def getBlackedCharHexByUnicode(self, uCode):
		return self.getBlackedCharHex(self.getCharBmpByUnicode(uCode))

	def getGlyphInfo(self, uCode):
		if uCode in self.resultDict:
			thisResultDictList = self.resultDict[uCode]
			# BBX BBw BBh BBxoff0x BByoff0y
			resultDwx0 = re.search(r'\s*DWIDTH\s*(?P<dwx0>[-\d]+)\s*[-\d]+\s*\n', thisResultDictList[0], re.MULTILINE)
			# DWIDTH dwx0 0
			if resultDwx0:
				dwx0 = resultDwx0.group('dwx0')
			else:
				dwx0 = self.fDwx0
			retDict = {
				'dwx0'    : int(dwx0),
				'bbW'     : int(thisResultDictList[2]),
				'bbH'     : int(thisResultDictList[3]),
				'bbXOff'  : int(thisResultDictList[4]),
				'bbYOff'  : int(thisResultDictList[5]),
				'bitmap'  : thisResultDictList[6].rstrip(),
				'outputW' : int(dwx0),
				'outputH' : self.fbbH,
				'shadowedOutputW' : int(dwx0) + 1,
				'shadowedOutputH' : self.fbbH + 1,
				'glowedOutputW' : int(dwx0) + 2,
				'glowedOutputH' : self.fbbH + 2
			}
			return retDict
		else:
			return None

	# foreground	1	FF
	# shadow	2	01
	# background	0	00
	def getCharHex(self, bmpCode):
		return bytes(bmpCode, 'ascii').replace(b'0', b'\x00').replace(b'1', b'\xff').replace(b'2', b'\x01').replace(b'\n', b'')
		# return bmpCode.replace('0', '00').replace('1', 'ff').replace('2', '01').replace('\n', '')

	def getBlackedCharHex(self, bmpCode):
		return bytes(bmpCode, 'ascii').replace(b'0', b'\x00').replace(b'1', b'\x01').replace(b'\n', b'')
		# return bmpCode.replace('0', '00').replace('1', '01').replace('\n', '')

# test
# bpo = BdfParser('SimSun-14.bdf')
# bpo = BdfParser('FZCKJW-GB1-0-26.bdf')

# print(bpo.getCharBmpByUnicode(30340)) # 的
# print(bpo.getCharHexByUnicode(30340)) # 的
# print(bpo.getCharHexByUnicode(30340).hex()) # 的

# print(bpo.getGlyphInfo(30340))
# print(bpo.getCharBmpByUnicode(65507)) # ￣
# print(bpo.getCharBmpByUnicode(169)) # © -- not exist in some font, not exist in GBK
