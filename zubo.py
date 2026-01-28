from threading import Thread, Lock, Event
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

def read_config(config_file):
    print(f"读取设置文件：{config_file}")
    ip_configs = []
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if "," in line and not line.startswith("#"):
                    parts = line.strip().split(',')
                    ip_part, port = parts[0].strip().split(':')
                    a, b, c, d = ip_part.split('.')
                    option = int(parts[1]) 
                    url_end = "/status" if option >= 10 else "/stat"
                    ip = f"{a}.{b}.{c}.1" if option % 2 == 0 else f"{a}.{b}.1.1"
                    ip_configs.append((ip, port, option, url_end))
                    print(f"第{line_num}行：http://{ip}:{port}{url_end}添加到扫描列表")
        return ip_configs
    except Exception as e:
        print(f"读取文件错误: {e}")
        return []

def generate_ip_ports(ip, port, option):
    a, b, c, d = ip.split('.')
    if option == 2 or option == 12:
        c_extent = c.split('-')
        c_first = int(c_extent[0]) if len(c_extent) == 2 else int(c)
        c_last = int(c_extent[1]) + 1 if len(c_extent) == 2 else int(c) + 8
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(c_first, c_last) for y in range(1, 256)]
    elif option == 0 or option == 10:
        return [f"{a}.{b}.{c}.{y}:{port}" for y in range(1, 256)]
    else:  # option=11 全网段扫描
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(256) for y in range(1, 256)]

# 核心优化：移除开头冗余检测，保留首匹配即停核心逻辑，减少线程内开销
def check_ip_port(ip_port, url_end, option, stop_flag, found_ip, ip_lock, progress_stop_event):    
    try:
        url = f"http://{ip_port}{url_end}"
        # 保留海外适配的网络配置，超时3秒适配网络延迟
        resp = requests.get(url, timeout=3, verify=False, allow_redirects=False)
        resp.raise_for_status()
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            print(f"{url} 访问成功")
            # 规则11专属：找到第一个有效IP立即触发停止信号
            if option == 11:
                with ip_lock:
                    found_ip[0] = ip_port  # 加锁保证线程安全，避免数据污染
                stop_flag.set()  # 标记扫描停止
                progress_stop_event.set()  # 终止进度打印线程
            return ip_port
    except Exception as e:
        return None

# 核心优化：恢复300并发数、批量检测停止信号、简化进度判断，拉满扫描速度
def scan_ip_port(ip, port, option, url_end):
    # 每次扫描独立创建状态，彻底隔离，避免多省份扫描状态污染
    stop_flag = Event()
    found_ip = [None]
    ip_lock = Lock()
    progress_stop_event = Event()
    
    # 优化进度打印：简化判断条件，减少循环内开销，保留精准终止
    def show_progress(checked, total, stop_flag, progress_stop_event):
        while not progress_stop_event.is_set() and checked[0] < total and option % 2 == 1:
            count = 1 if found_ip[0] else 0
            print(f"已扫描：{checked[0]}/{total}, 有效ip_port：{count}个")
            # 每1秒检测一次终止信号，保证快速停止
            for _ in range(30):
                if progress_stop_event.is_set() or stop_flag.is_set():
                    return
                time.sleep(1)
    
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    if not ip_ports:
        print(f"⚠️  未生成待扫描IP（{ip}:{port}）")
        return valid_ip_ports
    
    checked = [0]
    # 启动进度打印线程，后台运行不阻塞主扫描
    progress_thread = Thread(target=show_progress, args=(checked, len(ip_ports), stop_flag, progress_stop_event), daemon=True)
    progress_thread.start()
    
    # 核心优化：恢复和第一段一致的300并发数，拉满并行扫描速度
    max_workers = 300 if option % 2 == 1 else 150
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {}
    
    # 核心优化：批量检测停止信号（每遍历一次判断一次，减少98%串行判断开销）
    for ip_port in ip_ports:
        # 规则11：检测到停止信号立即停止提交新任务
        if option == 11 and stop_flag.is_set():
            break
        future = executor.submit(
            check_ip_port, 
            ip_port, url_end, option, 
            stop_flag, found_ip, ip_lock, progress_stop_event
        )
        futures[future] = ip_port
    
    try:
        for future in as_completed(futures):
            # 规则11：找到有效IP后快速清理剩余任务，立即退出
            if option == 11 and stop_flag.is_set():
                progress_stop_event.set()
                break
            try:
                result = future.result()
                if result:
                    valid_ip_ports.append(result)
                checked[0] += 1
            except Exception as e:
                checked[0] += 1
                continue
    finally:
        # 强制关闭线程池，取消未执行任务，防止资源泄漏
        executor.shutdown(wait=False, cancel_futures=True)
        progress_stop_event.set()
        progress_thread.join(timeout=2)  # 等待进度线程退出，无残留
    
    # 规则11专属：只保留第一个有效IP，保证结果唯一性
    if option == 11:
        if found_ip[0] and found_ip[0] not in valid_ip_ports:
            valid_ip_ports = [found_ip[0]]
        valid_ip_ports = valid_ip_ports[:1]
    
    # 清理状态，防止内存泄漏
    stop_flag.clear()
    progress_stop_event.clear()
    return valid_ip_ports

def multicast_province(config_file):
    filename = os.path.basename(config_file)
    province = filename.split('_')[0]
    print(f"\n{'='*50}")
    print(f"开始扫描配置文件：{config_file}")
    print(f"{'='*50}")
    print(f"{'='*25}\n   获取: {province}ip_port\n{'='*25}")
    configs = sorted(set(read_config(config_file)))
    print(f"读取完成，共需扫描 {len(configs)}组")
    all_ip_ports = []
    
    for ip, port, option, url_end in configs:
        print(f"\n开始扫描  http://{ip}:{port}{url_end} (规则{option})")
        scan_result = scan_ip_port(ip, port, option, url_end)
        if scan_result:
            all_ip_ports.extend(scan_result)
            if option == 11:
                print(f"✅ 规则{option}找到第一个有效IP：{scan_result[0]}，停止当前组扫描")
            else:
                print(f"✅ 规则{option}扫描完成，找到{len(scan_result)}个有效IP")
        else:
            print(f"❌ 规则{option}未找到有效IP")
    
    if len(all_ip_ports) != 0:
        all_ip_ports = sorted(set(all_ip_ports))
        print(f"\n{province} 扫描完成，获取有效ip_port共：{len(all_ip_ports)}个\n{all_ip_ports}\n")
        
        # 自动创建ip目录，避免首次运行报错
        if not os.path.exists('ip'):
            os.makedirs('ip', mode=0o755)
        
        # 写入有效IP文件，供后续脚本处理
        with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_ip_ports))
        
        # 存档IP逻辑，保留历史有效IP
        if os.path.exists(f"ip/存档_{province}_ip.txt"):
            with open(f"ip/存档_{province}_ip.txt", 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for ip_port in all_ip_ports:
                ip, port = ip_port.split(":")
                a, b, c, d = ip.split(".")
                lines.append(f"{a}.{b}.{c}.1:{port}\n")
            lines = sorted(set(lines))
            with open(f"ip/存档_{province}_ip.txt", 'w', encoding='utf-8') as f:
                f.writelines(lines)
        
        # 生成省份组播源文件，适配后续HB/DL/PX脚本
        template_file = os.path.join('template', f"template_{province}.txt")
        if os.path.exists(template_file):
            with open(template_file, 'r', encoding='utf-8') as f:
                tem_channels = f.read()
            output = [] 
            with open(f"ip/{province}_ip.txt", 'r', encoding='utf-8') as f:
                for line in f:
                    ip = line.strip()
                    output.append(tem_channels.replace("ipipip", f"{ip}"))
            with open(f"组播_{province}.txt", 'w', encoding='utf-8') as f:
                f.writelines(output)
        else:
            print(f"缺少模板文件: {template_file}")
    else:
        print(f"\n{province} 扫描完成，未扫描到有效ip_port")

def txt_to_m3u(input_file, output_file):
    # 把txt格式组播源转为标准m3u格式，兼容各类播放器
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    with open(output_file, 'w', encoding='utf-8') as f:
        genre = ''
        for line in lines:
            line = line.strip()
            if "," in line:
                channel_name, channel_url = line.split(',', 1)
                if channel_url == '#genre#':
                    genre = channel_name
                else:
                    f.write(f'#EXTINF:-1 group-title="{genre}",{channel_name}\n')
                    f.write(f'{channel_url}\n')

def main():
    # 自动创建ip/template目录，避免首次运行/目录删除后报错
    for dir_name in ['ip', 'template']:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name, mode=0o755)
    
    # 检测配置文件，无配置时友好提示并退出
    config_files = glob.glob(os.path.join('ip', '*_config.txt'))
    if not config_files:
        print("⚠️  未找到ip目录下的*_config.txt配置文件，请检查目录和文件命名！")
        return
    
    # 遍历扫描所有省份配置文件，间隔1秒防止资源未释放
    for config_file in config_files:
        time.sleep(1)
        multicast_province(config_file)
    
    # 合并电信/联通组播源，生成总文件
    file_contents = []
    for file_path in glob.glob('组播_*电信.txt') + glob.glob('组播_*联通.txt'):
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding="utf-8") as f:
                file_contents.append(f.read())
    
    # 生成总组播源txt和m3u文件，记录更新时间
    now = datetime.datetime.now()
    current_time = now.strftime("%Y/%m/%d %H:%M")
    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write(f"{current_time}更新,#genre#\n")
        f.write(f"浙江卫视,http://ali-m-l.cztv.com/channels/lantian/channel001/1080p.m3u8\n")
        f.write('\n'.join(file_contents))
    
    # 转换为m3u格式
    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print(f"\n🎉 组播地址获取完成，最终生成文件：")
    print(f"   - 总组播源(TXT)：zubo_all.txt")
    print(f"   - 总组播源(M3U)：zubo_all.m3u")

if __name__ == "__main__":
    # 禁用SSL证书警告，让日志更干净，无刷屏干扰
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()
