-- default codepage : GBK (Windows cp936)

Work_dir = "G:/work5/1"

Cover_name = false
-------------------------------------------------------------
Lang_start = 2 -- dont change

local common = require("common")
local lfs = require("lfs")
local csv = require("csv")
--------------------------------------------------------------
local function file_to_data(file_path)
    local lines = {}
    local index = 1
    print("Read ast: " .. file_path)
    for line in io.lines(file_path) do
        if index == 1 and string.find(line, "astver") then
            index = index - 1
        else
            if index == 1 then
                local s, e = string.find(line, "^ast *= *")
                if s then
                    line = string.sub(line, e + 1)
                end
            end
            table.insert(lines, line)
        end
        index = index + 1
    end
    local str = table.concat(lines, "\n")
    local t = load("return " .. str)()
    return t
end

local function fill_row(row, default)
    if row[Lang_start] == "" then
        row[Lang_start] = default
    end
    -- 填充
    for col_index = Lang_start, #row do
        if row[col_index] == "" then
            row[col_index] = row[Lang_start]
        end
    end
    table.insert(Text_table, row)
    Row_index = Row_index + 1
end

local function get_text()
    local row = Text_table[Row_index]
    Row_index = Row_index + 1
    return row
end
--------------------------------------------------------------
local function item_to_row_text(item)
    -- 名字
    local row = { "name" }
    local has_name = Key_exist(item, "name")
    for lang_index, lang in pairs(Languages) do
        local str = ""
        if has_name and Key_exist(item["name"], lang) then
            str = item["name"][lang]
        end
        table.insert(row, str)
    end
    local default = ""
    if has_name then
        default = item["name"]["name"]
        fill_row(row, default)
    end
    -- 对话
    local row = { "message" }
    for lang_index, lang in pairs(Languages) do
        local str = ""
        if Key_exist(item, lang) then
            for _, text in pairs(item[lang][1]) do
                if type(text) == "table" then
                    -- 控制标签
                    if text[1] == "rt2" or text[1] == "/ruby" then
                        str = str .. "<" .. text[1] .. ">"
                    elseif text[1] == "ruby" then
                        str = str .. "<ruby text=" .. text["text"] .. ">"
                    else
                        print("Error: not support ", text[1])
                    end
                else
                    -- 字符串
                    str = str .. text
                end
            end
        end
        table.insert(row, str)
    end
    fill_row(row, "")
end

local function item_to_row_select(item)
    for seq = 1, #item[Languages[1]] do
        local row = {
            "select",
        }
        for lang_index, lang in pairs(Languages) do
            local str = ""
            if Key_exist(item, lang) then
                str = item[lang][seq]
            end
            table.insert(row, str)
        end
        fill_row(row, "")
    end
end

local function cmd_to_row(item)
    local row = {
        item[1],
    }
    for lang_index, lang in pairs(Languages) do
        local str = ""
        if Key_exist(item, lang) then
            str = item[lang]
        end
        table.insert(row, str)
    end
    fill_row(row, item["text"])
end

--------------------------------------------------------------
local function row_to_item_text(item)
    -- 名字
    local row = get_text()
    local has_name = row[1] == "name"
    if has_name then
        if Cover_name then
            item["name"]["name"] = row[Lang_start]
        end
        for lang_index, lang in pairs(Languages) do
            local str = row[Lang_start + lang_index - 1]
            item["name"][lang] = str
        end
        -- 获取下一个
        row = get_text()
    end
    -- 对话
    for lang_index, lang in pairs(Languages) do
        local str = row[Lang_start + lang_index - 1]
        -- 分割控制文本
        local texts = {}
        local pos = 1
        while pos < #str do
            local s, e = string.find(str, "<[^>]+>", pos)
            if not s then
                break
            end
            table.insert(texts, string.sub(str, pos, s - 1))
            table.insert(texts, string.sub(str, s, e))
            pos = e + 1
        end
        if pos < #str then
            table.insert(texts, string.sub(str, pos))
        end
        -- 生成
        if not Key_exist(item, lang) then
            item[lang] = { {} }
        else
            item[lang][1] = {}
        end
        for _, text in pairs(texts) do
            if string.find(text, "<") then
                local s, e = string.find(text, "<ruby text=")
                if s then
                    text = { "ruby", text = string.sub(text, e+1, #text-1) }
                else
                    text = { string.sub(text, 2, #text-1) }
                end
            end
            table.insert(item[lang][1], text)
        end
    end
end

local function row_to_item_select(item)
    for seq = 1, #item[Languages[1]] do
        local row = get_text()
        for lang_index, lang in pairs(Languages) do
            if not Key_exist(item, lang) then
                item[lang] = {}
            end
            local str = row[Lang_start + lang_index - 1]
            item[lang][seq] = str
        end
    end
end

local function row_to_cmd(item)
    local row = get_text()
    item["text"] = row[Lang_start]
    for lang_index, lang in pairs(Languages) do
        local str = row[Lang_start + lang_index - 1]
        item[lang] = str
    end
end

--------------------------------------------------------------
local function data_to_text(data_root)
    -- 遍历block
    for block_name, block in pairs(data_root) do
        if block_name == "text" then
            -- 文本块
            block = Sort(block)
            for item_index, item in pairs(block) do
                if Key_exist(item, "select") then
                    -- 选项
                    if Import_trans then
                        -- 导入
                        row_to_item_select(item["select"])
                    else
                        -- 提取
                        item_to_row_select(item["select"])
                    end
                else
                    -- 对话
                    if Import_trans then
                        -- 导入
                        row_to_item_text(item)
                    else
                        -- 提取
                        item_to_row_text(item)
                    end
                end
            end
        else
            for cmd_index, cmd in pairs(block) do
                if type(cmd) == "table" and cmd[1] == "savetitle" then
                    -- 标题块
                    if Import_trans then
                        -- 导入
                        row_to_cmd(cmd)
                    else
                        -- 提取
                        cmd_to_row(cmd)
                    end
                end
            end
        end
    end
    return Text_table
end

--------------------------------------------------------------
local function main()
    New_dir = Work_dir .. "/new"
    lfs.mkdir(New_dir)
    Orig_dir = Work_dir .. "/orig"
    lfs.mkdir(Orig_dir)
    Trans_dir = Work_dir .. "/trans"
    lfs.mkdir(Trans_dir)
    -- 获取子文件
    local files = {}
    for filename in lfs.dir(Work_dir) do
        local f = Work_dir .. "/" .. filename
        local attr = lfs.attributes(f)
        if attr.mode == "file" then
            table.insert(files, filename)
        end
    end

    -- 遍历文件
    for _, filename in pairs(files) do
        -- 初始化
        local ast_path = Work_dir .. "/" .. filename
        local trans_path = Trans_dir .. "/" .. filename .. ".csv"
        local attr = lfs.attributes(trans_path)
        if attr and attr.mode == "file" then
            -- 译文读入到data
            Text_table = {}
            local f = csv.open(trans_path)
            print("Read trans: " .. trans_path)
            if f then
                for fields in f:lines() do
                    table.insert(Text_table, fields)
                end
            else
                print("Error: open csv " .. trans_path)
                break
            end
            
            Import_trans = true
        else
            -- 没有译文
            Text_table = {
                { "type" },
            }
            for i, lang in pairs(Languages) do
                table.insert(Text_table[1], lang)
            end
            Import_trans = false
        end
        Row_index = 2 -- 第一行是表头
        -- 读取文件
        local data = file_to_data(ast_path)
        local text_table = data_to_text(data)
        if not Import_trans then
            -- 生成orig
            local orig_path = Orig_dir .. "/" .. filename .. ".csv"
            Export_csv(text_table, orig_path)
            print("Write orig: " .. orig_path)
        end
        -- 生成new
        local str = TableToStr(data)
        local new_path = New_dir .. "/" .. filename
        local f = io.open(new_path, "w")
        if f then
            if Astver > 1 then
                f:write("astver=" .. Astver .. ".0 \n")
            end
            f:write("ast=")
            f:write(str)
            print("Write new: " .. new_path)
        else
            print("Error: open file " .. new_path)
        end
    end

    print("Done.")
end

main()

