import os

# ==================== 配置项（适配仓库根目录iptvz，无iptv子文件夹） ====================
# 自动获取脚本所在的仓库根目录（iptvz），无需手动修改
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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
# 输出文件名：直接生成在仓库根目录iptvz下
OUTPUT_FILE = "HB.txt"
# 文件编码（确保和原文件一致，兼容UTF-8/GBK）
FILE_ENCODING = "utf-8"
# Linux文件权限设置
FILE_MODE = 0o644

def merge_multicast_files():
    """合并仓库根目录的组播文件，直接输出HB.txt到仓库根目录（无iptv子文件夹）"""
    # 存储所有内容（去重）
    all_content = set()
    # 记录处理的文件
    processed_files = []
    # 记录缺失的文件
    missing_files = []

    print("开始合并组播文件...")
    print("=" * 50)
    print(f"🔧 仓库根目录：{BASE_DIR}")
    print(f"🔧 输出文件：{os.path.join(BASE_DIR, OUTPUT_FILE)}（直接生成在根目录）")
    print("=" * 50)

    # 遍历所有源文件（读取仓库根目录的文件）
    for file_name in SOURCE_FILES:
        file_path = os.path.join(BASE_DIR, file_name)  # 源文件=仓库根目录+文件名
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
            print(f"⚠️  文件不存在：{file_path}（请检查是否放在仓库根目录iptvz下）")

    print("=" * 50)

    # 输出文件的完整路径：直接在仓库根目录下
    output_path = os.path.join(BASE_DIR, OUTPUT_FILE)
    
    # 写入合并后的内容
    if all_content:
        sorted_content = sorted(all_content)  # 排序保持内容一致性
        try:
            with open(output_path, "w", encoding=FILE_ENCODING) as f:
                f.write("\n".join(sorted_content))
            os.chmod(output_path, FILE_MODE)
            # 打印成功统计信息
            print(f"✅ 合并完成！HB.txt直接生成在仓库根目录：{output_path}")
            print(f"📊 合并统计：")
            print(f"   - 成功处理源文件：{len(processed_files)} 个")
            print(f"   - 缺失源文件：{len(missing_files)} 个")
            print(f"   - 合并后去重总记录：{len(all_content)} 条")
            print(f"   - 输出文件权限：{oct(os.stat(output_path).st_mode)[-3:]}")
        except PermissionError:
            print(f"❌ 写入{output_path}失败：权限不足")
            print(f"   解决方案：执行 chmod 755 {BASE_DIR}")
        except Exception as e:
            print(f"❌ 写入{output_path}失败：{str(e)}")
    else:
        print("❌ 没有可合并的有效内容（所有源文件缺失/空内容）！")
        # 即使无内容，也创建空的输出文件保证文件存在
        try:
            with open(output_path, "w", encoding=FILE_ENCODING) as f:
                f.write("")
            os.chmod(output_path, FILE_MODE)
            print(f"ℹ️  已在仓库根目录创建空文件：{output_path}")
        except Exception as e:
            print(f"❌ 创建空文件失败：{str(e)}")

    # 打印缺失文件列表（方便排查）
    if missing_files:
        print("\n⚠️  缺失的源文件列表（请放到仓库根目录iptvz下）：")
        for file in missing_files:
            print(f"   - {file}")

if __name__ == "__main__":
    # 直接运行，无root检查、无文件夹创建，极简逻辑
    merge_multicast_files()
    print("\n📌 组播文件合并任务全部完成！HB.txt在仓库根目录iptvz下")
