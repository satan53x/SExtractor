### Leaf Tools
由`瑜瑜`&`Lite`&`Steins;Gate`提供
* leaf社旧作的各类工具，位图字库重绘，文本反编译，解包封包以及暴力提取截断exe里面的文本
* 用法详见各个脚本运行时的`--help`

#### 二次提取正则示例
```
01_search=WN str8\("(?P<name>.+?)"
10_search=SetMessage2 str16\("<[0-9\\a-zA-Z　:]+　(.+)>"\)
11_search=SetMessage2 str16\("[　]*(.+?)[<>0-9\\a-zA-Z　]+"\)
18_search=SetMessage2 str16\("[　]*(.+)"\)
21_search=AddMessage2 str16\("[　]*(?P<pre_unfinish>.+?)[<>0-9\\a-zA-Z　]+"\)
22_search=AddMessage2 str16\("[　]*(?P<pre_unfinish>.+)"\)
23_search=SetSelectMes str8\("(.+?)"\)
JisEncodeName=shift-jis
```
