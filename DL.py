import subprocess
import time
import re
import os
import threading
import socket
from urllib.parse import urlparse
from concurrent.futures import ProcessPoolExecutor, as_completed

# ==================== 配置参数（适配Linux + /root/iptv目录） ====================
BASE_DIR = "/root/iptv"
SOURCE_FILE = os.path.join(BASE_DIR, "HB.txt")  # 待测试文件
OUTPUT_FILE = os.path.join(BASE_DIR, "DL.txt")   # 结果保存文件
TEST_DURATION = 10      # 单次测试时长（秒）
RETRY_COUNT = 1         # 重试次数
# 直接指定ffprobe绝对路径（你的实际路径）
FFPROBE_PATH = "/root/iptv/ffmpeg/bin/ffprobe"
TOTAL_TIMEOUT = 15      # 总超时时间（秒）
# 进程池大小（固定值，无需psutil，VPS通用最优值）
PROCESS_POOL_SIZE = 4   # 1核VPS设2，4核设4，8核设8
# Linux文件编码（强制UTF-8）
FILE_ENCODING = "utf-8"
FILE_MODE = 0o644
DIR_MODE = 0o755

def is_ffprobe_available():
    """检查ffprobe是否可用"""
    try:
        # 确保ffprobe有执行权限
        if not os.access(FFPROBE_PATH, os.X_OK):
            os.chmod(FFPROBE_PATH, 0o755)
            print(f"✅ 已给ffprobe添加执行权限：{FFPROBE_PATH}")
        
        # 测试ffprobe运行
        result = subprocess.run(
            [FFPROBE_PATH, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        if result.returncode == 0:
            print(f"✅ ffprobe可用：{FFPROBE_PATH}")
            return True
        else:
            print(f"❌ ffprobe执行失败，返回码：{result.returncode}")
            print(f"错误信息：{result.stderr.decode('utf-8', errors='ignore')}")
            return False
    except FileNotFoundError:
        print(f"❌ 未找到ffprobe文件：{FFPROBE_PATH}")
        print(f"请检查路径是否正确，执行：ls -l {FFPROBE_PATH}")
        return False
    except PermissionError:
        print(f"❌ ffprobe无执行权限，尝试手动添加：chmod +x {FFPROBE_PATH}")
        return False
    except Exception as e:
        print(f"❌ ffprobe检测异常：{str(e)}")
        return False

def parse_source_file():
    """解析源文件（完全移除预检查）"""
    # 确保工作目录存在
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR, mode=DIR_MODE)
        print(f"⚠️  工作目录 {BASE_DIR} 不存在，已自动创建")
    
    if not os.path.exists(SOURCE_FILE):
        print(f"❌ 错误：未找到待测试文件 → {SOURCE_FILE}")
        print(f"请确保HB.txt文件放在 {BASE_DIR} 目录下！")
        return []
    
    data_list = []
    try:
        with open(SOURCE_FILE, "r", encoding=FILE_ENCODING) as f:
            lines = f.readlines()
            for idx, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                
                # 适配「频道名,链接」逗号分隔格式
                if "," in line:
                    parts = line.split(",")
                    channel_name = ",".join(parts[:-1]).strip()
                    if not channel_name:
                        channel_name = f"频道{idx}"
                    stream_url = parts[-1].strip()
                else:
                    channel_name = f"频道{idx}"
                    stream_url = line
                
                # 仅验证链接格式（不做任何网络预检查）
                if stream_url.startswith(("http://", "udp://")):
                    data_list.append((idx, channel_name, stream_url))
                else:
                    print(f"⚠️  第{idx}行地址格式无效，跳过：{stream_url}")
        
        print(f"\n✅ 解析完成：共找到 {len(data_list)} 个有效格式的地址（无预检查）")
        return data_list
    except UnicodeDecodeError:
        # 兼容GBK编码（Windows上传的文件）
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
                        print(f"⚠️  第{idx}行格式无效：{stream_url}")
            print(f"\n✅ 解析完成（GBK编码）：共找到 {len(data_list)} 个有效格式的地址")
            return data_list
        except Exception as e:
            print(f"❌ 读取文件失败（编码不兼容）：{str(e)}")
            return []
    except PermissionError:
        print(f"❌ 读取文件失败：权限不足！")
        print(f"   执行命令修复：chmod {oct(FILE_MODE)[2:]} {SOURCE_FILE}")
        return []
    except Exception as e:
        print(f"❌ 解析文件失败：{str(e)}")
        return []

def test_single_stream(stream_url, process_ref, result_ref):
    """单次测试流稳定性（Linux适配，补充UDP超时控制）"""
    cmd = [
        FFPROBE_PATH,
        "-v", "error",          # 只输出错误信息
        "-show_entries", "frame=pkt_pts_time",  # 检测帧时间戳
        "-of", "csv=p=0",       # 简化输出格式
        "-timeout", str(TEST_DURATION * 1000000),  # ffprobe内部超时（微秒）
    ]
    # 补充UDP网络超时配置（stimeout），避免UDP链接阻塞
    if stream_url.startswith("udp://"):
        cmd.extend(["-stimeout", str(5 * 1000000)])  # UDP网络超时5秒（微秒）
    cmd.extend([
        "-i", stream_url,       # 待测试流地址
        "-hide_banner"          # 隐藏banner信息
    ])
    
    process = None
    last_frame_time = None
    has_disconnect = False
    
    try:
        # 启动ffprobe进程
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        process_ref[0] = process
        
        start_time = time.time()
        # 循环检测TEST_DURATION秒
        while time.time() - start_time < TEST_DURATION:
            # 进程已退出 = 流断开
            if process.poll() is not None:
                has_disconnect = True
                break
            
            # 读取帧时间戳
            line = process.stdout.readline()
            if line:
                line = line.strip()
                if line:
                    try:
                        current_frame_time = float(line)
                        # 检测时间戳回退（断流重连特征）
                        if last_frame_time is not None and current_frame_time < last_frame_time - 1:
                            has_disconnect = True
                            break
                        last_frame_time = current_frame_time
                    except:
                        continue
            
            # 超过5秒无新帧 = 断流
            if last_frame_time is not None:
                if time.time() - start_time - last_frame_time > 5:
                    has_disconnect = True
                    break
            
            time.sleep(0.1)
        
        # 结果：无断流 = True，断流 = False
        result_ref[0] = not has_disconnect
    
    except Exception as e:
        print(f"⚠️  单次测试异常：{str(e)}")
        result_ref[0] = False
    finally:
        # 确保进程终止
        if process and process.poll() is None:
            try:
                process.terminate()
                time.sleep(0.3)
                if process.poll() is None:
                    process.kill()
            except Exception as e:
                print(f"⚠️  终止进程失败：{str(e)}")

def test_stream_stability(stream_url) -> bool:
    """测试流稳定性（带重试和总超时）"""
    total_start = time.time()
    
    # 重试机制
    for retry in range(RETRY_COUNT + 1):
        # 总超时判断
        if time.time() - total_start > TOTAL_TIMEOUT:
            print(f"⏰ 总耗时超{TOTAL_TIMEOUT}秒，强制终止")
            return False
        
        if retry > 0:
            print(f"\n🔄 第{retry}次重试...", end="", flush=True)
        
        process_ref = [None]
        result_ref = [False]
        
        # 启动测试线程
        test_thread = threading.Thread(
            target=test_single_stream,
            args=(stream_url, process_ref, result_ref)
        )
        test_thread.daemon = True
        test_thread.start()
        
        # 线程超时控制
        test_thread.join(timeout=TOTAL_TIMEOUT - (time.time() - total_start))
        
        # 线程超时
        if test_thread.is_alive():
            print(f"⏰ 单次测试超时，强制终止", end="", flush=True)
            if process_ref[0] and process_ref[0].poll() is None:
                process_ref[0].terminate()
            continue
        
        # 测试成功（无断流）
        if result_ref[0]:
            return True
    
    # 所有重试都失败
    return False

def main():
    print("🚀 组播源断流检测脚本（无预检查+无psutil依赖版）")
    print(f"📝 工作目录：{BASE_DIR}")
    print(f"⏱️  单次测试{TEST_DURATION}秒，重试{RETRY_COUNT}次，总超时{TOTAL_TIMEOUT}秒")
    print(f"⚡ 进程池大小：{PROCESS_POOL_SIZE}")
    print(f"📁 待测试文件：{SOURCE_FILE}")
    print(f"📁 结果输出文件：{OUTPUT_FILE}")
    print("="*60)
    
    # 检查root权限
    if os.geteuid() != 0:
        print("⚠️  警告：非root用户运行，可能存在权限问题！")
        print("   建议执行：sudo python3 /root/iptv/DL.py")
    
    # 检查ffprobe
    if not is_ffprobe_available():
        return
    
    # 解析源文件（无预检查）
    data_list = parse_source_file()
    if not data_list:
        print("❌ 无有效地址可测试")
        return
    
    # 进程池批量检测
    stable_data = []
    try:
        with ProcessPoolExecutor(max_workers=PROCESS_POOL_SIZE) as executor:
            # 提交所有链接的测试任务（不再区分gaoma/php）
            future_dict = {}
            
            # 所有链接都提交到进程池测试
            for idx, name, url in data_list:
                future_dict[executor.submit(test_stream_stability, url)] = (idx, name, url)
            
            # 处理所有测试结果
            for future in as_completed(future_dict):
                idx, channel_name, stream_url = future_dict[future]
                print(f"\n📌 正在测试第{idx}个：{channel_name}")
                print(f"🔗 地址：{stream_url}")
                print(f"⌛ 测试中（总超时{TOTAL_TIMEOUT}秒）...", end="", flush=True)
                
                try:
                    is_stable = future.result()
                    if is_stable:
                        print("✅ 稳定（无断流）")
                        stable_data.append((channel_name, stream_url))
                    else:
                        print("❌ 不稳定/超时/无效地址")
                except Exception as e:
                    print(f"❌ 检测异常：{str(e)}")
    except Exception as e:
        print(f"❌ 进程池运行异常：{str(e)}")
        return

    # 保存结果
    try:
        with open(OUTPUT_FILE, "w", encoding=FILE_ENCODING) as f:
            for channel_name, stream_url in stable_data:
                f.write(f"{channel_name},{stream_url}\n")
        # 设置文件权限
        os.chmod(OUTPUT_FILE, FILE_MODE)
    except PermissionError:
        print(f"❌ 写入文件失败：权限不足！")
        print(f"   执行命令修复：chmod {oct(DIR_MODE)[2:]} {BASE_DIR}")
        return
    except Exception as e:
        print(f"❌ 保存结果失败：{str(e)}")
        return
    
    # 输出统计信息（移除跳过相关统计）
    print("\n" + "="*60)
    print(f"🎉 测试完成！")
    print(f"📊 总测试地址数：{len(data_list)}")
    print(f"✅ 最终保存稳定地址数：{len(stable_data)}")
    print(f"💾 结果已保存到：{OUTPUT_FILE}")
    print(f"🔑 文件权限：{oct(os.stat(OUTPUT_FILE).st_mode)[-3:]}")

if __name__ == "__main__":
    # 直接运行主函数，无任何依赖安装逻辑
    main()