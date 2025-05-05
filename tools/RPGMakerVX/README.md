## 使用说明
* 脚本会根据文件后缀，决定是从`.rvdata`转换到`.json`，还是还原。
* 预期支持类型：`.rvdata2`（已测试）, `.rvdata`（未测试）, `.rxdata`（未测试）。
* 脚本仅使用rubymarshal进行处理，虽然转换后的json结构上可能和MV略有区别（SE提取的话内容应该是一样的），但因为不针对RPGMaker，兼容性应该比较好，不容易出现转不回去的情况。（缺点可能是不涉及RPGMaker的class的话，有部分bytes数据无法解码，但是这里边一般没有文本，应该不影响用作翻译）

## 引用项目
* [RubyMarshal](https://github.com/d9pouces/RubyMarshal)
