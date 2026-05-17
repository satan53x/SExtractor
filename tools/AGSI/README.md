# AGSI SB2 情况 A 文本提取/注入工具

适用范围：只翻译已有正文/选项，不改 CODE 指令流，不新增/删除 CSTR index。

## 模块

- `agsi_sb_tool.py`：结构级解包/封包，`.sb <-> dump_dir`
- `agsi_cstr_codec.py`：`CSTR.bin <-> CSTR_decode.bin` 原始二进制解码/编码
- `agsi_common.py`：文本提取/注入公共模块
- `agsi_extract.py`：从 `CODE.bin + FTBL_1.bin + CSTR_decode.bin` 提取可翻译文本
- `agsi_inject.py`：读取翻译 JSON，只重建 `CSTR_decode.bin / CSTR.bin`

## 完整流程

```bat
python agsi_sb_tool.py unpack majo2.sb dump_majo2 --overwrite
python agsi_cstr_codec.py decode dump_majo2
python agsi_extract.py dump_majo2 majo2_text.json
```

翻译时只改：

```json
"message": "..."
```

不要改：

```json
"scr_msg": "..."
```

注入并封包：

```bat
python agsi_inject.py dump_majo2 majo2_text.json
python agsi_sb_tool.py pack dump_majo2 majo2_chs.sb
```

如果有 `subs_cn_jp.json` 这类单字映射，可用：

```bat
python agsi_inject.py dump_majo2 majo2_text.json --char-map subs_cn_jp.json
```

## JSON 格式

正文例：

```json
{
  "_kind": "message",
  "_api": "Mess$is",
  "_cstr_id": 2659,
  "_code_off": "0x0000ee82",
  "_push_off": "0x0000ee7d",
  "_msg_no": 50056,
  "_voice": "002_A0036",
  "_talk": "ミント",
  "_talk_api": "Talk$s",
  "scr_msg": "原文",
  "message": "译文"
}
```

选项例：

```json
{
  "_kind": "choice",
  "_api": "Cmd1$s",
  "_select_group": 1,
  "_cstr_id": 2660,
  "_code_off": "0x0000ee9b",
  "_push_off": "0x0000ee96",
  "scr_msg": "原文",
  "message": "译文"
}
```

## 提取规则

只提取：

- `Mess$is`
- `MessC$s`
- `Cmd1$s` ~ `Cmd5$s`

不提取：

- `Talk$s / Talk2$s / TalkC$`
- `Voice$s / PlayVoiceC$s`
- `Change$s`
- `Map$ii / MapEnd$`
- `Cg$s / Char$s / Face$s / PlayBgm$s / PlaySe$s` 等资源 API

## 变长注入判断

当前工具只修改 CSTR 内容，保持 CSTR index 数量不变。由于 CODE 里 `PUSH_STR` 保存的是 CSTR index，不是字符串池 offset，所以正文和选项可以变长/变短；工具会重新计算 CSTR 的 offset/size 表。
