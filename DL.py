import subprocess
import time
import re
import os
import threading
import socket
from urllib.parse import urlparse
from concurrent.futures import ProcessPoolExecutor, as_completed

# ==================== 配置参数（适配仓库根目录iptvz + FFmpeg，无iptv子文件夹） ====================
# 自动获取脚本所在的仓库根目录（iptvz），无需手动修改，跨环境兼容
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_FILE = os.path.join(BASE_DIR, "HB.txt")  # 读取HB.py生成的HB.txt（仓库根目录）
OUTPUT_FILE = os.path.join(BASE_DIR, "DL.txt")   # 结果保存到仓库根目录DL.txt
TEST_DURATION = 10      # 单次测试时长（秒）
RETRY_COUNT = 1         # 重试次数
# ffprobe绝对路径（请根据你仓库/服务器的实际路径修改！！！）
# 建议：将ffmpeg文件夹放到仓库根目录，路径就是 ./ffmpeg/bin/ffprobe，云端/本地都能识别
FFPROBE_PATH = os.path.join(BASE_DIR, "ffmpeg/bin/ffprobe")
TOTAL_TIMEOUT = 15      # 总超时时间（秒）
# 进程池大小（按需调整：1核设2，4核设4，8核设8，云端/本地通用）
PROCESS_POOL_SIZE = 4   
# 文件编码/权限（和HB.py保持一致，兼容UTF-8/GBK）
FILE_ENCODING = "utf-8"
FILE_MODE = 0o644

def is_ffprobe_available():
    """检查ffprobe是否可用（适配仓库路径，完善权限/路径提示）"""
    try:
        # 确保ffprobe有执行权限（自动修复，无需手动操作）
        if os.path.exists(FFPROBE_PATH) and not os.access(FFPROBE_PATH, os.X_OK):
            os.chmod(FFPROBE_PATH, 0o755)
            print(f"✅ 已自动给ffprobe添加执行权限：{FFPROBE_PATH}")
        
        # 测试ffprobe基础运行
        result = subprocess.run(
            [FFPROBE_PATH, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        if result.returncode == 0:
            print(f"✅ ffprobe检测通过，路径有效：{FFPROBE_PATH}")
            return True
        else:
            print(f"❌ ffprobe执行失败，返回码：{result.returncode}")
            print(f"错误详情：{result.stderr.decode('utf-8', errors='ignore')[:200]}")
            return False
    except FileNotFoundError:
        print(f"❌ 未找到ffprobe文件！当前配置路径：{FFPROBE_PATH}")
        print(f"📌 解决方案：")
        print(f"   1. 将ffmpeg文件夹放到【仓库根目录iptvz】下")
        print(f"   2. 确保路径为：iptvz/ffmpeg/bin/ffprobe")
        print(f"   3. 若服务器路径不同，直接修改代码中FFPROBE_PATH为实际绝对路径")
        return False
    except PermissionError:
        print(f"❌ ffprobe无执行权限！路径：{FFPROBE_PATH}")
        print(f"   手动修复命令：chmod +x {FFPROBE_PATH}")
        return False
    except Exception as e:
        print(f"❌ ffprobe检测异常：{str(e)}")
        return False

def parse_source_file():
    """解析源文件HB.txt（仓库根目录，兼容UTF-8/GBK，完善缺失提示）"""
    if not os.path.exists(SOURCE_FILE):
        print(f"❌ 错误：未找到待测试文件 → {SOURCE_FILE}")
        print(f"📌 请确保：")
        print(f"   1. HB.py已成功运行，生成了HB.txt")
        print(f"   2. HB.txt放在【仓库根目录iptvz】下（和本脚本同目录）")
        return []
    
    data_list = []
    try:
        with open(SOURCE_FILE, "r", encoding=FILE_ENCODING) as f:
            lines = f.readlines()
            for idx, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                
                # 适配「频道名,链接」逗号分隔格式（兼容多逗号场景）
                if "," in line:
                    parts = line.split(",")
                    channel_name = ",".join(parts[:-1]).strip()
                    channel_name = channel_name if channel_name else f"频道{idx}"
                    stream_url = parts[-1].strip()
                else:
                    channel_name = f"频道{idx}"
                    stream_url = line
                
                # 仅验证链接格式，不做网络预检查（保留原有逻辑）
                if stream_url.startswith(("http://", "udp://")):
                    data_list.append((idx, channel_name, stream_url))
                else:
                    print(f"⚠️  第{idx}行地址格式无效，跳过：{stream_url}")
        
        print(f"\n✅ HB.txt解析完成：共找到 {len(data_list)} 个有效格式的流地址")
        return data_list
    except UnicodeDecodeError:
        # 兼容GBK编码（Windows上传/本地生成的HB.txt大概率是GBK）
        try:
            with open(SOURCE_FILE, "r", encoding="gbk") as f:
                lines = f.readlines()
                for idx, line in enumerate(lines, 1):
                    line = line.strip()
                    if not line:
                        continue
                    if "," in line:
                        parts = line.split(",")
                        channel_name = ",".join(parts[:-1]).strip() or f"频道{idx}"
                        stream_url = parts[-1].strip()
                    else:
                        channel_name = f"频道{idx}"
                        stream_url = line
                    if stream_url.startswith(("http://", "udp://")):
                        data_list.append((idx, channel_name, stream_url))
                    else:
                        print(f"⚠️  第{idx}行格式无效，跳过：{stream_url}")
            print(f"\n✅ HB.txt解析完成（自动识别GBK编码）：共找到 {len(data_list)} 个有效格式的流地址")
            return data_list
        except Exception as e:
            print(f"❌ 读取HB.txt失败（编码不兼容）：{str(e)}")
            print(f"📌 建议：将HB.txt转换为UTF-8编码后重新运行")
            return []
    except PermissionError:
        print(f"❌ 读取HB.txt失败：权限不足！")
        print(f"   一键修复命令：chmod {oct(FILE_MODE)[2:]} {SOURCE_FILE}")
        return []
    except Exception as e:
        print(f"❌ 解析HB.txt文件失败：{str(e)}")
        return []

def test_single_stream(stream_url, process_ref, result_ref):
    """单次测试流稳定性（保留原有FFmpeg核心逻辑，完善UDP超时）"""
    cmd = [
        FFPROBE_PATH,
        "-v", "error",          # 只输出错误信息，减少冗余日志
        "-show_entries", "frame=pkt_pts_time",  # 检测帧时间戳（断流核心判断）
        "-of", "csv=p=0",       # 简化输出格式，方便解析
        "-timeout", str(TEST_DURATION * 1000000),  # ffprobe内部超时（微秒）
    ]
    # UDP专属超时配置，避免UDP链接阻塞（保留原有优化逻辑）
    if stream_url.startswith("udp://"):
        cmd.extend(["-stimeout", str(5 * 1000000)])  # UDP网络超时5秒
    cmd.extend([
        "-i", stream_url,       # 待测试流地址
        "-hide_banner"          # 隐藏banner信息，日志更整洁
    ])
    
    process = None
    last_frame_time = None
    has_disconnect = False
    
    try:
        # 启动ffprobe进程（保留原有管道/缓冲配置）
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        process_ref[0] = process
        
        start_time = time.time()
        # 循环检测指定时长，核心断流判断逻辑不变
        while time.time() - start_time < TEST_DURATION:
            if process.poll() is not None:  # 进程退出=流断开
                has_disconnect = True
                break
            
            # 读取帧时间戳，判断是否断流/时间戳回退
            line = process.stdout.readline()
            if line:
                line = line.strip()
                if line:
                    try:
                        current_frame_time = float(line)
                        # 时间戳回退超过1秒 = 断流重连（保留原有核心判断）
                        if last_frame_time is not None and current_frame_time < last_frame_time - 1:
                            has_disconnect = True
                            break
                        last_frame_time = current_frame_time
                    except:
                        continue
            
            # 5秒无新帧 = 断流（保留原有优化逻辑）
            if last_frame_time is not None:
                if time.time() - start_time - last_frame_time > 5:
                    has_disconnect = True
                    break
            
            time.sleep(0.1)
        
        # 测试结果：无断流=True，断流/异常=False
        result_ref[0] = not has_disconnect
    
    except Exception as e:
        print(f"⚠️  流测试单次异常：{str(e)[:50]}")
        result_ref[0] = False
    finally:
        # 强制终止进程，避免资源泄漏（保留原有逻辑）
        if process and process.poll() is None:
            try:
                process.terminate()
                time.sleep(0.3)
                if process.poll() is None:
                    process.kill()
            except Exception as e:
                print(f"⚠️  终止ffprobe进程失败：{str(e)[:30]}")

def test_stream_stability(stream_url) -> bool:
    """测试流稳定性（带重试/总超时，核心逻辑完全保留）"""
    total_start = time.time()
    
    # 重试机制，次数由RETRY_COUNT配置
    for retry in range(RETRY_COUNT + 1):
        # 总超时判断，避免无限阻塞
        if time.time() - total_start > TOTAL_TIMEOUT:
            print(f"⏰ 总耗时超{TOTAL_TIMEOUT}秒，强制终止", end="", flush=True)
            return False
        
        if retry > 0:
            print(f"\n🔄 第{retry}次重试...", end="", flush=True)
        
        process_ref = [None]
        result_ref = [False]
        
        # 启动测试线程，分离主进程（保留原有线程控制逻辑）
        test_thread = threading.Thread(
            target=test_single_stream,
            args=(stream_url, process_ref, result_ref)
        )
        test_thread.daemon = True
        test_thread.start()
        
        # 线程超时控制，避免线程阻塞
        test_thread.join(timeout=TOTAL_TIMEOUT - (time.time() - total_start))
        
        # 线程超时，强制终止
        if test_thread.is_alive():
            print(f"⏰ 单次测试超时，强制终止", end="", flush=True)
            if process_ref[0] and process_ref[0].poll() is None:
                process_ref[0].terminate()
            continue
        
        # 任意一次测试成功，直接返回True
        if result_ref[0]:
            return True
    
    # 所有重试失败，返回False
    return False

def main():
    print("🚀 组播源断流检测脚本（适配仓库根目录+FFmpeg+无预检查）")
    print(f"📁 仓库根目录：{BASE_DIR}")
    print(f"📥 读取文件：{SOURCE_FILE}（HB.py生成的HB.txt）")
    print(f"📤 输出文件：{OUTPUT_FILE}（稳定流地址保存为DL.txt）")
    print(f"⏱️  单次测试{TEST_DURATION}秒 | 重试{RETRY_COUNT}次 | 总超时{TOTAL_TIMEOUT}秒")
    print(f"⚡ 进程池并发数：{PROCESS_POOL_SIZE}")
    print(f"🔧 ffprobe路径：{FFPROBE_PATH}")
    print("="*60)
    
    # 移除root强制检查！适配GitHub Actions普通用户+VPS非root运行
    if os.geteuid() != 0:
        print("⚠️  提示：当前为非root用户运行，部分UDP/系统级权限可能受限")
        print("   若测试UDP流异常，可尝试：sudo python3 本脚本名.py\n")
    else:
        print("✅ 当前为root用户运行，权限充足\n")
    
    # 第一步：检查ffprobe是否可用，不可用则直接退出
    if not is_ffprobe_available():
        print("❌ ffprobe不可用，脚本终止运行")
        return
    
    # 第二步：解析HB.txt，获取待测试的流地址
    data_list = parse_source_file()
    if not data_list:
        print("❌ 未解析到有效流地址，脚本终止运行")
        return
    
    # 第三步：进程池批量检测流稳定性（核心逻辑不变）
    stable_data = []
    try:
        with ProcessPoolExecutor(max_workers=PROCESS_POOL_SIZE) as executor:
            # 提交所有测试任务，不区分链接类型，保留原有逻辑
            future_dict = {
                executor.submit(test_stream_stability, url): (idx, name, url)
                for idx, name, url in data_list
            }
            
            # 逐个处理测试结果，实时打印日志
            for future in as_completed(future_dict):
                idx, channel_name, stream_url = future_dict[future]
                print(f"\n📌 测试第{idx}个：{channel_name[:20]}")  # 截断长频道名，日志整洁
                print(f"🔗 地址：{stream_url[:50]}...")  # 截断长链接，日志整洁
                print(f"⌛ 测试中（总超时{TOTAL_TIMEOUT}秒）...", end="", flush=True)
                
                try:
                    is_stable = future.result()
                    if is_stable:
                        print("✅ 稳定（无断流/超时）")
                        stable_data.append((channel_name, stream_url))
                    else:
                        print("❌ 不稳定/超时/地址无效")
                except Exception as e:
                    print(f"❌ 检测异常：{str(e)[:50]}")
    except Exception as e:
        print(f"\n❌ 进程池运行异常：{str(e)}")
        return

    # 第四步：保存稳定流地址到DL.txt（仓库根目录）
    try:
        with open(OUTPUT_FILE, "w", encoding=FILE_ENCODING) as f:
            for channel_name, stream_url in stable_data:
                f.write(f"{channel_name},{stream_url}\n")
        # 设置文件权限，方便后续PX.py读取
        os.chmod(OUTPUT_FILE, FILE_MODE)
        print(f"\n✅ 已给DL.txt添加读取权限：{oct(FILE_MODE)[2:]}")
    except PermissionError:
        print(f"\n❌ 写入DL.txt失败：权限不足！")
        print(f"   一键修复命令：chmod 755 {BASE_DIR}")
        return
    except Exception as e:
        print(f"\n❌ 保存稳定流结果失败：{str(e)}")
        return
    
    # 输出最终统计信息，日志更直观
    print("\n" + "="*60)
    print(f"🎉 组播源断流检测全部完成！")
    print(f"📊 统计结果：")
    print(f"   📥 总测试流地址数：{len(data_list)}")
    print(f"   ✅ 稳定无断流地址数：{len(stable_data)}")
    print(f"   💾 稳定地址已保存到：{OUTPUT_FILE}")
    print(f"   📁 文件所在目录：【仓库根目录iptvz】（可直接给PX.py读取）")
    print("="*60)

if __name__ == "__main__":
    # 直接运行主函数，无多余依赖，和其他脚本联动无冲突
    main()
