### tool
由`Steins;Gate`提供
* 用于04年旧版

#### 测试游戏
* フォーチュンクッキーセレクト

#### 正则参考
```
00_skip=TEXT [\t　  ]+$
20_search=VOICE_NAME_TEXT[\t　 0-9a-zA-Z]+,(?P<name>.+?),(.+)
21_search=VOICE_TEXT[\t　 0-9a-zA-Z]+,[　]*(.+)
22_search=NAME_TEXT[\t　 0-9a-zA-Z]+(?P<name>.+?),[　]*(.+)
31_search=TEXT [\t　  ]*(.+)
```