### ACV1 script.dat unpack/pack tool
由`瑜瑜`提供
* 使用方法详见运行help
* --game-title 可以指定游戏名用于密钥计算

#### 测试游戏
* 真剣で私に恋しなさい！Ａ猟犬ルートアフター
* クロガネ回姫譚-絢爛華麗- DL版
* みなとカーニバルFD

#### 二次提取规则示例
```
01_skip=^\s*[;#/a-zA-Z\*]
11_search=^【(?P<name>.+?)@,.+?】(.+)$
12_search=^【.+?@(?P<name>.+?),.+?】(.+)$
21_search=^【(?P<name>.*?),.+?】(.+)$
22_search=^【(?P<name>.*?)@】(.+?)$
23_search=^【(?P<name>.*?)】(.+?)$
24_search=^【(?P<name>.*?),.+?】$
25_search=^【(?P<name>.*?)】$
42_search=^(.+)$
newline=
```
newline=用于保证输出换行为\n而不是\r\n
