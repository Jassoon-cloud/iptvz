from threading import Thread, Lock, Event
import os
import time
import datetime
import glob
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==================== 移除全局变量，改为每次扫描时动态创建 ====================
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
    else:  # option=11
        return [f"{a}.{b}.{x}.{y}:{port}" for x in range(256) for y in range(1, 256)]

# 核心修改1：check_ip_port不再依赖全局变量，改用参数传递状态
def check_ip_port(ip_port, url_end, option, stop_flag, found_ip, ip_lock, progress_stop_event):    
    # 先检查是否需要停止
    if option == 11 and stop_flag.is_set():
        return None
    
    try:
        url = f"http://{ip_port}{url_end}"
        resp = requests.get(url, timeout=3, verify=False, allow_redirects=False)  # 关闭重定向，避免跨网段污染
        resp.raise_for_status()
        if "Multi stream daemon" in resp.text or "udpxy status" in resp.text:
            print(f"{url} 访问成功")
            
            if option == 11:
                with ip_lock:
                    found_ip[0] = ip_port  # 用列表（可变对象）存储找到的IP
                stop_flag.set()  # 标记停止
                progress_stop_event.set()  # 终止进度线程
            
            return ip_port
    except Exception as e:
        # 可选：打印失败原因，方便排查
        # print(f"{url} 扫描失败：{str(e)[:50]}")
        return None

# 核心修改2：scan_ip_port内创建所有局部状态，彻底隔离每次扫描
def scan_ip_port(ip, port, option, url_end):
    # 每次扫描都重新创建独立的状态变量，彻底隔离
    stop_flag = Event()  # 替换全局的stop_option_11
    found_ip = [None]    # 用列表存储找到的IP（可变对象）
    ip_lock = Lock()     # 每次扫描新建锁
    progress_stop_event = Event()  # 每次扫描新建进度终止事件
    
    def show_progress(checked, total, stop_flag, progress_stop_event):
        while not progress_stop_event.is_set() and checked[0] < total and (option % 2 == 1) and (not stop_flag.is_set() or option != 11):
            count = 1 if found_ip[0] else 0
            print(f"已扫描：{checked[0]}/{total}, 有效ip_port：{count}个")
            # 每1秒检查一次终止信号
            for _ in range(30):
                if progress_stop_event.is_set() or stop_flag.is_set():
                    return
                time.sleep(1)
    
    valid_ip_ports = []
    ip_ports = generate_ip_ports(ip, port, option)
    if not ip_ports:
        print(f"⚠️  未生成待扫描IP（{ip}:{port}）")
        return valid_ip_ports
    
    checked = [0]  # 用列表存储已扫描数量（可变对象）
    # 启动进度线程
    progress_thread = Thread(target=show_progress, args=(checked, len(ip_ports), stop_flag, progress_stop_event), daemon=True)
    progress_thread.start()
    
    # 配置并发数
    max_workers = 250 if option % 2 == 1 else 150
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {}
    
    # 提交扫描任务
    for ip_port in ip_ports:
        if option == 11 and stop_flag.is_set():
            break  # 找到有效IP后停止提交新任务
        future = executor.submit(
            check_ip_port, 
            ip_port, url_end, option, 
            stop_flag, found_ip, ip_lock, progress_stop_event  # 传递局部状态，而非全局
        )
        futures[future] = ip_port
    
    try:
        for future in as_completed(futures):
            if option == 11 and stop_flag.is_set():
                # 找到有效IP后，快速处理剩余任务并退出
                try:
                    result = future.result()
                    if result:
                        valid_ip_ports.append(result)
                except:
                    pass
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
        # 强制关闭线程池，确保无残留
        executor.shutdown(wait=False, cancel_futures=True)
        # 终止进度线程并等待其退出
        progress_stop_event.set()
        progress_thread.join(timeout=2)
    
    # 处理规则11的结果（只保留第一个有效IP）
    if option == 11:
        if found_ip[0] and found_ip[0] not in valid_ip_ports:
            valid_ip_ports = [found_ip[0]]
        valid_ip_ports = valid_ip_ports[:1]
    
    # 清空所有状态，防止内存泄漏
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
        # 每次扫描都是独立的，彻底隔离上一次的状态
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
        
        if not os.path.exists('ip'):
            os.makedirs('ip', mode=0o755)
        
        with open(f"ip/{province}_ip.txt", 'w', encoding='utf-8') as f:
            f.write('\n'.join(all_ip_ports))
        
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
    for dir_name in ['ip', 'template']:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name, mode=0o755)
    
    config_files = glob.glob(os.path.join('ip', '*_config.txt'))
    if not config_files:
        print("⚠️  未找到ip目录下的*_config.txt配置文件")
        return
    
    # 核心修改3：扫描每个配置文件前，强制等待1秒，确保所有资源清理完毕
    for config_file in config_files:
        time.sleep(1)  # 防止资源未释放
        multicast_province(config_file)
    
    file_contents = []
    for file_path in glob.glob('组播_*电信.txt') + glob.glob('组播_*联通.txt'):
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding="utf-8") as f:
                file_contents.append(f.read())
    
    now = datetime.datetime.now()
    current_time = now.strftime("%Y/%m/%d %H:%M")
    with open("zubo_all.txt", "w", encoding="utf-8") as f:
        f.write(f"{current_time}更新,#genre#\n")
        f.write(f"浙江卫视,http://ali-m-l.cztv.com/channels/lantian/channel001/1080p.m3u8\n")
        f.write('\n'.join(file_contents))
    
    txt_to_m3u("zubo_all.txt", "zubo_all.m3u")
    print(f"\n🎉 组播地址获取完成，最终文件：zubo_all.txt / zubo_all.m3u")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()
