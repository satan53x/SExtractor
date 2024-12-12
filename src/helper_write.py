import json
import pandas
from common import *
from helper_text import *

var = ExVar
filepathOrig = ''
# --------------------------- 写 ---------------------------------
def getAllOrig():
	if var.nameMoveUp:
		#名字上移
		allOrig = []
		for i in range(len(var.allOrig)):
			item = {}
			if i < len(var.allOrig)-1 and 'name' in var.allOrig[i+1]:
				item['name'] = var.allOrig[i+1]['name']
			if 'message' in var.allOrig[i]:
				item['message'] = var.allOrig[i]['message']
			if item:
				allOrig.append(item)
		return allOrig
	return var.allOrig
	
# --------------------------- 写 ---------------------------------
def writeFormat():
	if var.isInput:
		if var.dontExportWhenImport:
			return
	fmt = var.curIO.outputFormat
	if fmt < 0:
		return
	if var.ignoreEmptyFile:
		if not var.allOrig:
			return
	allOrig = getAllOrig()
	transDic = keepFirstTrans(var.transDic) #value转为单字符串
	global filepathOrig
	filepathOrig = os.path.join(var.workpath, var.outputDir, var.curIO.ouputFileName)
	if fmt == 0:
		writeFormatDirect(transDic)
	elif fmt == 1:
		writeFormatCopyKey(transDic)
	elif fmt == 2:
		writeFormatDirect(allOrig)
	elif fmt == 3:
		writeFormatDirect(var.transDicIO)
	elif fmt == 4:
		writeFormatCopyKey(var.transDicIO)
	elif fmt == 5:
		writeFormatTxt(transDic)
	elif fmt == 6:
		writeFormatTxtByItem(allOrig)
	elif fmt == 7:
		writeFormatListByItem(allOrig)
	elif fmt == 8:
		writeFormatXlsx(transDic)
	elif fmt == 9:
		writeFormatTxtTwoLineByItem(allOrig)
	elif fmt == 10:
		writeFormatListCopyKey(allOrig, True)
	elif fmt == 11:
		writeFormatListCopyKey(allOrig, False)

def writeFormatDirect(targetJson):
	printInfo('输出Json:', len(targetJson), var.curIO.ouputFileName)
	fileOutput = open(filepathOrig, 'w', encoding='utf-8')
	json.dump(targetJson, fileOutput, ensure_ascii=False, indent=2)
	fileOutput.close()

def writeFormatCopyKey(targetJson):
	printInfo('输出Json:', len(targetJson), var.curIO.ouputFileName)
	fileOutput = open(filepathOrig, 'w', encoding='utf-8')
	tmpDic = {}
	for orig,trans in targetJson.items():
		if trans == '':
			tmpDic[orig] = orig
		else:
			tmpDic[orig] = trans
	json.dump(tmpDic, fileOutput, ensure_ascii=False, indent=2)
	fileOutput.close()

def writeFormatTxt(targetJson):
	printInfo('输出Txt:', len(targetJson), var.curIO.ouputFileName)
	fileOutput = open(filepathOrig, 'w', encoding='utf-8')
	for orig in targetJson.keys():
		fileOutput.write(orig + '\n')
	fileOutput.close()

def writeFormatTxtByItem(targetJson):
	printInfo('输出Txt:', len(targetJson), var.curIO.ouputFileName)
	fileOutput = open(filepathOrig, 'w', encoding='utf-8')
	for item in targetJson:
		if 'name' in item:
			fileOutput.write(item['name'] + '\n')
		if 'message' in item:
			fileOutput.write(item['message'] + '\n')
	fileOutput.close()

def writeFormatListByItem(targetJson):
	printInfo('输出Json:', len(targetJson), var.curIO.ouputFileName)
	fileOutput = open(filepathOrig, 'w', encoding='utf-8')
	tmpList = []
	for item in targetJson:
		if 'name' in item:
			tmpList.append(item['name'])
		if 'message' in item:
			tmpList.append(item['message'])
	json.dump(tmpList, fileOutput, ensure_ascii=False, indent=2)
	fileOutput.close()

def writeFormatXlsx(targetJson):
	printInfo('输出Xlsx:', len(targetJson), var.curIO.ouputFileName)
	df = pandas.DataFrame(list(targetJson.items()), columns=['Key', 'Value'], dtype=str)
	df.to_excel(filepathOrig, index=False, engine='openpyxl')
	
def writeFormatTxtTwoLine(targetJson):
	printInfo('输出Txt:', len(targetJson), var.curIO.ouputFileName)
	fileOutput = open(filepathOrig, 'w', encoding='utf-8')
	for i, orig in enumerate(targetJson.keys()):
		id = i + 1
		fileOutput.write(f'{var.twoLineFlag[0]}{id:06d}{var.twoLineFlag[0]}{orig}' + '\n')
		fileOutput.write(f'{var.twoLineFlag[1]}{id:06d}{var.twoLineFlag[1]}{orig}' + '\n')
		fileOutput.write('\n')
	fileOutput.close()

def writeFormatTxtTwoLineByItem(targetJson):
	sep = ExVar.splitParaSep
	sepRegex = ExVar.splitParaSepRegex
	printInfo('输出Txt:', len(targetJson), var.curIO.ouputFileName)
	fileOutput = open(filepathOrig, 'w', encoding='utf-8')
	for i, item in enumerate(targetJson):
		id = i + 1
		list1 = [f'{var.twoLineFlag[0]}{id:06d}{var.twoLineFlag[0]}']
		list2 = [f'{var.twoLineFlag[1]}{id:06d}{var.twoLineFlag[1]}']
		if 'name' in item:
			list1.extend([item['name'], var.twoLineFlag[0]])
			list2.extend([item['name'], var.twoLineFlag[1]])
		if 'message' in item:
			if sep != sepRegex:
				orig = item['message'].replace(sep, sepRegex)
			else:
				orig = item['message']
			list1.extend([orig, '\n'])
			list2.extend([orig, '\n'])
		list2.append('\n')
		text = ''.join(list1 + list2)
		fileOutput.write(text)
	fileOutput.close()

#mergeName 是否合并name到message相同的dic
def writeFormatListCopyKey(targetJson, mergeName):
	printInfo('输出Json:', len(targetJson), var.curIO.ouputFileName)
	fileOutput = open(filepathOrig, 'w', encoding='utf-8')
	tmpList = []
	for item in targetJson:
		if not mergeName:
			if 'name' in item:
				tmpList.append({item['name']:item['name']})
			if 'message' in item:
				tmpList.append({item['message']:item['message']})
		else:
			newItem = {}
			if 'name' in item:
				newItem[item['name']] = item['name']
			if 'message' in item:
				newItem[item['message']] = item['message']
			tmpList.append(newItem)
	json.dump(tmpList, fileOutput, ensure_ascii=False, indent=2)
	fileOutput.close()