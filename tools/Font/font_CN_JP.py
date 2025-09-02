# ------------------------------------------------------------
# https://github.com/satan53x/SExtractor/tree/main/tools/Font
# 安装依赖: pip install fonttools
# 会尝试写入多个平台和编码，有部分编码提示不存在是正常现象
# ------------------------------------------------------------
import json
import sys
from fontTools.ttLib import TTFont

FontSrc = 'MSGothic_WenQuanYi.ttf' #替换前的字体名
SubsJson = '../../src/subs_cn_jp.json' #替换字典路径
Reverse = True #字典键值交换位置

def main():
    if len(sys.argv) >= 2:
        fnt = sys.argv[1]
    else:
        fnt = FontSrc
    
    obj = TTFont(fnt)

    with open(SubsJson, encoding='utf-8') as f:
        print('读入Json', SubsJson)
        data:dict = json.load(f)
        #键值互换
        if Reverse:
            newDic = {}
            for key, value in data.items():
                if value in newDic:
                    print('新Key已存在', value)
                else:
                    newDic[value] = key
            data = newDic
        #替换
        for table in obj['cmap'].tables:
            if table.platformID == 1: continue #平台过滤：mac
            for key, value in data.items():
                if key == value:
                    continue
                s = ord(key)
                j = ord(value)
                try:
                    table.cmap[s] = table.cmap[j]
                except:
                    print(f'平台{table.platformID} 编码{table.platEncID} 不存在: {key} {value}')
            #break
        #更改定义
        #changeDef(obj)
    
    newfile = '%s_cnjp.ttf' % fnt[0:fnt.rfind('.')]
    obj.save(newfile)
    print('会尝试写入多个平台和编码，有部分编码提示不存在是正常现象')
    print('生成font:', newfile)

if __name__ == '__main__':
    main()