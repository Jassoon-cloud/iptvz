import os

# ==================== 配置项（适配仓库根目录iptvz，源文件同目录，输出到iptv文件夹） ====================
# 脚本工作根目录（仓库根目录，HB.py所在的目录，即iptvz）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 自动获取脚本所在的仓库根目录，无需手动改
# 要合并的文件列表（直接放在仓库根目录的源文件）
SOURCE_FILES = [
    # "GM.txt",
    "组播_湖北电信.txt",
    "组播_湖南电信.txt",
    # "组播_江西电信.txt",
    # "组播_江苏电信.txt",
    # "组播_重庆联通.txt",
    "组播_上海电信.txt",
    "组播_重庆电信.txt"
]
# 输出文件目录（仓库根目录下的iptv文件夹，存放最终的HB.txt）
OUTPUT_DIR = os.path.join(BASE_DIR, "iptv")
# 输出文件名
OUTPUT_FILE = "HB.txt"
# 文件编码（确保和原文件一致）
FILE_ENCODING = "utf-8"
# Linux文件权限设置（八进制）
FILE_MODE = 0o644
DIR_MODE = 0o755

def merge_multicast_files():
    """合并仓库根目录的组播文件，输出到./iptv/HB.txt（适配仓库结构，无权限问题）"""
    # 确保输出目录存在（仓库根目录/iptv）
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, mode=DIR_MODE)
        print(f"⚠️  输出目录 {OUTPUT_DIR} 不存在，已自动创建")
    
    # 存储所有内容（去重）
    all_content = set()
    # 记录处理的文件
    processed_files = []
    # 记录缺失的文件
    missing_files = []

    print("开始合并组播文件...")
    print("=" * 50)
    print(f"🔧 源文件目录：{BASE_DIR}（仓库根目录）")
    print(f"🔧 输出文件：{os.path.join(OUTPUT_DIR, OUTPUT_FILE)}")
    print("=" * 50)

    # 遍历所有源文件（读取仓库根目录的文件）
    for file_name in SOURCE_FILES:
        file_path = os.path.join(BASE_DIR, file_name)  # 源文件路径=仓库根目录+文件名
        if os.path.exists(file_path):
            print(f"正在读取：{file_path}")
            try:
                # 读取文件内容（指定编码，兼容utf-8/GBK）
                with open(file_path, "r", encoding=FILE_ENCODING) as f:
                    # 按行读取，过滤空行，自动去重
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                    all_content.update(lines)  # 等价于循环add，更高效
                processed_files.append(file_name)
                os.chmod(file_path, FILE_MODE)  # 修复源文件权限
            except UnicodeDecodeError:
                # 自动兼容GBK编码（Windows上传的文件大概率是GBK）
                try:
                    with open(file_path, "r", encoding="gbk") as f:
                        lines = [line.strip() for line in f.readlines() if line.strip()]
                        all_content.update(lines)
                    processed_files.append(file_name)
                    print(f"ℹ️  {file_name} 为GBK编码，已自动转换为UTF-8处理")
                except Exception as e:
                    print(f"❌ 读取{file_path}失败（编码不兼容）：{str(e)}")
            except PermissionError:
                print(f"❌ 读取{file_path}失败：权限不足")
                print(f"   解决方案：执行 chmod {oct(FILE_MODE)[2:]} {file_path}")
            except Exception as e:
                print(f"❌ 读取{file_path}失败：{str(e)}")
        else:
            missing_files.append(file_name)
            print(f"⚠️  文件不存在：{file_path}（请检查是否放在仓库根目录）")

    print("=" * 50)

    # 输出文件的完整路径（仓库根目录/iptv/HB.txt）
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    
    # 写入合并后的内容
    if all_content:
        sorted_content = sorted(all_content)  # 排序保持内容一致性
        try:
            with open(output_path, "w", encoding=FILE_ENCODING) as f:
                f.write("\n".join(sorted_content))
            os.chmod(output_path, FILE_MODE)
            # 打印成功统计信息
            print(f"✅ 合并完成！最终输出：{output_path}")
            print(f"📊 合并统计：")
            print(f"   - 成功处理源文件：{len(processed_files)} 个")
            print(f"   - 缺失源文件：{len(missing_files)} 个")
            print(f"   - 合并后去重总记录：{len(all_content)} 条")
            print(f"   - 输出文件权限：{oct(os.stat(output_path).st_mode)[-3:]}")
        except PermissionError:
            print(f"❌ 写入{output_path}失败：权限不足")
            print(f"   解决方案：执行 chmod {oct(DIR_MODE)[2:]} {OUTPUT_DIR}")
        except Exception as e:
            print(f"❌ 写入{output_path}失败：{str(e)}")
    else:
        print("❌ 没有可合并的有效内容（所有源文件缺失/空内容）！")
        # 即使无内容，也创建空的输出文件保证文件存在
        try:
            with open(output_path, "w", encoding=FILE_ENCODING) as f:
                f.write("")
            os.chmod(output_path, FILE_MODE)
            print(f"ℹ️  已在输出目录创建空文件：{output_path}")
        except Exception as e:
            print(f"❌ 创建空文件失败：{str(e)}")

    # 打印缺失文件列表（方便排查）
    if missing_files:
        print("\n⚠️  缺失的源文件列表（请放到仓库根目录）：")
        for file in missing_files:
            print(f"   - {file}")

if __name__ == "__main__":
    # 移除root用户检查（仓库目录非/root，普通用户可正常运行，适配GitHub Actions）
    merge_multicast_files()
    print("\n📌 组播文件合并任务全部完成！")
