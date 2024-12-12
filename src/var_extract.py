
class IOConfig():
	#输入输出格式: 见engine.ini
	outputFormat = 0
	ouputFileName = ''
	inputFileName = ''
	prefix = ''
	def init(self):
		self.isTxt = self.outputFormat in (5, 6, 9)
		self.isList = self.outputFormat in (2, 6, 7, 9, 10, 11)

class ExtractVar():
	parseImp = None
	replaceOnceImp = None
	readFileDataImp = None
	replaceEndImp = None
	workpath = ''
	window = None
	#导出配置
	io = IOConfig()
	ioExtra = IOConfig()
	curIO:IOConfig = None

	partMode = 0 # 0 单json; 1 多json
	outputDir = 'ctrl'
	inputDir = 'ctrl'

	#-------------------
	transDic = {} #字典的value为字符串list
	transDicIO = {} #读取写入时的原本字典，不参与write()，模式01则不需要
	allOrig = []

	filename = ''
	content = None
	isInput = False #是否写入译文
	isStart = 0 #1-提取第一个文件 2-提取中 3-提取最后一个文件 0-提取结束
	listOrig = [] #原文表
	listCtrl = [] #控制表
	cutoffDic = {}
	textConf = {}
	fullWidthDic = {} #全角转半角字典

	#-------------------
	engineName = ''
	Postfix = '.txt'
	EncodeRead = 'utf-8'
	contentSeparate = None
	fileType = '' #引擎类型
	nameList = []
	regDic = {}
	cutoff = False
	cutoffCopy = False
	noInput = False
	indent = 2 #缩进
	#-------------------
	symbolPattern = '[\\.~ \\u3000-\\u303F\\uFF00-\\uFF65\\u2000-\\u206F\\u2600-\\u27FF]' #重新分割匹配字符
	addSeparate = True
	printSetting = None
	splitAuto = False
	splitParaSep = '\r\n' #段落分割符
	splitParaSepRegex = '\\r\\n' #段落分割符的regex
	ignoreSameLineCount = True #如果行数和原本一致，则忽略
	ignoreNotMaxCount = True #如果所有行都没有超过最大字符，则忽略
	maxCountPerLine = 0
	fixedMaxPerLine = False
	addSpace = '　' #行数补充的空格
	JisEncodeName = 'cp932'
	tunnelJis = False
	subsJis = False
	transReplace = True #译文替换
	preReplace = True #译文分割前替换
	ouputTmp = False #输出中间临时文件
	skipIgnoreCtrl = False #段落：skip不影响ctrl（lastCtrl不会置为None）
	skipIgnoreUnfinish = False #段落：skip不影响unfinish（不会添加predel_unfinish）
	ignoreEmptyFile = True #提取到的内容为空则不导出
	jsonWrite = 1 #dump模式 0-rapidjson.WM_COMPACT 1-rapidjson.WM_PRETTY 10-除了第一层，其它WM_COMPACT
	outputTextType = False #输出文本类型
	dontImportName = False #不导入name
	dontExportWhenImport = False #导入时不导出
	joinAfterSplit = False #分割后再合并为一句
	dontInterrupt = False #单文件异常时不中断
	toFullWidth = False #半角转全角
	nameKeepCtrl = False #name分组保留lastCtrl
	binEncodeValid = False #bin模式下是否应用编码
	useStructPara = False #默认开启struct=para

	#-------------------
	def clear(self):
		self.OldEncodeName = 'cp932'
		self.NewEncodeName = 'gbk'
		self.newline = None
		#
		self.insertContent = {} #需要插入的内容
		self.inputCount = 0 #导出文件个数
		self.outputCount = 0 #导出文件个数
		#各引擎参数
		self.startline = 0 #起始行数
		self.extractKey = ''
		self.structure = ''
		self.extraData = '' #引擎自定义的数据
		self.ignoreDecodeError = False #忽略编码错误
		self.postSkip = None #匹配后置skip，匹配成功则跳过
		self.checkJIS = None #检查JIS，可配置允许的单字符匹配
		self.endStr = None #匹配到则结束
		self.ctrlStr = None #控制段跳过
		self.sepStr = None #分割控制段和文本
		self.version = '0' #版本
		self.decrypt = '' #加解密密钥
		self.pureText = False #bin模式下如果为纯文本，则会先转为utf再进行正则
		self.writeOffset = '0' #写入偏移
		self.keepFormat = True #保持格式
		self.linebreak = '' #标识换行的字符串
		self.nameMoveUp = False #name向上移动
		self.keepBytes = '' #保留字节
		self.padding = '　' #截断填充默认为全角空格,最后有剩余字节再用半角空格补全
		self.twoLineFlag = ['☆', '★'] #双行分割符
		
gExtractVar = ExtractVar()