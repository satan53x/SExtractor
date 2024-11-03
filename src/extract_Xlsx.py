import re
import pandas as pd
from common import *
from extract_CSV import setValid
from extract_CSV import parseImp as parseImpCSV
from extract_CSV import replaceOnceImp as replaceOnceImpCSV
from io import BytesIO

sheetName = 'sheet1'

# ---------------- Group: CSV/TSV -------------------
def parseImp(content, listCtrl, dealOnce):
	parseImpCSV(content, listCtrl, dealOnce)

# -----------------------------------
def replaceOnceImp(content, lCtrl, lTrans):
	return replaceOnceImpCSV(content, lCtrl, lTrans)

def replaceEndImp(content:pd):
	if ExVar.pureText: return content
	#需要改变外部content
	stream = BytesIO()
	content.to_excel(stream, sheet_name=sheetName, index=False)
	stream.seek(0)
	data = stream.getvalue()
	ExVar.content = [data]

# -----------------------------------
def initXlsx(fileOld):
	global sheetName
	xls = pd.ExcelFile(fileOld)
	sheetName = xls.sheet_names[0]
	fileOld.seek(0)
	if ExVar.extraData == 'nohead':
		content = pd.read_excel(fileOld, header=None)
		contentNames = None
		row = content.iloc[0]
		colMax = len(row)
	else:
		content = pd.read_excel(fileOld)
		contentNames = content.columns.tolist()
		colMax = len(contentNames)
	setValid(contentNames, colMax)
	return content

def readFileDataImp(fileOld, contentSeparate):
	if ExVar.pureText:
		printError('xlsx不支持纯文本模式，请勿勾选')
		return [], {}
	content = initXlsx(fileOld)
	return content, {}


