## 说明
* font_CN_JP.py使用的字典为src下的subs_cn_jp.json。
* 如果游戏不支持修改字体时，字体可进行安装，也可使用UIF的`font_manager`加载（即使函数不能hook也可以加载）。

## 字体
如果游戏不能通过游戏内选择或修改exe更改字体，则需要用FontCreator修正，以替换系统自带字体：
* 字体系：`MS Gothic`
* 字体系：`ＭＳ ゴシック`
* 唯一标识：`Microsoft:ＭＳ ゴシック`
* 匹配规格：`2-11-6-9-7-2-5-8-2-4` `2-2-4-0-0-0-0-0-0-0`

## 文件
* 原字体：`WenQuanYi.ttf`
* 替换后：`WenQuanYi_CNJP.ttf`（WenQuanYi Micro Hei）
* 字体名MS Gothic修正后：`WenQuanYi_msgothic.otf`（ＭＳ ゴシック）

## 工具
otfcc: https://github.com/caryll/otfcc

FontCreator: 非开源