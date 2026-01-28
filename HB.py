import os

# ==================== 配置项（可根据需要调整） ====================
# 脚本工作根目录（Ubuntu下固定为/root/iptv）
BASE_DIR = "/root/iptv"
# 要合并的文件列表（按你指定的顺序）
SOURCE_FILES = [
#    "GM.txt",
    "组播_湖北电信.txt",
    "组播_湖南电信.txt",
#    "组播_江西电信.txt",
#    "组播_江苏电信.txt",
#    "组播_重庆联通.txt",
    "组播_上海电信.txt",
    "组播_重庆电信.txt"
]
# 输出文件名（保存到/root/iptv目录下）
OUTPUT_FILE = "HB.txt"
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