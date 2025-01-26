Astver = 1 -- 目前仅支持1.0版本
Languages = {"ja", "cn"}

local str_pri_list = {
    "lane", "vo", "name", "text", "ja", "cn", "en",
    "crc", "lang",
}

-----------------------------------------------------------
function Key_exist(t, key)
    local i = 1
    for k,v in pairs(t) do
      if k == key then
          return true, i
      end
      i = i + 1
    end
    return false, 0
end

function Index_of(tab, value)
    for i, v in ipairs(tab) do
        if v == value then
            return i
        end
    end
    return 99999
end

local function sort_compare(a, b)
    if type(a) == "number" then
        if type(b) == "number" then
            return a < b
        else
            return true
        end
    else
        if type(b) == "string" then
            local ia = Index_of(str_pri_list, a)
            local ib = Index_of(str_pri_list, b)
            if ia == 99999 and ib == 99999 then
                return a < b
            end
            return ia < ib
        else
            return false
        end
    end
end

function Sort(t)
    local keys = {}
    for key in pairs(t) do
        table.insert(keys, key)
    end
    table.sort(keys)
    local sortedTable = {}
    for _, key in ipairs(keys) do
        sortedTable[key] = t[key]
    end
    return sortedTable
end

function Get_keys(t)
    local keys = {}
    for key in pairs(t) do
        table.insert(keys, key)
    end
    table.sort(keys, sort_compare)
    return keys
end

function Count(t)
    local count = 0
    for k, v in pairs(t) do
        count = count + 1
    end
    return count
end

function Export_csv(data, filepath)
    local file = io.open(filepath, "w")
    if not file then
        print("Error: Unable to open file for writing.")
        return
    end
    for i = 1, #data do
        local row = data[i]
        local colNum = #row
        for j = 1, colNum do
            file:write(tostring(row[j]))
            if j < colNum then
                file:write("\t")
            end
        end
        file:write("\n")
    end
    file:close()
end



--------------------------------------------------------------
Node_path = {}
function ToStringEx(value)
    if type(value)=='table' then
        return TableToStr(value), true
    elseif type(value)=='string' then
        return "\""..value.."\"", false
    else
       return tostring(value), false
    end
end

function TableToStr(t)
    if t == nil then return "" end

    -- 是否显示数字key
    local depth = #Node_path
    local show_num_key = false
    if depth==1 and type(Node_path[depth]) == "string" then
        show_num_key = true
    end

    local has_table_child = false
    local children = {}
    local keys = Get_keys(t)
    for _, key in pairs(keys) do
        local value = t[key]
        table.insert(Node_path, key)
        local child = ""

        local value_str, is_table = ToStringEx(value)
        if is_table then
            has_table_child = true
        end

        if type(key)=='number' then
            if show_num_key then
                child = '['..ToStringEx(key).."]="..value_str
            else
                child = value_str
            end
        else
            child = key.."="..value_str
        end
        table.insert(children, child)

        table.remove(Node_path, #Node_path)
    end

    -- 判断是否需要换行
    local rn = "\n"
    if not has_table_child then
        rn = ""
        if type(Node_path[1]) == "string" then
            if depth == 4 then
                rn = "\n"
            end
        end
    end
    -- 拼接
    local retstr= "{"
    for i, child in pairs(children) do
        retstr = retstr..rn..child
        if i < #children or rn ~= "" then
            retstr = retstr..","
        end
    end
    retstr = retstr..rn.."}"
    return retstr
end