import os

# ==================== 配置项（可根据需要调整） ====================
# 脚本工作根目录（Ubuntu下固定为/root/iptv）
BASE_DIR = "/root/iptv"
# 要合并的文件列表（按你指定的顺序）
SOURCE_FILES = [
    "GM.txt",
    "DL.txt",
    "MG.txt"
]
# 输出文件名（保存到/root/iptv目录下）
OUTPUT_FILE = "GG.txt"
# 文件编码（确保和原文件一致）
FILE_ENCODING = "utf-8"
# Linux文件权限设置（八进制）
FILE_MODE = 0o644
DIR_MODE = 0o755

def merge_multicast_files():
    """合并指定的组播文件为HB.txt（适配Linux/root/iptv目录）"""
    # 确保工作目录存在
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR, mode=DIR_MODE)
        print(f"⚠️  工作目录 {BASE_DIR} 不存在，已自动创建")
    
    # 存储所有内容（去重）
    all_content = set()
    # 记录处理的文件
    processed_files = []
    # 记录缺失的文件
    missing_files = []

    print("开始合并组播文件...")
    print("=" * 50)
    print(f"🔧 工作目录：{BASE_DIR}")
    print(f"🔧 输出文件：{os.path.join(BASE_DIR, OUTPUT_FILE)}")
    print("=" * 50)

    # 遍历所有源文件（拼接绝对路径）
    for file_name in SOURCE_FILES:
        file_path = os.path.join(BASE_DIR, file_name)
        if os.path.exists(file_path):
            print(f"正在读取：{file_path}")
            try:
                # 读取文件内容（Linux下强制指定编码）
                with open(file_path, "r", encoding=FILE_ENCODING) as f:
                    # 按行读取，过滤空行，去重
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                    for line in lines:
                        all_content.add(line)
                processed_files.append(file_name)
                # 修复文件权限（防止后续访问问题）
                os.chmod(file_path, FILE_MODE)
            except UnicodeDecodeError:
                # 兼容GBK编码（Windows上传的文件）
                try:
                    with open(file_path, "r", encoding="gbk") as f:
                        lines = [line.strip() for line in f.readlines() if line.strip()]
                        for line in lines:
                            all_content.add(line)
                    processed_files.append(file_name)
                    print(f"ℹ️  {file_name} 为GBK编码，已自动转换处理")
                except Exception as e:
                    print(f"❌ 读取{file_path}失败（编码不兼容）：{str(e)}")
            except PermissionError:
                print(f"❌ 读取{file_path}失败：权限不足")
                print(f"   请执行：chmod {oct(FILE_MODE)[2:]} {file_path}")
            except Exception as e:
                print(f"❌ 读取{file_path}失败：{str(e)}")
        else:
            missing_files.append(file_name)
            print(f"⚠️  文件不存在：{file_path}")

    print("=" * 50)

    # 拼接输出文件绝对路径
    output_path = os.path.join(BASE_DIR, OUTPUT_FILE)
    
    # 写入合并后的文件
    if all_content:
        # 转换为列表并排序（保持一致性）
        sorted_content = sorted(all_content)
        try:
            with open(output_path, "w", encoding=FILE_ENCODING) as f:
                # 每行一个内容，保持格式整洁
                f.write("\n".join(sorted_content))
            # 设置输出文件权限
            os.chmod(output_path, FILE_MODE)
            print(f"✅ 合并完成！输出文件：{output_path}")
            print(f"📊 统计信息：")
            print(f"   - 成功处理文件数：{len(processed_files)}")
            print(f"   - 缺失文件数：{len(missing_files)}")
            print(f"   - 合并后总记录数：{len(all_content)}")
            print(f"   - 文件权限：{oct(os.stat(output_path).st_mode)[-3:]}")
        except PermissionError:
            print(f"❌ 写入{output_path}失败：权限不足")
            print(f"   请执行：chmod {oct(DIR_MODE)[2:]} {BASE_DIR}")
        except Exception as e:
            print(f"❌ 写入{output_path}失败：{str(e)}")
    else:
        print("❌ 没有可合并的有效内容！")
        # 创建空文件（确保文件存在）
        try:
            with open(output_path, "w", encoding=FILE_ENCODING) as f:
                f.write("")
            os.chmod(output_path, FILE_MODE)
            print(f"已创建空文件：{output_path}")
        except Exception as e:
            print(f"❌ 创建空文件失败：{str(e)}")

    # 输出缺失文件列表（如果有）
    if missing_files:
        print("\n⚠️  缺失的文件列表：")
        for file in missing_files:
            print(f"   - {os.path.join(BASE_DIR, file)}")

if __name__ == "__main__":
    # 检查是否为root用户（/root目录需要root权限）
    if os.geteuid() != 0 and "root" in BASE_DIR:
        print("⚠️  警告：非root用户运行，可能无法访问/root/iptv目录！")
        print("   建议使用：sudo python3 merge_files.py")
    
    merge_multicast_files()
    print("\n合并任务完成！")
    
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

        # CCTV频道优先级字典（完全保留你的数值）
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
        
        # 获取优先级（完全保留你的逻辑）
        priority = priority_map.get(number, 20 + number)
        if number == 5 and '+' in suffix:
            priority = 6  # CCTV5+ 排在CCTV5(5)之后、CCTV6(6)之前
        
        return (priority, number, suffix)

    # 处理非CCTV频道的优先级（完全保留你的逻辑）
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
    # ========== 核心修改：指定/root/iptv绝对路径 ==========
    # 固定脚本运行的根目录（/root/iptv）
    base_dir = "/root/iptv"
    # 输入文件：/root/iptv/GG.txt
    input_file = os.path.join(base_dir, "GG.txt")
    # 输出文件：/root/iptv/TV.txt
    output_file = os.path.join(base_dir, "TV.txt")

    # Linux下确保目录存在（防止/root/iptv被误删）
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, mode=0o755)
        print(f"⚠️  目录 {base_dir} 不存在，已自动创建")

    # 读取输入文件（Linux下强制UTF-8编码，添加权限/编码容错）
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            channels = [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        print(f"❌ 错误：未找到输入文件 → {input_file}")
        print(f"   请确保GG.txt文件放在 {base_dir} 目录下！")
        return
    except UnicodeDecodeError:
        # 兼容GBK编码（Windows传过来的文件常见）
        try:
            with open(input_file, 'r', encoding='gbk') as f:
                channels = [line.strip() for line in f.readlines()]
            print(f"⚠️  文件 {input_file} 是GBK编码，已自动转换为UTF-8处理")
        except Exception as e:
            print(f"❌ 读取文件失败（编码不兼容）：{str(e)}")
            return
    except PermissionError:
        print(f"❌ 错误：没有读取 {input_file} 的权限！")
        print(f"   请执行：chmod 644 {input_file}")
        return
    except Exception as e:
        print(f"❌ 读取输入文件失败：{str(e)}")
        return

    # 过滤无效行（空行、N/A,N/A）
    channels = [channel for channel in channels if channel and channel != "N/A,N/A"]

    if not channels:
        print(f"⚠️  输入文件 {input_file} 中无有效频道数据")
        return

    # 分类并排序频道
    final_channels = classify_and_sort_channels(channels)

    # 将结果写入输出文件（Linux下设置权限，避免写入失败）
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in final_channels:
                f.write(line + '\n')
        # Linux下设置文件权限（方便后续读取）
        os.chmod(output_file, 0o644)
        
        print(f"✅ 分类排序完成！")
        print(f"📥 输入文件：{input_file}")
        print(f"📤 输出文件：{output_file}")
        
        # 统计输出
        gaoma_count = len([c for c in channels if "gaoma" in c.split(",")[-1].lower()])
        php_count = len([c for c in channels if "php" in c.split(",")[-1].lower() and "gaoma" not in c.split(",")[-1].lower()])
        udp_rtp_count = len([c for c in channels if any(k in c.split(",")[-1].lower() for k in ["udp", "rtp"]) and not any(k in c.split(",")[-1].lower() for k in ["gaoma", "php"])])
        cctv_count = len([c for c in channels if 'CCTV' in c.split(',')[0]])
        satellite_count = len([c for c in channels if '卫视' in c.split(',')[0]])
        other_count = len(channels) - cctv_count - satellite_count
        print(f"📊 统计：")
        print(f"   🔴 含Gaoma的链接数：{gaoma_count} 个")
        print(f"   🟡 含PHP的链接数：{php_count} 个")
        print(f"   🟢 含UDP/RTP的链接数：{udp_rtp_count} 个")
        print(f"   📺 央视频道（CCTV）：{cctv_count} 个")
        print(f"   📡 卫视频道：{satellite_count} 个")
        print(f"   🎬 其他频道：{other_count} 个")
    except PermissionError:
        print(f"❌ 错误：没有写入 {output_file} 的权限！")
        print(f"   请执行：chmod 755 {base_dir}")
        return
    except Exception as e:
        print(f"❌ 写入输出文件失败：{str(e)}")
        return

if __name__ == '__main__':
    main()