## extract_ast
- 用于提取和导入多语言ast，支持ast版本：1.0
- trans文件夹里有对应csv时则会进行导入
- `extract_ast.lua`的文本编码默认为GBK，用于在简中Windows上运行，在其他环境下可能需要自行转编码

### lua
- lua版本: 5.4 
- 依赖lfs
- 依赖Lua-CSV
