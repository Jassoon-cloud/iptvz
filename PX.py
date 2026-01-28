import re
import os

def parse_channel_name(channel):
    """解析频道名，返回排序优先级（修复CCTV-5+匹配问题）"""
    # 先提取纯频道名（兼容 "频道名,链接" 格式）
    channel_name = channel.split(",")[0].strip() if "," in channel else channel.strip()
    # 预处理：移除横线，避免CCTV-5无法匹配数字
    channel_name_clean = channel_name.replace("-", "")
    
    match = re.match(r'(CCTV)(\d+)(.*)', channel_name_clean)
    if match:
        prefix = match.group(1)  # CCTV
        number = int(match.group(2))  # 提取数字部分
        suffix = match.group(3)  # 提取后缀部分

        # CCTV频道优先级字典（完全保留原有数值）
        priority_map = {
            1: 1,   # CCTV1
            2: 2,   # CCTV2
            3: 3,   # CCTV3
            4: 4,   # CCTV4
            5: 5,   # CCTV5
            6: 6,   # CCTV6
            7: 7,   # CCTV7
            8: 8,   # CCTV8
            9: 9,   # CCTV9
            10: 10, # CCTV10
            11: 11, # CCTV11
            12: 12, # CCTV12
            13: 13, # CCTV13
            14: 14, # CCTV14
            15: 15, # CCTV15
            16: 16, # CCTV16
        }
        
        # 获取优先级（完全保留原有逻辑）
        priority = priority_map.get(number, 20 + number)
        if number == 5 and '+' in suffix:
            priority = 6  # CCTV5+ 排在CCTV5(5)之后、CCTV6(6)之前
        
        return (priority, number, suffix)

    # 处理非CCTV频道的优先级（完全保留原有逻辑）
    channel_name = channel_name.strip()
    if '湖南卫视' in channel_name:
        return (20, 0, channel)
    elif '北京卫视' in channel_name:
        return (21, 0, channel)
    elif '东方卫视' in channel_name:
        return (22, 0, channel)
    elif '卫视' in channel_name:
        return (23, 0, channel)
    elif 'CHC' in channel_name:
        return (24, 0, channel)
    elif '体育' in channel_name:
        return (25, 0, channel)
    elif any(keyword in channel_name for keyword in ['卡通', '哈哈', '少儿']):
        return (26, 0, channel)
    return (27, 0, channel)

def sort_same_channel_links(channel_links):
    """
    对相同频道名的所有链接排序：
    1. gaoma链接排在第一位
    2. php链接排在第二位
    3. 普通链接（不含指定关键词）排在中间
    4. udp/rtp链接排在最后
    """
    # 初始化不同优先级的链接列表
    gaoma_links = []       # 含gaoma的链接（最高优先级）
    php_links = []         # 含php的链接（次优先级）
    normal_links = []      # 普通链接（无指定关键词）
    udp_rtp_links = []     # 含udp/rtp的链接（最低优先级）

    # 遍历链接，按URL关键词分类
    for link in channel_links:
        # 提取链接部分（兼容"频道名,链接"格式）
        link_parts = link.split(",")
        channel_url = link_parts[-1].strip().lower() if len(link_parts) >= 2 else ""
        
        # 按关键词优先级分类
        if "gaoma" in channel_url:
            gaoma_links.append(link)
        elif "php" in channel_url:
            php_links.append(link)
        elif any(keyword in channel_url for keyword in ["udp", "rtp"]):
            udp_rtp_links.append(link)
        else:
            normal_links.append(link)
    
    # 拼接结果：gaoma → php → 普通 → udp/rtp
    return gaoma_links + php_links + normal_links + udp_rtp_links

def classify_and_sort_channels(channels):
    """分类并排序频道：CCTV组 → 卫视组 → 其他组；同频道名内按关键词优先级排序"""
    # 1. 初始化三个分类列表
    cctv_channels = []    # CCTV频道
    satellite_channels = [] # 卫视频道
    other_channels = []   # 其他频道

    # 2. 拆分频道到不同分类
    for channel in channels:
        channel_name = channel.split(",")[0].strip() if "," in channel else channel.strip()
        
        # 判断分类
        if re.search(r'CCTV', channel_name, re.IGNORECASE):  # 匹配CCTV（不区分大小写）
            cctv_channels.append(channel)
        elif '卫视' in channel_name:  # 匹配含"卫视"的频道
            satellite_channels.append(channel)
        else:  # 其他频道
            other_channels.append(channel)

    # 3. 对每个分类内的频道先按频道名分组，再处理同频道名内的链接排序
    def process_channel_group(channel_group):
        # 按频道名分组：key=频道名，value=该频道名对应的所有链接列表
        channel_name_groups = {}
        for channel in channel_group:
            channel_name = channel.split(",")[0].strip()
            if channel_name not in channel_name_groups:
                channel_name_groups[channel_name] = []
            channel_name_groups[channel_name].append(channel)
        
        # 对频道名进行排序（使用原有parse_channel_name规则）
        sorted_channel_names = sorted(channel_name_groups.keys(), key=lambda name: parse_channel_name(f"{name},dummy_url"))
        
        # 遍历排序后的频道名，对每个频道名的链接按关键词优先级排序
        processed_group = []
        for channel_name in sorted_channel_names:
            # 获取该频道名对应的所有链接
            channel_links = channel_name_groups[channel_name]
            # 按自定义优先级排序链接
            sorted_links = sort_same_channel_links(channel_links)
            # 添加到处理后的分组中
            processed_group.extend(sorted_links)
        
        return processed_group

    # 处理每个分类：先分组，再按关键词优先级排序链接，最后保持频道名原有排序
    cctv_channels_sorted = process_channel_group(cctv_channels)
    satellite_channels_sorted = process_channel_group(satellite_channels)
    other_channels_sorted = process_channel_group(other_channels)

    # 4. 构建最终结果（分类标题 + 处理后的频道）
    final_result = []
    
    # 添加央视频道分类标题 + 处理后的CCTV频道
    if cctv_channels_sorted:
        final_result.append("📺央视频道,#genre#")  # 央视频道分类标题
        final_result.extend(cctv_channels_sorted)  # 添加所有CCTV频道
        final_result.append("")  # 空行分隔分类（可选）
    
    # 添加卫视频道分类标题 + 处理后的卫视频道
    if satellite_channels_sorted:
        final_result.append("📡卫视频道,#genre#")  # 卫视频道分类标题
        final_result.extend(satellite_channels_sorted)  # 添加所有卫视频道
        final_result.append("")  # 空行分隔分类（可选）
    
    # 添加其他频道分类标题 + 处理后的其他频道
    if other_channels_sorted:
        final_result.append("🎬其他频道,#genre#")  # 其他频道分类标题
        final_result.extend(other_channels_sorted)  # 添加所有其他频道

    return final_result

def main():
    # ========== 核心修改：适配仓库根目录iptvz，分离输入/输出目录 ==========
    # 自动获取脚本所在的仓库根目录（iptvz），无需手动修改
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    # 输出目录：仓库根目录下的iptv文件夹（存放最终的TV.txt）
    OUTPUT_DIR = os.path.join(BASE_DIR, "iptv")
    # 输入文件：仓库根目录下的GG.txt（和脚本同目录）
    INPUT_FILE = os.path.join(BASE_DIR, "GG.txt")
    # 输出文件：仓库根目录/iptv/TV.txt（输出到专属文件夹，不污染根目录）
    OUTPUT_FILE = os.path.join(OUTPUT_DIR, "TV.txt")
    # Linux文件权限设置（和HB.py保持一致）
    FILE_MODE = 0o644
    DIR_MODE = 0o755

    # 确保输出目录存在（仓库根目录/iptv），普通用户可创建
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, mode=DIR_MODE)
        print(f"⚠️  输出目录 {OUTPUT_DIR} 不存在，已自动创建")

    # 读取输入文件（仓库根目录的GG.txt，兼容UTF-8/GBK，完善容错提示）
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            # 读取并过滤空行（保留原有逻辑）
            channels = [line.strip() for line in f.readlines()]
        print(f"✅ 成功读取输入文件：{INPUT_FILE}（UTF-8编码）")
    except FileNotFoundError:
        print(f"❌ 错误：未找到输入文件 → {INPUT_FILE}")
        print(f"   请确保GG.txt文件放在【仓库根目录iptvz】下（和本脚本同目录）！")
        return
    except UnicodeDecodeError:
        # 兼容GBK编码（Windows上传文件常见，自动转换处理）
        try:
            with open(INPUT_FILE, 'r', encoding='gbk') as f:
                channels = [line.strip() for line in f.readlines()]
            print(f"⚠️  输入文件 {INPUT_FILE} 为GBK编码，已自动转换为UTF-8处理")
        except Exception as e:
            print(f"❌ 读取文件失败（编码不兼容）：{str(e)}")
            print(f"   建议将GG.txt转换为UTF-8编码后重新上传！")
            return
    except PermissionError:
        print(f"❌ 错误：读取 {INPUT_FILE} 权限不足！")
        print(f"   解决方案：在仓库/服务器执行 → chmod {oct(FILE_MODE)[2:]} {INPUT_FILE}")
        return
    except Exception as e:
        print(f"❌ 读取输入文件失败：{str(e)}")
        return

    # 过滤无效行（空行、N/A,N/A），保留原有逻辑
    original_count = len(channels)
    channels = [channel for channel in channels if channel and channel != "N/A,N/A"]
    filter_count = original_count - len(channels)
    if filter_count > 0:
        print(f"ℹ️  已过滤无效行（空行/N/A,N/A）：{filter_count} 行")

    # 检查是否有有效频道数据
    if not channels:
        print(f"❌ 错误：输入文件 {INPUT_FILE} 中无有效频道数据！")
        return

    # 核心逻辑：分类并排序频道（完全保留原有排序规则，不做任何修改）
    print(f"🚀 开始对 {len(channels)} 条频道数据进行分类排序...")
    final_channels = classify_and_sort_channels(channels)

    # 将排序结果写入输出文件（设置权限，适配普通用户）
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            for line in final_channels:
                f.write(line + '\n')
        # 设置输出文件权限，方便后续读取/使用
        os.chmod(OUTPUT_FILE, FILE_MODE)
        
        # 打印成功结果+详细统计（保留原有统计，优化提示格式）
        print(f"✅ 频道分类排序完成！")
        print(f"=" * 50)
        print(f"📥 输入文件：{INPUT_FILE}（有效数据：{len(channels)} 条）")
        print(f"📤 输出文件：{OUTPUT_FILE}（最终数据：{len(final_channels)} 行）")
        print(f"=" * 50)
        print(f"📊 链接类型统计：")
        gaoma_count = len([c for c in channels if "gaoma" in c.split(",")[-1].lower()])
        php_count = len([c for c in channels if "php" in c.split(",")[-1].lower() and "gaoma" not in c.split(",")[-1].lower()])
        udp_rtp_count = len([c for c in channels if any(k in c.split(",")[-1].lower() for k in ["udp", "rtp"]) and not any(k in c.split(",")[-1].lower() for k in ["gaoma", "php"])])
        print(f"   🔴 Gaoma链接：{gaoma_count} 个")
        print(f"   🟡 PHP链接：{php_count} 个")
        print(f"   🟢 UDP/RTP链接：{udp_rtp_count} 个")
        print(f"=" * 50)
        print(f"📺 频道分类统计：")
        cctv_count = len([c for c in channels if 'CCTV' in c.split(',')[0]])
        satellite_count = len([c for c in channels if '卫视' in c.split(',')[0]])
        other_count = len(channels) - cctv_count - satellite_count
        print(f"   📺 央视频道：{cctv_count} 个")
        print(f"   📡 卫视频道：{satellite_count} 个")
        print(f"   🎬 其他频道：{other_count} 个")
        print(f"=" * 50)
    except PermissionError:
        print(f"❌ 错误：写入 {OUTPUT_FILE} 权限不足！")
        print(f"   解决方案：执行 → chmod {oct(DIR_MODE)[2:]} {OUTPUT_DIR}")
        return
    except Exception as e:
        print(f"❌ 写入输出文件失败：{str(e)}")
        return

if __name__ == '__main__':
    main()
