# Malie 引擎《タペストリー》文本提取注入工具

本次逆向完成了 Malie 引擎字节码 VM 的完整分析，实现提取注入（方案B：变长+重定位）。
所有环节均通过 byte-exact 验证。

## 文件清单

| 文件 | 作用 |
|---|---|
| `malie_fmt.py` | 格式共享库（EXEC字节码解析/重建/消息token化），提取和注入都依赖它 |
| `malie_text_extract.py` | 提取：字节码 → 对话JSON + 选择肢JSON + meta + 说话人对照表 |
| `malie_text_inject.py` | 注入：译文JSON → 重建字节码（方案B） |
| `malie_selftest.py` | 工具链自测 |
| `malie_exec_crypt.py` | （上环节）EXEC 解密/加密 |
| `malie_exe_tool.py` | （上环节）exe 解封包/封包 |

## 完整工作流

```
① 解包 exe，导出加密的 EXEC 资源
   python malie_exe_tool.py unpack malie.exe unpack_dir

② 解密 EXEC 得到明文字节码
   python malie_exec_crypt.py decrypt unpack_dir/EXEC/EXEC EXEC_decrypted.bin

③ 提取文本（本工具）
   python malie_text_extract.py EXEC_decrypted.bin -o out
   → out/dialogue.json    对话（48793条，译者翻 message 字段）
   → out/choices.json     选择肢+角色名（168条）
   → out/speaker_map.json  说话人对照表（可选人工补全角色名）
   → out/*.meta.json      注入用元数据（勿改）

   【翻译】译者编辑 dialogue.json / choices.json 的 message 字段填中文

④ 注入译文（本工具）
   python malie_text_inject.py EXEC_decrypted.bin \
     -d out/dialogue.json --dialogue-meta out/dialogue.meta.json \
     -c out/choices.json  --choices-meta out/choices.meta.json \
     -o EXEC_new.bin

⑤ 加密回 EXEC
   python malie_exec_crypt.py encrypt EXEC_new.bin unpack_dir/EXEC/EXEC

⑥ 封包回 exe
   python malie_exe_tool.py pack malie.exe unpack_dir malie_cn.exe
```

## JSON 字段说明

### dialogue.json（对话）
- `id`：消息槽索引
- `speaker`：说话人（已确证9个主角映射，其余显示语音前缀如 v_hrm）
- `voice`：原始语音名（如 v_hkr0001）
- `pre_jp`：原文日文（只读参考）
- `message`：**译者在此填中文**

### choices.json（选择肢+角色名）
- `kind`：`choice`选择肢 / `chara`角色名
- `pre_jp`：原文
- `message`：**译者在此填中文**

## 文本处理规则（已按要求实现）
- 停顿符 `[0007][0004]`：自动删除
- 换行 `[000A]`：正文内删除
- 注音（ルビ）`枡(ます)`：提取为 `枡`（去注音留汉字），注入也不带注音
- 语音标记、换页等控制符：存入 meta，注入时无损还原
- 演出效果（渐变/等待/音效）：在代码段作为字节码指令，与文本分离，翻译不影响

## 技术保证
- **空注入 byte-exact**：不改译文时，提取→注入完全还原原文件（SHA一致）
- **变长安全**：译文可任意长短，自动重算段6消息表 + 重定位段4跳转/标签
- **溢出保护**：段3引用偏移超 u16 时，op10 自动升级为 op12（已测2000字符超长串触发827处升级，结构完整）
- **端到端验证**：exe→解密→提取→注入→加密→封包 全链路 byte-exact
