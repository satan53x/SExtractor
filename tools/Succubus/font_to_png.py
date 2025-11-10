import os
from PIL import Image, ImageDraw, ImageFont
import math

# --- 用户配置 ---
# 输入和输出文件夹
TXT_FOLDER = 'txt'
OUTPUT_FOLDER = 'new'

# 字体设置
TTF_PATH = "../Font/WenQuanYi_cnjp.ttf" # 请确保字体文件与脚本在同一目录，或提供完整路径
FONT_SIZE = 29 # 字体大小

# 图像布局设置
CHAR_WIDTH = 29  # 单个字符的宽度
CHAR_HEIGHT = 29 # 单个字符的高度
CHARS_PER_LINE = 16 # 每行排列的字符数量

# --- 调色板模式设置 ---
# 将此设置为 True 以启用调色板模式
USE_PALETTE_MODE = True 
# 用于提取调色板的图像路径 (仅在 USE_PALETTE_MODE 为 True 时使用)
# 脚本会自动从该图片加载调色板
PALETTE_IMG_PATH = "原始字库图片/SJIS_1B.png" 

# 颜色设置 (仅在 USE_PALETTE_MODE 为 False 时使用)
BACKGROUND_COLOR = (0, 0, 0) # 背景颜色 (黑)
FILL_COLOR = (255, 255, 255) # 文字颜色 (白)

# 图片格式
IMG_FORMAT = 'PNG'

# --- 全局变量 (请勿修改) ---
img_font: ImageFont = None
palette_data = None
background_color_index = 0
fill_color_index = 1 # 默认值，会被覆盖

# --- 核心功能 ---

def find_closest_color_index(palette, target_color):
    """在调色板中查找最接近目标颜色的颜色索引。"""
    if not palette:
        return 1 # 如果没有调色板，返回默认值
    
    palette_colors = [tuple(palette[i:i+3]) for i in range(0, len(palette), 3)]
    
    min_distance = float('inf')
    closest_index = 0
    
    for i, color in enumerate(palette_colors):
        # 计算欧氏距离的平方
        distance = sum([(c1 - c2) ** 2 for c1, c2 in zip(color, target_color)])
        if distance < min_distance:
            min_distance = distance
            closest_index = i
            
    return closest_index

def initialize():
    """初始化，加载字体、调色板和创建文件夹。"""
    global img_font, palette_data, fill_color_index
    # 检查并创建输入输出文件夹
    if not os.path.exists(TXT_FOLDER):
        os.makedirs(TXT_FOLDER)
        print(f"创建输入文件夹: {TXT_FOLDER}")
        # 创建一个示例txt文件，方便用户使用
        with open(os.path.join(TXT_FOLDER, 'example.txt'), 'w', encoding='utf-8') as f:
            f.write("请在这里输入您想转换成图片的文字。")
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
        print(f"创建输出文件夹: {OUTPUT_FOLDER}")

    # 加载字体
    try:
        img_font = ImageFont.truetype(TTF_PATH, FONT_SIZE)
    except IOError:
        print(f"错误: 无法找到字体文件 '{TTF_PATH}'。请确保字体文件存在于脚本目录中。")
        exit()

    # 如果启用调色板模式，则加载调色板
    if USE_PALETTE_MODE:
        try:
            with Image.open(PALETTE_IMG_PATH) as palette_img:
                # 确保图像是调色板模式
                if palette_img.mode != 'P':
                    print(f"警告: '{PALETTE_IMG_PATH}' 不是调色板模式。将尝试转换为调色板模式。")
                    palette_img = palette_img.convert('P', palette=Image.ADAPTIVE, colors=256)
                
                palette_data = palette_img.getpalette()
                if not palette_data:
                    print(f"错误: 无法从 '{PALETTE_IMG_PATH}' 获取调色板。")
                    exit()
                
                # 查找最接近白色的颜色作为文字颜色
                fill_color_index = find_closest_color_index(palette_data, (255, 255, 255))
                print(f"调色板加载成功。背景色索引: {background_color_index}, 文字颜色索引: {fill_color_index}")

        except FileNotFoundError:
            print(f"错误: 找不到调色板图片 '{PALETTE_IMG_PATH}'。")
            exit()
        except Exception as e:
            print(f"加载调色板时出错: {e}")
            exit()


def draw_text_on_image(text):
    """根据给定的文本绘制一张完整的图片。"""
    # 计算图片尺寸
    total_chars = len(text)
    if total_chars == 0:
        return None
    
    num_rows = math.ceil(total_chars / CHARS_PER_LINE)
    img_width = CHAR_WIDTH * CHARS_PER_LINE
    img_height = CHAR_HEIGHT * num_rows

    # 根据是否使用调色板模式创建图片
    if USE_PALETTE_MODE and palette_data:
        image = Image.new('P', (img_width, img_height), color=background_color_index)
        image.putpalette(palette_data)
        current_fill_color = fill_color_index
    else:
        image = Image.new('RGB', (img_width, img_height), color=BACKGROUND_COLOR)
        current_fill_color = FILL_COLOR

    draw = ImageDraw.Draw(image)

    # 逐行逐字绘制
    for i, char in enumerate(text):
        row = i // CHARS_PER_LINE
        col = i % CHARS_PER_LINE
        
        pos_x = col * CHAR_WIDTH
        pos_y = row * CHAR_HEIGHT
        
        # 为了让字符居中，可能需要微调位置
        # 此处简化为左上角对齐，因为字符和格子大小一致
        draw.text((pos_x, pos_y), char, font=img_font, fill=current_fill_color)
        
    return image

def main():
    """主函数，处理所有txt文件。"""
    initialize()
    
    # 遍历txt文件夹中的所有文件
    txt_files = [f for f in os.listdir(TXT_FOLDER) if f.endswith('.txt')]
    
    if not txt_files:
        print(f"在 '{TXT_FOLDER}' 文件夹中没有找到任何 .txt 文件。")
        return

    for filename in txt_files:
        input_path = os.path.join(TXT_FOLDER, filename)
        
        # 读取txt文件内容
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                content = f.read().replace('\n', '').replace('\r', '') # 移除换行符
            print(f"正在处理: {filename}...")
        except Exception as e:
            print(f"读取文件 {filename} 时出错: {e}")
            continue

        # 绘制图片
        image = draw_text_on_image(content)
        
        # 保存图片
        if image:
            output_filename = f"{os.path.splitext(filename)[0]}.{IMG_FORMAT.lower()}"
            output_path = os.path.join(OUTPUT_FOLDER, output_filename)
            # 如果是调色板模式，需要确保保存时保留调色板
            if USE_PALETTE_MODE and image.mode == 'P':
                image.save(output_path, IMG_FORMAT, palette=palette_data)
            else:
                 image.save(output_path, IMG_FORMAT)
            print(f"成功输出 -> {output_path}")

    print("\n所有文件处理完毕。")

if __name__ == '__main__':
    main()
