## 说明
* font_CN_JP.py使用的字典为src下的subs_cn_jp.json。
* 如果游戏不支持修改字体时，字体可进行安装，也可使用UIF的`font_manager`加载（即使函数不能hook也可以加载）。

## 文件v2
* 原字体：`WenQuanYi.ttf`（WenQuanYi / WenQuanYi Micro Hei）
* 用FontCreator修改字体名：`MSGothic_WenQuanYi.ttf`（伪装为：ＭＳ ゴシック）
* 原字体进行JIS替换：`WenQuanYi_cnjp.ttf`（WenQuanYi / WenQuanYi Micro Hei）
* 修改后进行JIS替换：`MSGothic_WenQuanYi_cnjp.ttf`（伪装为：ＭＳ ゴシック）
> 注意：现在只有文件名包含`cnjp`的才是JIS替换字体。

## subs_cn_jp变化
* 因为提前了字体名修正步骤，现在可以自行修改`subs_cn_jp.json`后直接运行`font_CN_JP.py`生成ＭＳ ゴシック字体了。
* 删除即左边中文无法再使用，右边日文则可以正常使用。
#### 2024.06.01
* 删除：`"缳": "瑠"`
* 删除：`"俜": "雫"`
* 删除：`"遹": "畑"`
* 删除：`"崐": "栞"`
* 删除：`"涑": "紬"`

## 工具
* otfcc: https://github.com/caryll/otfcc
* FontCreator: 非开源