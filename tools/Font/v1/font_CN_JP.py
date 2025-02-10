import json
import subprocess
import sys

FontSrc = 'MSGothic_WenQuanYi.ttf' #替换前的字体名
SubsJson = '../../src/subs_cn_jp.json' #替换字典路径
Reverse = True #字典键值交换位置

def main():
    if len(sys.argv) >= 2:
        fnt = sys.argv[1]
    else:
        fnt = FontSrc
    
    obj = json.loads(subprocess.check_output(('otfccdump.exe', '-n', '0', '--hex-cmap', '--no-bom', fnt)))

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
        for key, value in data.items():
            if key == value:
                continue
            s = f'U+{ord(key):04X}'
            j = f'U+{ord(value):04X}'
            try:
                obj['cmap'][s] = obj['cmap'][j]
            except:
                print('字体中不存在:', key, value)
        #更改定义
        #changeDef(obj)
    
    subprocess.run(['otfccbuild.exe', '--keep-average-char-width', '-O3', '-o', '%s_cnjp.ttf' % fnt[0:fnt.rfind('.')]], input=json.dumps(obj), encoding='utf-8')
    print('Done.')


if __name__ == '__main__':
    main()