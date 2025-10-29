import json
import pandas
from common import *
from helper_text import *

var = ExVar
filepathOrig = ''
# ------------------------ 处理原文 ------------------------------
def replaceOrig(orig, ctrl):
	if var.engineName in TextConfig['orig_fix']:
		dic = TextConfig['orig_fix'][var.engineName]
		for old, new in dic.items():
			orig = re.sub(old, new, orig)
	if var.dynamicReplace:
		#动态替换
		end = 0
		while True:
			r = var.dynamicReplace.search(orig, pos=end)
			if not r:
				break
			start = r.start()
			end = r.end()
			old = orig[start:end]
			if old in var.dynamicReplaceOldList:
				index = var.dynamicReplaceOldList.index(old)
			else:
				index = len(var.dynamicReplaceOldList)
				var.dynamicReplaceOldList.append(old)
			if index >= len(var.dynamicReplaceNewList):
				#可用元素不足
				continue
			new = var.dynamicReplaceNewList[index]
			orig = orig[:start] + new + orig[end:]
			end = start + len(new)
	if var.transReplace:
		if 'orig_replace' in var.textConf:
			for old, new in var.textConf['orig_replace'].items():
				orig = orig.replace(old, new)
		if 'name' in ctrl and 'name_replace' in var.textConf:
			for old, new in var.textConf['name_replace'].items():
				if orig == old:
					orig = new
	return orig

# --------------------------- 写 ---------------------------------
def getAllOrig(varAllOrig):
	if var.nameMoveUp:
		#名字上移
		allOrig = []
		for i in range(len(varAllOrig)):
			item = {}
			if i < len(varAllOrig)-1 and 'name' in varAllOrig[i+1]:
				item['name'] = varAllOrig[i+1]['name']
			if 'message' in varAllOrig[i]:
				item['message'] = varAllOrig[i]['message']
			if item:
				allOrig.append(item)
		return allOrig
	return varAllOrig
	
# --------------------------- 写 ---------------------------------
class TMP:
	allOrig = None
	transDic = None
	transDicRN = None
def writeFormat(recalc=True):
	if var.isInput and var.dontExportWhenImport:
		return
	fmt = var.curIO.outputFormat
	if fmt < 0:
		return
	if var.ignoreEmptyFile and not var.allOrig:
		return
	if var.textAppend and not var.allOrigAppend:
		#printInfo('没有新增提取')
		return
	if var.textAppend:
		if recalc:
			TMP.allOrig = getAllOrig(var.allOrigAppend)
			TMP.transDic = keepFirstTrans(var.transDicAppend)
			TMP.transDicRN = var.transDicRNAppend
		seq = len(var.appendDirList)
		outputDirpath = os.path.join(var.workpath, var.outputDir, f'append{seq}')
		if not os.path.exists(outputDirpath):
			os.makedirs(outputDirpath)
	else:
		if recalc:
			TMP.allOrig = getAllOrig(var.allOrig)
			TMP.transDic = keepFirstTrans(var.transDic) #value转为单字符串
			TMP.transDicRN = var.transDicRN
		outputDirpath = os.path.join(var.workpath, var.outputDir)
	global filepathOrig
	filepathOrig = os.path.join(outputDirpath, var.curIO.ouputFileName)
	if fmt == 0:
		writeFormatDirect(TMP.transDic)
	elif fmt == 1:
		writeFormatCopyKey(TMP.transDic)
	elif fmt == 2:
		writeFormatDirect(TMP.allOrig)
	elif fmt == 3:
		writeFormatDirect(TMP.transDicRN)
	elif fmt == 4:
		writeFormatCopyKey(TMP.transDicRN)
	elif fmt == 5:
		writeFormatTxt(TMP.transDic)
	elif fmt == 6:
		writeFormatTxtByItem(TMP.allOrig)
	elif fmt == 7:
		writeFormatListByItem(TMP.allOrig)
	elif fmt == 8:
		writeFormatXlsx(TMP.transDic)
	elif fmt == 9:
		writeFormatTxtTwoLineByItem(TMP.allOrig)
	elif fmt == 10:
		writeFormatListCopyKey(TMP.allOrig, True)
	elif fmt == 11:
		writeFormatListCopyKey(TMP.allOrig, False)
	elif fmt == 12:
		writeFormatXlsxListOrigTrans(TMP.allOrig)

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

def writeFormatXlsxListOrigTrans(targetJson):
	printInfo('输出Xlsx:', len(targetJson), var.curIO.ouputFileName)
	data = []
	for item in targetJson:
		name = item['name'] if 'name' in item else ''
		message = item['message'] if 'message' in item else ''
		data.append([name, message, name, message])
	df = pandas.DataFrame(data, columns=['Name', 'Text', 'Trans Name', 'Trans Text'], dtype=str)
	df.to_excel(filepathOrig, index=False, engine='openpyxl')
