# JIS替换示例 
github: https://github.com/satan53x/SExtractor/tree/main/document
* 游戏引擎：Alicesoft
* 游戏名：しゃーまんず・さんくちゅあり -巫女の聖域-

# Alicesoft
* 教程1: [【见解】AlicesoftGame汉化破解新手向](https://tieba.baidu.com/p/3220665569?pn=1)
* 教程2: [AliceSoft社System4.3中文化支持简记，以《どらぺこ！体験版》为例](https://ultrapre.github.io/clip/%E6%B1%89%E5%8C%96%E7%A0%B4%E8%A7%A3%E7%A0%94%E8%AE%A8%E5%AE%A4/2019-10-14-1570984627/index.html)
* 工具1: [AliceSoft(ain) 包含AinDecompiler](https://github.com/Inori/FuckGalEngine/tree/master/AliceSoft(ain))
* 工具2: [alice-tools](https://github.com/nunuhara/alice-tools)
* 其他工具： LocaleEmulator, x32dbg, ida, 010Editor
* JIS替换工具：[UIF](https://github.com/AtomCrafty/UniversalInjectorFramework)

# 处理程序
## 确定模块
示例这个游戏使用了`fnl`字库，并且字体切换调用的函数不在exe中，所以需要调试查找函数位置。需要跟踪`CreateFileA`读取fnl文件的位置，并向上跳转。
1. 由于游戏必须要转区启动，所以先设置`LocaleEmulator`配置，勾选`CREATE_SUSPENDED`，运行之后不会弹窗，在`任务管理器`中可以发现已经挂起了进程。
2. 用`x32dbg`附加游戏进程，在符号中找到`CreateFileA`，在kernel模块中打上断点。
3. 在`任务管理器-性能-资源监视器`中恢复挂起的游戏进程，然后一直F9，每次中断都观察中断堆栈的字符串信息，直到出现对应的`fnl`文件后缀为止。（这个游戏其实进入游戏场景才会调用fnl，可以等到开始界面待机后再启用断点，不然之前有几十个文件读取需要跳过）
![1_1](img\1_1.png)
4. 根据堆栈信息可以看出，是`ChipmunkSpriteEngine.dll`在处理字体。用ida反编译这个dll，然后从导入表找到`CreateFileA`，按x进行索引跳转。

## 确定函数
> 这个步骤可以不进行，直接进行[调用系统字体](#调用系统字体)
1. 堆栈中地址是50B6F660，由于基址不同，看后边几位就行，跳转到sub_1000F660。但是sub_1000F660这个函数明显没有字体调用的分支，所以继续往上跳转查看调用。（也可以通过F5查看伪代码确认）
![1_2](img\1_2.png)
2. 上层是sub_1000DE20，前部也没有分支，继续跳转。此时有多处调用，可以配合x32dbg，也可以每个都查看确认。会发现每个调用都有类似的比较结构，也就是参考教程里说的`cmp ..., 0x100`。
![1_4](img\1_4.png)
![1_5](img\1_5.png)
![1_6](img\1_6.png)
![1_7](img\1_7.png)

## 调用系统字体
可以由`CreateFileA`跳转，也可以直接搜索立即数`0x100`。
1. 过滤cmp，找到三处`cmp dword ..., 0x100`，如果不清楚具体需要修改哪个，可以依次尝试。
![1_10](img\1_10.png)
2. 示例游戏是修改第一处。把0x100改为0x200。
![1_11](img\1_11.png)
3. 删除`fnl`文件，游戏能正常显示，且字体有变化，说明修改位置是正确的。

> ### 如果使用GBK编码汉化，则无需进行以下步骤，请按参考教程操作

## 修改字体名
* 示例游戏的字体名也在`ChipmunkSpriteEngine.dll`里。
* 因为用`UIF`无法hook到函数，所以本示例将采用替换ttf字体的方案。
* `010Editor`搜`ＭＳ`(ida之类的也可以用字节搜索)，示例游戏有4个`ＭＳ ゴシック`，修改成你需要的字体名即可。（其实并不需要都修改）

# 处理文本
* `alice-tools`或`AinDecompiler`均可，此处使用`alice-tools`。
* 导出为txt，建议先将控制文本和对话文本分割成多个txt，最后再合成。（或者使用AinDecompiler，原生支持提取成多个txt，但是设置界面的文本只能用legacy单文本方式导出）
* SE提取txt为json，然后翻译。
## 非场景文本
设置界面文本不多，建议手动处理需要的，其他的不要翻译，是utf-8文本保持原样即可。
```
10_search=^;[sm]\[\d+\] = "([^ -~].*?)"$
```
## 场景文本
本游戏的人名可能与控制有关，示例暂不翻译，如果有需要可以自行修改对应脚本或资源名。
```
01_skip=^[^;]
02_skip=^;[^sm]
05_search=^;s\[\d+\] = "(?P<name>.+)"$
10_search=^;m\[\d+\] = "(「.+」)"$
11_search=^;m\[\d+\] = "(（.+）)"$
15_search=^;m\[\d+\] = "　(?P<pre_unfinish>.+)"$
16_search=^;m\[\d+\] = "(.+)(?<=。)"$
20_search=^;m\[\d+\] = "(?P<unfinish>.+)"$
30_skip=^.
structure=paragraph
```
示例正则并不严谨，只是大概方向，跟游戏自身的文本结构有关，请自行修改。（导出jam才能有充足的信息）
## 导入
* 最后用文本编辑器批量把s或m前的;去掉，才能使文本修改有效。
* 导入时选择`生成UniversalInjector的JIS替换配置`，会额外生成一个uif_config。

## JIS替换
> * 原理：通过字典，将json译文中的简体中文替换为合法的日文汉字导入txt（但并不是标准的日繁对应关系），最后通过`UIF`的hook或者ttf/otf字体还原简体。
> * 还原方法1：UIF的`character_substitution`模块hook系统函数。（示例游戏不生效）
> * 还原方法2：使用JIS替换字典对应的ttf字体，通过UIF的`font_manager`模块加载。
> * 还原方法3：直接安装ttf字体。

# 使用JIS替换字体
`tools/font`文件夹下`_msgothic`字体名是`ＭＳ ゴシック`，`_CNJP`是原本字体名。示例使用SimHei黑体，所以需要修改程序的字体名。
* 用`alice-tools`将txt写回ain。此时
![1_20](img\1_20.png)
* [修改字体名](#修改字体名)时修改为SimHei。保持字节不变，长度不足则补00。
![1_21](img\1_21.png)
* 通过UIF的模块加载`simhei_CNJP.ttf`字体。
```
"font_manager": {
    "enable": true,
    "resource_files": [ "simhei_CNJP.ttf" ],
}
```
![1_22](img\1_22.png)
![1_23](img\1_23.png)